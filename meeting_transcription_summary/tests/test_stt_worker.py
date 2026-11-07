#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies (<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions (<https://www.cybrosys.com>)
#
#    This program is free software: you can modify it under the terms of the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful, but
#    WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

import array
import importlib.metadata
import io
import json
import os
import runpy
import shutil
import socket
import sys
import tempfile
import threading
import time
import types
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.meeting_transcription_summary.tools import stt_client, stt_worker


@tagged('post_install', '-at_install')
class TestSpeechWorkerScheduler(TransactionCase):
    """Turns of the shared speech worker: how many captions are transcribed at once."""

    def test_one_caption_at_a_time_by_default(self):
        scheduler = stt_worker.Scheduler()
        self.assertTrue(scheduler.acquire(0, engine='whisper'))
        self.assertEqual(scheduler.idle_seconds(), 0.0)
        self.assertFalse(scheduler.acquire(0, engine='whisper'), "a second caption waits for the first")
        scheduler.release('whisper')
        self.assertTrue(scheduler.acquire(0, engine='whisper'))

    def test_workers_transcribe_captions_together(self):
        scheduler = stt_worker.Scheduler()
        self.assertTrue(scheduler.acquire(0, workers=2, engine='whisper'))
        self.assertTrue(scheduler.acquire(0, workers=2, engine='whisper'))
        self.assertFalse(scheduler.acquire(0, workers=2, engine='whisper'), "a third waits for a free worker")
        scheduler.release('whisper')
        self.assertTrue(scheduler.acquire(0, workers=2, engine='whisper'))

    def test_whistle_one_at_a_time(self):
        scheduler = stt_worker.Scheduler()
        self.assertTrue(scheduler.acquire(0, workers=2, engine='whistle'))
        self.assertFalse(scheduler.acquire(0, workers=2, engine='whistle'))
        self.assertTrue(scheduler.acquire(0, workers=2, engine='whisper'), "Whisper may run beside it")
        scheduler.release('whistle')
        scheduler.release('whisper')
        self.assertTrue(scheduler.acquire(0, workers=2, engine='whistle'))

    def test_waiting_caption_gets_the_next_turn(self):
        scheduler = stt_worker.Scheduler()
        self.assertTrue(scheduler.acquire(0, engine='whisper'))
        result = {}
        thread = threading.Thread(target=lambda: result.update(got=scheduler.acquire(5, engine='whisper')))
        thread.start()
        deadline = time.monotonic() + 5
        while not scheduler._waiting and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(scheduler._waiting, 1)
        scheduler.release('whisper')
        thread.join(5)
        self.assertTrue(result['got'])

    def test_request_workers(self):
        self.assertEqual(stt_worker.request_workers({}), 1)
        self.assertEqual(stt_worker.request_workers({'workers': 3}), 3)
        self.assertEqual(stt_worker.request_workers({'workers': 0}), 1)
        self.assertEqual(stt_worker.request_workers({'workers': 'many'}), 1)

    def test_header_carries_workers(self):
        self.assertEqual(stt_client._header('whisper', 'en', 'small', [])['workers'], 1)
        self.assertEqual(stt_client._header('whisper', 'en', 'small', [], workers=2)['workers'], 2)

    def test_missing_package(self):
        def distribution(name):
            if name != 'faster-whisper':
                raise importlib.metadata.PackageNotFoundError(name)

        with patch.object(importlib.metadata, 'distribution', side_effect=distribution):
            self.assertIsNone(stt_client.missing_package('whisper'))
            self.assertEqual(stt_client.missing_package('whistle'), 'cactus-needle')
            self.assertIsNone(stt_client.missing_package('grok'), "a cloud engine needs no package")


def _wav(samples, rate=16000, channels=1):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(array.array('h', samples).tobytes())
    return buf.getvalue()


class _Samples(list):
    """Just enough of a numpy array for decode_wav (numpy is optional in Odoo's Python)."""

    def astype(self, _dtype):
        return self

    def __truediv__(self, divisor):
        return _Samples(value / divisor for value in self)

    def reshape(self, _rows, columns):
        return _Samples(self[i:i + columns] for i in range(0, len(self), columns))

    def mean(self, axis):
        return _Samples(sum(row) / len(row) for row in self)


