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
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.discuss_meeting_subtitles_ai.tools import grok_stt


def _reply(status=200, json_data=None):
    response = MagicMock(status_code=status, text='raw reply')
    response.json.return_value = json_data
    return response


@tagged('post_install', '-at_install')
class TestGrokStt(TransactionCase):
    """The Grok STT client: the request sent, and why a failed one failed."""

    def test_request(self):
        reply = _reply(json_data={'text': 'Hello Ash.', 'language': 'en'})
        with patch.object(grok_stt._session, 'post', return_value=reply) as post:
            result = grok_stt.transcribe(b'RIFF audio', 'xai-test', language='en-US', keywords=['Ash', ' Ash ', ''])
        self.assertEqual(result['text'], 'Hello Ash.')
        self.assertEqual(post.call_args.kwargs['headers'], {'Authorization': 'Bearer xai-test'})
        self.assertEqual(post.call_args.kwargs['data'], [
            ('model', grok_stt.MODEL), ('language', 'en'), ('format', 'true'), ('keyterm', 'Ash')])

    def _error(self, **post):
        with patch.object(grok_stt._session, 'post', **post), \
                self.assertRaises(grok_stt.GrokSttError) as caught:
            grok_stt.transcribe(b'RIFF audio', 'xai-test')
        return caught.exception

    def test_errors(self):
        error = self._error(return_value=_reply(401, {'error': {'message': 'Invalid API key'}}))
        self.assertIn('returned 401: Invalid API key', str(error))
        self.assertEqual((error.kind, error.status), ('auth', 401))
        error = self._error(return_value=_reply(429, {'error': 'Too many requests'}))
        self.assertIn('Too many requests', str(error))
        self.assertEqual((error.kind, error.status), ('rate_limit', 429))
        error = self._error(return_value=_reply(500, None))
        self.assertIn('returned 500: raw reply', str(error))
        self.assertEqual((error.kind, error.status), ('error', 500))
        self.assertEqual(self._error(side_effect=requests.ConnectionError('refused')).kind, 'unreachable')
        self.assertEqual(self._error(side_effect=requests.ReadTimeout('slow')).kind, 'timeout')
        unreadable = _reply()
        unreadable.json.side_effect = ValueError('not JSON')
        self.assertEqual(self._error(return_value=unreadable).kind, 'error')
        with patch.object(grok_stt, 'MAX_FILE_BYTES', 4), \
                self.assertRaisesRegex(grok_stt.GrokSttError, '500 MB') as caught:
            grok_stt.transcribe(b'RIFF audio', 'xai-test')
        self.assertEqual(caught.exception.kind, 'too_large')
