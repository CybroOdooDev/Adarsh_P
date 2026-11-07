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
import runpy
import shutil
import sys
import tempfile
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from odoo.addons.meeting_transcription_summary.tools import (
    grok_stt,
    stt_job,
    stt_worker,
)


@tagged('post_install', '-at_install')
class TestRecordingJobProcess(TransactionCase):
    """The detached process that transcribes one uploaded recording (stt_job.py)."""

    def setUp(self):
        super().setUp()
        self.job_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.job_dir, ignore_errors=True)
        with open(os.path.join(self.job_dir, 'audio.mp3'), 'wb') as f:
            f.write(b'ID3 audio')

    def _write_request(self, **request):
        stt_job.write_json(self.job_dir, 'request.json', dict({'audio': 'audio.mp3'}, **request))

    def _result(self):
        with open(os.path.join(self.job_dir, 'result.json'), encoding='utf-8') as f:
            return json.load(f)

    def test_write_json(self):
        stt_job.write_json(self.job_dir, 'result.json', {'text': 'Hello'})
        self.assertEqual(self._result(), {'text': 'Hello'})
        self.assertNotIn('result.json.tmp', os.listdir(self.job_dir))

    def test_heartbeat(self):
        stop = MagicMock(**{'is_set.side_effect': [False, True]})
        stt_job.heartbeat(self.job_dir, stop)
        self.assertIn('heartbeat', os.listdir(self.job_dir))
        stop.wait.assert_called_once_with(stt_job.HEARTBEAT_SECONDS)
        stop = MagicMock(**{'is_set.return_value': False})
        stt_job.heartbeat(os.path.join(self.job_dir, 'cancelled'), stop)
        stop.wait.assert_not_called()

    def test_run_grok(self):
        reply = {'text': 'Hello.', 'duration': 12.5, 'words': []}
        with patch.dict(sys.modules, {'grok_stt': grok_stt}), \
                patch.object(grok_stt, 'transcribe', return_value=reply) as transcribe:
            result = stt_job.run(self.job_dir, {'engine': 'grok', 'audio': 'audio.mp3', 'api_key': 'xai-test',
                                                'language': 'en', 'keywords': ['Ash']})
        self.assertEqual(result, {'text': 'Hello.', 'duration': 12.5})
        self.assertEqual(transcribe.call_args.args, (b'ID3 audio', 'xai-test'))
        self.assertEqual((transcribe.call_args.kwargs['filename'], transcribe.call_args.kwargs['diarize']),
                         ('audio.mp3', True))

    def test_run_whisper(self):
        with patch.dict(sys.modules, {'stt_worker': stt_worker}), \
                patch.object(stt_worker, 'patch_faster_whisper_av') as patch_av, \
                patch.object(stt_worker, 'transcribe_whisper', return_value={'text': 'Hello.'}) as transcribe:
            result = stt_job.run(self.job_dir, {'engine': 'whisper', 'audio': 'audio.mp3', 'language': 'fr'})
        self.assertEqual(result, {'text': 'Hello.', 'duration': None})
        patch_av.assert_called_once()
        self.assertEqual(transcribe.call_args.args, (b'ID3 audio', 'fr', 'small', []))
        self.assertEqual(transcribe.call_args.kwargs, {'beam_size': 5, 'main_language': None})

    def _main(self, **run):
        resource = MagicMock(**{'getrlimit.return_value': (1, 2)})
        with patch.object(sys, 'argv', ['stt_job.py', self.job_dir]), \
                patch.object(stt_job, 'resource', resource), patch.object(stt_job, 'run', **run):
            stt_job.main()
        resource.setrlimit.assert_called_once_with(resource.RLIMIT_AS, (2, 2))
        return self._result()

    def test_main(self):
        self._write_request(engine='grok')
        self.assertEqual(self._main(return_value={'text': 'Hello.', 'duration': 1.0}),
                         {'text': 'Hello.', 'duration': 1.0})
        self.assertEqual(self._main(side_effect=ImportError('No module named faster_whisper')),
                         {'error': 'not_installed: No module named faster_whisper'})
        with mute_logger('stt_job'):
            self.assertEqual(self._main(side_effect=RuntimeError('model crashed')), {'error': 'model crashed'})
            self.assertEqual(self._main(side_effect=RuntimeError()), {'error': 'RuntimeError()'})

    def test_main_cancelled_meanwhile(self):
        self._write_request(engine='grok')
        with patch.object(sys, 'argv', ['stt_job.py', self.job_dir]), patch.object(stt_job, 'resource', **{'getrlimit.return_value': (2, 2)}), \
                patch.object(stt_job, 'run', side_effect=lambda job_dir, request: shutil.rmtree(job_dir)):
            stt_job.main()  # nothing left to write the result into
        self.assertFalse(os.path.exists(self.job_dir))

    def test_run_as_script(self):
        self._write_request(engine='grok', api_key='xai-test')
        with patch.object(sys, 'argv', ['stt_job.py', self.job_dir]), patch('resource.setrlimit'), \
                patch.dict(sys.modules, {'grok_stt': None}):
            runpy.run_path(stt_job.__file__, run_name='__main__')
        self.assertTrue(self._result()['error'].startswith('not_installed'))
