# -*- coding: utf-8 -*-
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

import importlib.metadata
import threading
import time
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.discuss_meeting_subtitles_ai.tools import stt_client, stt_worker


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