def _fake_numpy():
    numpy = types.ModuleType('numpy')
    numpy.int16 = numpy.float32 = None
    numpy.frombuffer = lambda frames, dtype: _Samples(array.array('h', frames))
    return numpy


def _segment(text, no_speech_prob=0.01, avg_logprob=-0.2, compression_ratio=1.2):
    return SimpleNamespace(text=text, no_speech_prob=no_speech_prob, avg_logprob=avg_logprob,
                           compression_ratio=compression_ratio)


class _FakeWhisperModel:
    """Stands in for faster_whisper.WhisperModel: records what it is asked to transcribe."""
    supported_languages = ['en', 'fr']
    segments = []
    detected = ('fr', 0.5)
    instances = []

    def __init__(self, size, **kwargs):
        self.size, self.kwargs = size, kwargs
        self.calls = []
        self.instances.append(self)

    def detect_language(self, samples):
        return self.detected[0], self.detected[1], []

    def transcribe(self, audio, **options):
        self.calls.append((audio, options, isinstance(audio, str) and os.path.exists(audio)))
        info = SimpleNamespace(language=options['language'] or 'en', language_probability=0.95, duration=2.0)
        return iter(self.segments), info


@tagged('post_install', '-at_install')
class TestSpeechWorkerTranscription(TransactionCase):
    """What the worker does with one request: decoding, the engines, and the filtering of their text."""

    def setUp(self):
        super().setUp()
        faster_whisper = types.ModuleType('faster_whisper')
        faster_whisper.audio = types.ModuleType('faster_whisper.audio')
        self.av_open = MagicMock(return_value='container')
        faster_whisper.audio.av = SimpleNamespace(open=self.av_open)
        faster_whisper.WhisperModel = _FakeWhisperModel
        _FakeWhisperModel.instances = []
        _FakeWhisperModel.segments = []
        for patcher in (
            patch.dict(sys.modules, {'numpy': _fake_numpy(), 'faster_whisper': faster_whisper,
                                     'faster_whisper.audio': faster_whisper.audio}),
            patch.dict(stt_worker._whisper_models, clear=True),
            patch.object(stt_worker, '_whistle_loaded', False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_decode_wav(self):
        self.assertIsNone(stt_worker.decode_wav(b'OggS not a wav'))
        self.assertIsNone(stt_worker.decode_wav(_wav([0, 0], rate=8000)), "only 16 kHz is read directly")
        self.assertEqual(stt_worker.decode_wav(_wav([16384, -16384])), [0.5, -0.5])
        self.assertEqual(stt_worker.decode_wav(_wav([16384, 0, -16384, -16384], channels=2)), [0.25, -0.5],
                         "stereo is mixed down to mono")

    def test_patch_faster_whisper_av(self):
        stt_worker.patch_faster_whisper_av()
        av = sys.modules['faster_whisper.audio'].av
        self.assertEqual(av.open('clip.webm', metadata_errors='ignore'), 'container')
        self.av_open.assert_called_once_with('clip.webm')

    def test_whisper_model_loaded_once_per_workers(self):
        model = stt_worker.whisper_model('small')
        self.assertIs(stt_worker.whisper_model('small'), model)
        self.assertEqual((model.size, model.kwargs['num_workers'], model.kwargs['compute_type']), ('small', 1, 'int8'))
        self.assertEqual(stt_worker.loaded_models(), [['whisper', 'small', 1]])
        replicas = stt_worker.whisper_model('small', workers=2)
        self.assertIsNot(replicas, model, "another number of workers loads it again")
        self.assertEqual(replicas.kwargs['cpu_threads'], (os.cpu_count() or 0) // 2)

    def test_transcribe_whisper_unsure_language(self):
        _FakeWhisperModel.detected = ('fr', 0.5)
        _FakeWhisperModel.segments = [_segment(' Ship it on Friday. '), _segment(' Subscribe now', no_speech_prob=0.9)]
        result = stt_worker.transcribe_whisper(
            _wav([0] * 160), 'auto', 'small', ['Ash', 'Odoo'], prompt='Previous caption.',
            main_language='en-US', without_timestamps=True)
        self.assertEqual(result, {'text': 'Ship it on Friday.', 'language': 'en',
                                  'language_probability': 0.0, 'duration': 2.0},
                         "an assumed language is not reported as detected")
        samples, options, _is_file = _FakeWhisperModel.instances[0].calls[0]
        self.assertEqual(len(samples), 160)
        self.assertEqual((options['language'], options['hotwords'], options['initial_prompt'],
                          options['without_timestamps']), ('en', 'Ash Odoo', 'Previous caption.', True))

    def test_transcribe_whisper_confident_language(self):
        _FakeWhisperModel.detected = ('fr', 0.9)
        _FakeWhisperModel.segments = [_segment('Merci.')]
        result = stt_worker.transcribe_whisper(_wav([0] * 160), 'auto', 'small', [], main_language='en-US')
        self.assertEqual((result['text'], result['language'], result['language_probability']), ('Merci.', 'fr', 0.9),
                         "a confidently said stock phrase is kept")

    def test_transcribe_whisper_other_container(self):
        _FakeWhisperModel.segments = [_segment('Thank you.', avg_logprob=-0.8)]
        result = stt_worker.transcribe_whisper(b'\x1aE\xdf\xa3 webm', 'de-DE', 'small', [])
        path, options, existed = _FakeWhisperModel.instances[0].calls[0]
        self.assertTrue(existed, "a webm clip is handed over as a file")
        self.assertFalse(os.path.exists(path), "and the file is removed afterwards")
        self.assertIsNone(options['language'], "a language the model lacks is detected instead")
        self.assertNotIn('hotwords', options)
        self.assertEqual((result['text'], result['language_probability']), ('', 0.95),
                         "an unsure stock phrase is dropped")

    def test_transcribe_whistle(self):
        needle = types.ModuleType('needle')
        needle.transcribe = MagicMock(return_value={'text': '[Music] Hello there.', 'language': 'en'})
        with patch.dict(sys.modules, {'needle': needle}), patch.dict(os.environ):
            self.assertEqual(stt_worker.transcribe_whistle(_wav([0] * 160), 'ja-JP', []), {'text': ''})
            self.assertEqual(stt_worker.transcribe_whistle(b'OggS', 'auto', []), {'text': ''})
            self.assertEqual(stt_worker.loaded_models(), [])
            result = stt_worker.transcribe_whistle(_wav([0] * 160), 'en-US', ['Ash'])
        self.assertEqual(result, {'text': 'Hello there.', 'language': 'en', 'language_probability': 0.0})
        self.assertEqual(needle.transcribe.call_args.kwargs, {'language': 'en', 'keywords': ['Ash']})
        self.assertEqual(stt_worker.loaded_models(), [['whistle', None]])

    def test_handle(self):
        with patch.object(stt_worker, 'transcribe_whistle', return_value={'text': 'a'}) as whistle:
            self.assertEqual(stt_worker.handle({'engine': 'whistle', 'language': 'en'}, b'audio'), {'text': 'a'})
        whistle.assert_called_once_with(b'audio', 'en', [])
        with patch.object(stt_worker, 'transcribe_whisper', return_value={'text': 'b'}) as whisper:
            stt_worker.handle({'engine': 'whisper', 'language': 'fr', 'keywords': ['Ash'], 'beam_size': '1',
                               'workers': 2, 'prompt': 'Before.', 'main_language': 'en'}, b'audio')
        self.assertEqual(whisper.call_args.args, (b'audio', 'fr', 'small', ['Ash']))
        self.assertEqual(whisper.call_args.kwargs, {'prompt': 'Before.', 'beam_size': 1, 'main_language': 'en',
                                                    'without_timestamps': True, 'workers': 2})
        with self.assertRaisesRegex(ValueError, 'unknown engine'):
            stt_worker.handle({'engine': 'morse'}, b'audio')

    def test_read_exact(self):
        self.assertEqual(stt_worker.read_exact(io.BytesIO(b'abc'), 2), b'ab')
        with self.assertRaises(EOFError):
            stt_worker.read_exact(io.BytesIO(b'abc'), 5)


@tagged('post_install', '-at_install')
class TestSpeechWorkerServer(TransactionCase):
    """The worker's side of the socket protocol, and its life cycle."""

    def _serve(self, request=None, scheduler=None, **handle):
        """Run one connection; return the worker's hello and its reply (None if it sent none)."""
        server_end, client = socket.socketpair()
        scheduler = scheduler or stt_worker.Scheduler()
        with patch.object(stt_worker, 'handle', **handle), client, client.makefile('rwb') as stream:
            thread = threading.Thread(target=stt_worker.serve_connection, args=(server_end, scheduler))
            thread.start()
            hello = json.loads(stream.readline())
            if request is None:
                client.shutdown(socket.SHUT_WR)
            else:
                client.sendall(request)
            reply = stream.readline()
            thread.join(5)
        return hello, json.loads(reply) if reply else None

    def _request(self, audio=b'RIFF audio', **header):
        header = dict({'engine': 'whisper', 'lock_timeout': 0}, **header, size=len(audio))
        return json.dumps(header).encode() + b'\n' + audio

    def test_hello_only(self):
        hello, reply = self._serve()
        self.assertEqual(hello, {'pid': os.getpid(), 'loaded': []})
        self.assertIsNone(reply)

    def test_bad_request(self):
        self.assertIsNone(self._serve(b'not json\n')[1])
        self.assertIsNone(self._serve(b'{"engine": "whisper"}\n')[1], "a request without its size")

    def test_transcription(self):
        _hello, reply = self._serve(self._request(), return_value={'text': 'Hello.', 'language': 'en'})
        self.assertEqual((reply['text'], reply['language']), ('Hello.', 'en'))
        self.assertGreaterEqual(reply['queue_seconds'], 0)
        self.assertGreaterEqual(reply['stt_seconds'], 0)

    def test_errors(self):
        scheduler = stt_worker.Scheduler()
        self.assertTrue(scheduler.acquire(0))
        self.assertEqual(self._serve(self._request(), scheduler)[1], {'error': 'busy'})
        scheduler.release()
        _hello, reply = self._serve(self._request(), side_effect=ImportError('No module named needle'))
        self.assertEqual(reply['error'], 'not_installed: No module named needle')
        _hello, reply = self._serve(self._request(), side_effect=RuntimeError('model crashed'))
        self.assertEqual(reply['error'], "RuntimeError('model crashed')", "the worker keeps serving")

    def test_scheduler_idle_time(self):
        scheduler = stt_worker.Scheduler()
        scheduler.touch()
        self.assertGreaterEqual(scheduler.idle_seconds(), 0.0)

    def _main(self, select, code_path=None, idle_exit=0):
        """Run the worker's main loop with ``select`` standing in for select.select."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        sock_path = os.path.join(tmp, 'worker.sock')
        resource = MagicMock()
        resource.getrlimit.return_value = (1, 2)
        with patch.object(sys, 'argv', ['stt_worker.py', sock_path]), patch.object(sys, 'stdout'), \
                patch.object(stt_worker.os, 'dup2'), patch.object(stt_worker, 'signal'), \
                patch.object(stt_worker, 'resource', resource), \
                patch.object(stt_worker, 'select', MagicMock(select=MagicMock(side_effect=select))), \
                patch.object(stt_worker, 'IDLE_EXIT_SECONDS', idle_exit), \
                patch.object(stt_worker, '__file__', code_path or stt_worker.__file__):
            stt_worker.main()
        resource.setrlimit.assert_called_once_with(resource.RLIMIT_AS, (2, 2))
        self.assertFalse(os.path.exists(sock_path), "the socket is removed on exit")
        return sock_path

    def test_main_exits_when_idle(self):
        self._main(lambda *args: ([], [], []))

    def test_main_exits_when_code_changes(self):
        fd, code_path = tempfile.mkstemp(suffix='.py')
        os.close(fd)
        self.addCleanup(os.unlink, code_path)

        def select(*args):
            os.utime(code_path, (0, 0))
            return [], [], []

        self._main(select, code_path, idle_exit=900)

    def test_main_serves_connections(self):
        clients = []

        def select(readable, *args):
            if clients:
                return [], [], []
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(sys.argv[1])
            clients.append(client)
            return readable, [], []

        self._main(select)
        with clients[0] as client, client.makefile('rb') as stream:
            self.assertEqual(json.loads(stream.readline())['pid'], os.getpid())

    def test_run_as_script(self):
        # a socket path that cannot be bound: the script starts, then stops at once
        with patch.object(sys, 'argv', ['stt_worker.py', '/nonexistent/dir/worker.sock']), \
                patch.object(sys, 'stdout'), patch('os.dup2'), patch('resource.setrlimit'), \
                self.assertRaises(FileNotFoundError):
            runpy.run_path(stt_worker.__file__, run_name='__main__')
