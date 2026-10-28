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

from odoo.addons.discuss_meeting_subtitles_ai.tools import cloud_whisper


def _reply(status=200, json_data=None):
    response = MagicMock(status_code=status, text='raw reply')
    response.json.return_value = json_data
    return response


def _segment(text, no_speech_prob=0.01, avg_logprob=-0.2, compression_ratio=1.2):
    return {'text': text, 'no_speech_prob': no_speech_prob, 'avg_logprob': avg_logprob,
            'compression_ratio': compression_ratio}


@tagged('post_install', '-at_install')
class TestCloudWhisper(TransactionCase):
    """Whisper behind an OpenAI-compatible API: the request sent and the reply's filtering."""

    def _transcribe(self, reply, **kwargs):
        with patch.object(cloud_whisper._session, 'post', return_value=reply) as post:
            return cloud_whisper.transcribe(b'RIFF audio', **kwargs), post

    def test_request(self):
        result, post = self._transcribe(
            _reply(json_data={'text': ' Hello Ash. ', 'language': 'english', 'segments': [_segment(' Hello Ash. ')]}),
            api_key='gsk_test', url='https://api.groq.com/openai/v1/', language='en-US',
            keywords=['Ash', ' Odoo ', 'Ash', ''])
        self.assertEqual(result, {'text': 'Hello Ash.', 'language': 'en'})
        self.assertEqual(post.call_args.args[0], 'https://api.groq.com/openai/v1/audio/transcriptions')
        self.assertEqual(post.call_args.kwargs['headers'], {'Authorization': 'Bearer gsk_test'})
        data = post.call_args.kwargs['data']
        self.assertEqual((data['model'], data['language'], data['prompt'], data['response_format']),
                         ('whisper-large-v3', 'en', 'Ash, Odoo', 'verbose_json'))

    def test_no_key_and_auto_language(self):
        _result, post = self._transcribe(_reply(json_data={'text': 'Hi there.'}), url='http://gpu:8000/v1',
                                         language='auto')
        self.assertEqual(post.call_args.kwargs['headers'], {}, "a server of your own may need no key")
        self.assertNotIn('language', post.call_args.kwargs['data'])
        self.assertNotIn('prompt', post.call_args.kwargs['data'])

    def test_unreliable_segments_dropped(self):
        result, _post = self._transcribe(_reply(json_data={'text': 'Next item. Subscribe now', 'segments': [
            _segment('Next item.'),
            _segment('Subscribe now', no_speech_prob=0.9),
        ]}))
        self.assertEqual(result['text'], 'Next item.')

    def test_stock_phrases(self):
        unsure = _reply(json_data={'text': 'Thank you.', 'segments': [_segment('Thank you.', avg_logprob=-0.8)]})
        self.assertEqual(self._transcribe(unsure)[0]['text'], '', "Whisper's usual phrase on noise")
        confident = _reply(json_data={'text': 'Thank you.', 'segments': [_segment('Thank you.')]})
        self.assertEqual(self._transcribe(confident)[0]['text'], 'Thank you.', "clearly said")
        no_segments = _reply(json_data={'text': 'Thank you.'})
        self.assertEqual(self._transcribe(no_segments)[0]['text'], '')

    def _error(self, **post):
        with patch.object(cloud_whisper._session, 'post', **post), \
                self.assertRaises(cloud_whisper.CloudWhisperError) as caught:
            cloud_whisper.transcribe(b'RIFF audio')
        return caught.exception

    def test_errors(self):
        error = self._error(return_value=_reply(401, {'error': {'message': 'Invalid API Key'}}))
        self.assertIn('returned 401: Invalid API Key', str(error))
        self.assertEqual((error.kind, error.status), ('auth', 401))
        error = self._error(return_value=_reply(429, {'error': {'message': 'Rate limit reached'}}))
        self.assertEqual((error.kind, error.status), ('rate_limit', 429))
        self.assertEqual(self._error(return_value=_reply(500, None)).kind, 'error')
        self.assertEqual(self._error(side_effect=requests.ConnectionError('refused')).kind, 'unreachable')
        self.assertEqual(self._error(side_effect=requests.ReadTimeout('slow')).kind, 'timeout')
        with self.assertRaisesRegex(cloud_whisper.CloudWhisperError, '25 MB'):
            cloud_whisper.transcribe(b'0' * (cloud_whisper.MAX_FILE_BYTES + 1))
