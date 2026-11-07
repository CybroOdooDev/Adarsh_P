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
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.meeting_transcription_summary.tools import stt_client, stt_worker


class _FakeWorker:
    """A speech worker served in a thread: the real protocol, a mocked engine."""

    def __init__(self, path):
        self.path = path
        self.server = None
        self.stop = threading.Event()

    def start(self):
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(4)
        self.server.settimeout(0.05)
        scheduler = stt_worker.Scheduler()

        def loop():
            while not self.stop.is_set():
                try:
                    conn, _addr = self.server.accept()
                except TimeoutError:
                    continue
                threading.Thread(target=stt_worker.serve_connection, args=(conn, scheduler), daemon=True).start()

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def close(self):
        if self.server:
            self.stop.set()
            self.thread.join(5)
            self.server.close()


def _closed_connection():
    sock, other = socket.socketpair()
    other.close()
    return sock


@tagged('post_install', '-at_install')
class TestSpeechWorkerClient(TransactionCase):
    """Odoo's side of the shared speech worker: starting it, and talking to it."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for patcher in (
            patch.object(stt_client, 'SOCKET_PATH', os.path.join(self.tmp, 'worker.sock')),
            patch.object(stt_client, 'START_LOCK_PATH', os.path.join(self.tmp, 'worker.lock')),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.worker = _FakeWorker(stt_client.SOCKET_PATH)
        self.addCleanup(self.worker.close)

    def _engine(self, **kwargs):
        """The worker's engine, mocked: ``handle`` returns ``kwargs``' reply."""
        patcher = patch.object(stt_worker, 'handle', **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_transcribe(self):
        self.worker.start()
        handle = self._engine(return_value={'text': 'Hello Ash.', 'language': 'en', 'language_probability': 0.9})
        result = stt_client.transcribe_with_info(b'RIFF audio', 'whisper', 'en-US', keywords=['Ash'],
                                                 beam_size=1, main_language='en', workers=2)
        self.assertEqual((result['text'], result['language'], result['language_probability']),
                         ('Hello Ash.', 'en', 0.9))
        self.assertGreaterEqual(result['queue_seconds'], 0)
        header, audio = handle.call_args.args
        self.assertEqual(audio, b'RIFF audio')
        self.assertEqual((header['language'], header['keywords'], header['beam_size'], header['workers']),
                         ('en-US', ['Ash'], 1, 2))
        handle.return_value = {}
        self.assertEqual(stt_client.transcribe(b'RIFF audio', 'whistle'), '', "silence")

    def test_worker_errors(self):
        self.worker.start()
        handle = self._engine()
        for error, exception in (
            ('busy', stt_client.SttWorkerUnavailable),
            ('not_installed: No module named needle', stt_client.SttWorkerUnavailable),
            ('RuntimeError()', stt_client.SttWorkerError),
        ):
            handle.return_value = {'error': error}
            with self.assertRaises(exception) as caught:
                stt_client.transcribe(b'RIFF audio', 'whisper')
            self.assertEqual(type(caught.exception), exception, error)

    def test_only_if_cold(self):
        self.worker.start()
        handle = self._engine(return_value={'text': ''})
        with patch.object(stt_worker, 'loaded_models', return_value=[['whisper', 'small', 1], ['whistle', None]]):
            for engine in ('whisper', 'whistle'):
                header = stt_client._header(engine, 'auto', 'small', [])
                self.assertIsNone(stt_client._request(header, b'', only_if_cold=True), engine)
            header = stt_client._header('whisper', 'auto', 'small', [], workers=2)
            self.assertTrue(stt_client._request(header, b'', only_if_cold=True), "loaded with another worker count")
        handle.assert_called_once()

    def test_start_worker(self):
        with open(stt_client.SOCKET_PATH, 'w', encoding='utf-8'):
            pass  # left by a worker that was killed
        proc = MagicMock(returncode=None)
        # the worker listens a moment after it is started
        proc.poll.side_effect = lambda: self.worker.start() if not self.worker.server else None
        with patch.object(stt_client, 'subprocess') as subprocess:
            subprocess.Popen.return_value = proc
            with stt_client._connect_or_start() as sock:
                self.assertEqual(sock.getpeername(), stt_client.SOCKET_PATH)
        self.assertEqual(subprocess.Popen.call_args.args[0],
                         [sys.executable, stt_client.WORKER_PATH, stt_client.SOCKET_PATH])
        self.assertTrue(subprocess.Popen.call_args.kwargs['start_new_session'])

    def test_start_worker_fails(self):
        with patch.object(stt_client, 'subprocess') as subprocess:
            subprocess.Popen.return_value = MagicMock(returncode=1, **{'poll.return_value': 1})
            with self.assertRaisesRegex(stt_client.SttWorkerError, r'exited at start \(code 1\)'):
                stt_client._connect_or_start()
            proc = subprocess.Popen.return_value = MagicMock(**{'poll.return_value': None})
            with patch.object(stt_client, 'START_TIMEOUT', -1), \
                    self.assertRaisesRegex(stt_client.SttWorkerError, 'did not start'):
                stt_client._connect_or_start()
            proc.kill.assert_called_once()

    def test_started_by_another_process(self):
        sock = MagicMock()
        with patch.object(stt_client, '_connect', side_effect=[OSError('refused'), sock]), \
                patch.object(stt_client, 'subprocess') as subprocess:
            self.assertIs(stt_client._connect_or_start(), sock)
        subprocess.Popen.assert_not_called()

    def test_unreachable_or_silent_worker(self):
        with patch.object(stt_client, '_connect_or_start', side_effect=OSError('denied')), \
                self.assertRaisesRegex(stt_client.SttWorkerError, 'unreachable: denied'):
            stt_client.transcribe(b'RIFF audio', 'whisper')
        # exiting as we connect: tried once more, with a fresh worker
        with patch.object(stt_client, '_connect_or_start', side_effect=[_closed_connection(), _closed_connection()]) \
                as connect, self.assertRaisesRegex(stt_client.SttWorkerError, 'does not answer'):
            stt_client.transcribe(b'RIFF audio', 'whisper')
        self.assertEqual(connect.call_count, 2)

    def _worker_that_hangs_up(self, hang_up):
        sock, worker_end = socket.socketpair()
        self.addCleanup(worker_end.close)
        worker_end.sendall(b'{"pid": 4242, "loaded": []}\n')
        if hang_up:
            worker_end.close()
        return patch.object(stt_client, '_connect_or_start', return_value=sock)

    def test_worker_stuck_or_closed(self):
        with self._worker_that_hangs_up(False), patch.object(stt_client, 'FIRST_LOAD_TIMEOUT', 0), \
                patch.object(stt_client, '_kill') as kill, \
                self.assertRaisesRegex(stt_client.SttWorkerError, 'timed out'):
            stt_client.transcribe(b'RIFF audio', 'whisper', lock_timeout=0)
        kill.assert_called_once_with(4242)
        with self._worker_that_hangs_up(True), self.assertRaisesRegex(stt_client.SttWorkerError, 'failed'):
            stt_client.transcribe(b'RIFF audio', 'whisper')

    def test_kill(self):
        with patch.object(os, 'kill', side_effect=ProcessLookupError) as kill:
            stt_client._kill(None)
            kill.assert_not_called()
            stt_client._kill(4242)  # already gone
        kill.assert_called_once_with(4242, signal.SIGKILL)

    def test_warm_up(self):
        with patch.object(stt_client, 'threading') as threading_mock:
            stt_client.warm_up('whisper', 'medium', workers=2)
        run = threading_mock.Thread.call_args.kwargs['target']
        for outcome in (None, stt_client.SttWorkerUnavailable('busy'), stt_client.SttWorkerError('down')):
            with patch.object(stt_client, '_request', side_effect=[outcome] if outcome else None) as request:
                run()
            header = request.call_args.args[0]
            self.assertEqual((header['model'], header['workers'], header['lock_timeout'], header['beam_size']),
                             ('medium', 2, 0, 1))
            self.assertTrue(request.call_args.kwargs['only_if_cold'])


@tagged('post_install', '-at_install')
class TestRecordingJobs(TransactionCase):
    """The detached processes that transcribe uploaded recordings, as Odoo sees them."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.job_dir = os.path.join(self.tmp, 'job')

    def _start(self, filename='board.MP3'):
        with patch.object(stt_client, 'subprocess') as subprocess:
            subprocess.Popen.return_value.pid = 4242
            stt_client.start_job(self.job_dir, {'engine': 'grok', 'api_key': 'xai-secret'}, b'ID3 audio', filename)
        return subprocess.Popen

    def test_start_job(self):
        os.makedirs(self.job_dir)
        with open(os.path.join(self.job_dir, 'result.json'), 'w', encoding='utf-8') as f:
            f.write('{"error": "an earlier attempt"}')
        popen = self._start()
        self.assertEqual(popen.call_args.args[0], [sys.executable, stt_client.JOB_PATH, self.job_dir])
        self.assertEqual(sorted(os.listdir(self.job_dir)), ['audio.mp3', 'heartbeat', 'job.log', 'pid', 'request.json'])
        with open(os.path.join(self.job_dir, 'request.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f), {'engine': 'grok', 'api_key': 'xai-secret', 'audio': 'audio.mp3'})
        self.assertEqual(os.stat(os.path.join(self.job_dir, 'request.json')).st_mode & 0o777, 0o600,
                         "the API key is readable by the Odoo user only")
        with open(os.path.join(self.job_dir, 'pid'), encoding='utf-8') as f:
            self.assertEqual(f.read(), '4242')
        self.assertEqual(stt_client.job_status(self.job_dir), ('running', None))
        self._start(filename=None)
        self.assertIn('audio.bin', os.listdir(self.job_dir))

    def test_job_status(self):
        self.assertEqual(stt_client.job_status(self.job_dir), ('failed', 'the transcription job was lost'))
        self._start()
        stale = time.time() - stt_client.JOB_STALE_SECONDS - 10
        os.utime(os.path.join(self.job_dir, 'heartbeat'), (stale, stale))
        status, reason = stt_client.job_status(self.job_dir)
        self.assertEqual(status, 'failed')
        self.assertIn('stopped unexpectedly', reason)
        with open(os.path.join(self.job_dir, 'result.json'), 'w', encoding='utf-8') as f:
            f.write('{"text": "Hello", "duration": 3.5}')
        self.assertEqual(stt_client.job_status(self.job_dir), ('done', {'text': 'Hello', 'duration': 3.5}))
        with open(os.path.join(self.job_dir, 'result.json'), 'w', encoding='utf-8') as f:
            f.write('{"text": ')
        self.assertEqual(stt_client.job_status(self.job_dir), ('failed', 'unreadable job result'))

    def test_cancel_running_job(self):
        self._start()
        with patch.object(os, 'kill') as kill:
            stt_client.cancel_job(self.job_dir)
        kill.assert_called_once_with(4242, signal.SIGTERM)
        self.assertFalse(os.path.exists(self.job_dir))

    def test_cancel_finished_job(self):
        self._start()
        with open(os.path.join(self.job_dir, 'result.json'), 'w', encoding='utf-8') as f:
            f.write('{"text": "Hello"}')
        with patch.object(os, 'kill') as kill:
            stt_client.cancel_job(self.job_dir)
        kill.assert_not_called()  # its pid may be another process's by now
        self.assertFalse(os.path.exists(self.job_dir))
