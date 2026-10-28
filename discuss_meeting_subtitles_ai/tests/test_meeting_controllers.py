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
from unittest.mock import patch

from odoo import http
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.discuss_meeting_subtitles_ai.tools import cloud_whisper, grok_stt, stt_client

WAV = b'RIFF' + b'\0' * 4000  # long enough to be transcribed; the engine is mocked


@tagged('post_install', '-at_install')
class TestMeetingRoutes(HttpCase):
    """The routes the browser calls during a meeting, as an internal user and as a guest."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = new_test_user(cls.env, login='route_alice', name='Alice Martin', groups='base.group_user')
        cls.channel = cls.env['discuss.channel'].create({'name': 'Ops Review', 'channel_type': 'group'})
        cls.alice_member = cls.channel.channel_member_ids.filtered(lambda m: m.partner_id == cls.alice.partner_id) \
            or cls.env['discuss.channel.member'].create({'channel_id': cls.channel.id,
                                                         'partner_id': cls.alice.partner_id.id})
        cls.guest = cls.env['mail.guest'].create({'name': 'Visitor'})
        cls.guest_member = cls.env['discuss.channel.member'].create({'channel_id': cls.channel.id,
                                                                     'guest_id': cls.guest.id})
        # joined one at a time, as in a real call: the first session opens the call
        for member in (cls.alice_member, cls.guest_member):
            cls.env['discuss.channel.rtc.session'].create({'channel_member_id': member.id})
        cls.env['ir.config_parameter'].sudo().set_param('discuss_meeting_subtitles_ai.stt_engine', 'whisper')
        cls.meeting = cls.env['discuss.meeting.summary']._get_live_meeting(cls.channel)

    def setUp(self):
        super().setUp()
        # no speech worker in tests: loading a model in the background is skipped
        patcher = patch.object(stt_client, 'warm_up')
        patcher.start()
        self.addCleanup(patcher.stop)

    def url_open(self, *args, **kwargs):
        # the server sees what the test wrote, and the test then reads what the server wrote
        self.env.flush_all()
        response = super().url_open(*args, **kwargs)
        self.env.invalidate_all()
        return response

    def _as_guest(self):
        self.authenticate(None, None)
        self.opener.cookies.set('dgid', self.guest._format_auth_cookie())

    def _caption(self, text='We will send the report on Friday.', **data):
        reply = {'text': text, 'language': 'en', 'language_probability': 1.0,
                 'queue_seconds': 0.0, 'stt_seconds': 0.1}
        with patch.object(stt_client, 'transcribe_with_info', return_value=reply) as transcribe:
            response = self.url_open('/discuss/meeting/transcribe_chunk', data={
                'channel_id': self.channel.id, 'csrf_token': http.Request.csrf_token(self), **data,
            }, files={'file': ('audio.wav', WAV, 'audio/wav')})
        return response.json(), transcribe

    def test_only_internal_users_switch_transcription(self):
        self._as_guest()
        result = self.make_jsonrpc_request('/discuss/meeting/set_transcribe',
                                           {'channel_id': self.channel.id, 'enabled': True})
        self.assertEqual(result, {'error': 'not_allowed'})
        self.assertFalse(self.meeting.transcribe_enabled)

        self.authenticate('route_alice', 'route_alice')
        result = self.make_jsonrpc_request('/discuss/meeting/set_transcribe',
                                           {'channel_id': self.channel.id, 'enabled': True})
        self.assertEqual(result, {'channel_id': self.channel.id, 'transcribe': True, 'subtitles': False})
        self.assertTrue(self.meeting.transcribe_enabled)

        self._as_guest()
        state = self.make_jsonrpc_request('/discuss/meeting/state', {'channel_id': self.channel.id})
        self.assertTrue(state['transcribe'], "guests still see that the call is transcribed")

    def test_not_in_call(self):
        other = self.env['discuss.channel'].create({'name': 'Elsewhere', 'channel_type': 'group'})
        self.authenticate('route_alice', 'route_alice')
        for route in ('/discuss/meeting/state', '/discuss/meeting/transcript'):
            self.assertEqual(self.make_jsonrpc_request(route, {'channel_id': other.id}), {'error': 'not_in_call'})

    def test_caption_idle_without_subtitles_or_transcription(self):
        self.authenticate('route_alice', 'route_alice')
        result, transcribe = self._caption()
        self.assertEqual(result['status'], 'idle')
        transcribe.assert_not_called()

    def test_caption_recorded_while_transcribing(self):
        self.authenticate('route_alice', 'route_alice')
        self.make_jsonrpc_request('/discuss/meeting/set_transcribe', {'channel_id': self.channel.id, 'enabled': True})
        result, transcribe = self._caption()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['text'], 'We will send the report on Friday.')
        self.assertEqual(transcribe.call_args.args[1], 'whisper')
        self.assertEqual(self.meeting.transcript_line_ids.text, 'We will send the report on Friday.')
        self.assertEqual(self.meeting.transcript_line_ids.speaker_name, 'Alice Martin')

        transcript = self.make_jsonrpc_request('/discuss/meeting/transcript', {'channel_id': self.channel.id})
        self.assertTrue(transcript['transcribe'])
        self.assertEqual([line['text'] for line in transcript['lines']], ['We will send the report on Friday.'])

        summary = self.make_jsonrpc_request('/discuss/meeting/summarize', {'channel_id': self.channel.id})
        self.assertEqual(summary['status'], 'success')
        self.assertIn('Will send the report on Friday.', summary['action_items'])

        posted = self.make_jsonrpc_request('/discuss/meeting/post_summary', {'summary_id': summary['summary_id']})
        self.assertEqual(posted, {'status': 'posted'})
        again = self.make_jsonrpc_request('/discuss/meeting/post_summary', {'summary_id': summary['summary_id']})
        self.assertIn('error', again)

    def test_guest_captions_while_subtitles_are_on(self):
        self._as_guest()
        state = self.make_jsonrpc_request('/discuss/meeting/set_subtitles',
                                          {'channel_id': self.channel.id, 'enabled': True})
        self.assertTrue(state['subtitles'])
        result, _transcribe = self._caption('Hello everyone.')
        self.assertEqual((result['status'], result['text']), ('ok', 'Hello everyone.'))
        self.assertFalse(self.meeting.transcript_line_ids, "subtitles alone record nothing")

    def test_caption_uses_speech_workers_setting(self):
        self.authenticate('route_alice', 'route_alice')
        self.make_jsonrpc_request('/discuss/meeting/set_subtitles', {'channel_id': self.channel.id, 'enabled': True})
        set_param = self.env['ir.config_parameter'].sudo().set_param
        # one by default; anything invalid falls back to one, too many is capped
        for value, workers in ((False, 1), ('2', 2), ('9', 4), ('0', 1), ('many', 1)):
            set_param('discuss_meeting_subtitles_ai.stt_workers', value)
            _result, transcribe = self._caption()
            self.assertEqual(transcribe.call_args.kwargs['workers'], workers, value)

    def test_short_chunk(self):
        self.authenticate('route_alice', 'route_alice')
        self.make_jsonrpc_request('/discuss/meeting/set_subtitles', {'channel_id': self.channel.id, 'enabled': True})
        with patch.object(stt_client, 'transcribe_with_info') as transcribe:
            response = self.url_open('/discuss/meeting/transcribe_chunk', data={
                'channel_id': self.channel.id, 'csrf_token': http.Request.csrf_token(self),
            }, files={'file': ('audio.wav', b'RIFF', 'audio/wav')})
        self.assertEqual(response.json(), {'status': 'empty_chunk'})
        transcribe.assert_not_called()

    def test_caption_with_cloud_whisper(self):
        self.authenticate('route_alice', 'route_alice')
        self.make_jsonrpc_request('/discuss/meeting/set_subtitles', {'channel_id': self.channel.id, 'enabled': True})
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('discuss_meeting_subtitles_ai.stt_engine', 'cloud_whisper')
        set_param('discuss_meeting_subtitles_ai.cloud_whisper_url', 'https://api.openai.com/v1')
        set_param('discuss_meeting_subtitles_ai.cloud_whisper_model', 'whisper-1')
        set_param('discuss_meeting_subtitles_ai.cloud_whisper_api_key', 'sk-test')
        cloud = patch.object(cloud_whisper, 'transcribe', return_value={'text': 'Ship it today.', 'language': 'en'})
        with cloud as transcribe:
            result, local = self._caption()
        self.assertEqual((result['status'], result['text']), ('ok', 'Ship it today.'))
        self.assertNotIn('caption_error', result)
        local.assert_not_called()
        self.assertEqual(transcribe.call_args.args[1], 'sk-test')
        self.assertEqual((transcribe.call_args.kwargs['url'], transcribe.call_args.kwargs['model']),
                         ('https://api.openai.com/v1', 'whisper-1'))
        self.assertIn('Alice Martin', transcribe.call_args.kwargs['keywords'])

        # a lost caption tells the speaker why
        for error, reason in (
            (cloud_whisper.CloudWhisperError('429', 'rate_limit', 429), "reached this account's request limit"),
            (cloud_whisper.CloudWhisperError('401', 'auth', 401), 'rejected the API key'),
            (cloud_whisper.CloudWhisperError('slow', 'timeout'), 'did not answer within 15 seconds'),
            (cloud_whisper.CloudWhisperError('down', 'unreachable'), 'could not be reached'),
            (cloud_whisper.CloudWhisperError('502', 'error', 502), 'returned an error (HTTP 502)'),
        ):
            with patch.object(cloud_whisper, 'transcribe', side_effect=error):
                result, _local = self._caption()
            self.assertEqual((result['status'], result['text']), ('ok', ''), "a failed caption is skipped")
            self.assertIn('api.openai.com', result['caption_error'])
            self.assertIn(reason, result['caption_error'])

    def test_caption_with_grok_errors(self):
        self.authenticate('route_alice', 'route_alice')
        self.make_jsonrpc_request('/discuss/meeting/set_subtitles', {'channel_id': self.channel.id, 'enabled': True})
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('discuss_meeting_subtitles_ai.stt_engine', 'grok')
        set_param('discuss_meeting_subtitles_ai.stt_openai_fallback', False)
        set_param('discuss_meeting_subtitles_ai.xai_api_key', '')
        with patch.object(grok_stt, 'transcribe') as transcribe:
            result, _local = self._caption()
        transcribe.assert_not_called()
        self.assertIn('no xAI API key is set', result['caption_error'])

        set_param('discuss_meeting_subtitles_ai.xai_api_key', 'xai-test')
        with patch.object(grok_stt, 'transcribe', return_value={'text': 'Ship it today.', 'language': 'en'}):
            result, local = self._caption()
        self.assertEqual(result['text'], 'Ship it today.')
        self.assertNotIn('caption_error', result)
        local.assert_not_called()
        for error, reason in (
            (grok_stt.GrokSttError('429', 'rate_limit', 429), "reached this account's request limit"),
            (grok_stt.GrokSttError('401', 'auth', 401), 'rejected the API key'),
            (grok_stt.GrokSttError('slow', 'timeout'), 'did not answer within 15 seconds'),
            (grok_stt.GrokSttError('down', 'unreachable'), 'could not be reached'),
            (grok_stt.GrokSttError('500', 'error', 500), 'returned an error (HTTP 500)'),
            (grok_stt.GrokSttError('unreadable'), 'could not transcribe it'),
        ):
            with patch.object(grok_stt, 'transcribe', side_effect=error):
                result, _local = self._caption()
            self.assertEqual((result['status'], result['text']), ('ok', ''), "a failed caption is skipped")
            self.assertIn('xAI', result['caption_error'])
            self.assertIn(reason, result['caption_error'])

    def test_caption_engine_not_installed(self):
        self.authenticate('route_alice', 'route_alice')
        self.make_jsonrpc_request('/discuss/meeting/set_subtitles', {'channel_id': self.channel.id, 'enabled': True})
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('discuss_meeting_subtitles_ai.stt_engine', 'whistle')
        set_param('discuss_meeting_subtitles_ai.stt_openai_fallback', False)

        def transcribe(_audio, engine, *args, **kwargs):
            raise stt_client.SttWorkerUnavailable("not_installed: No module named %s" % engine)

        def caption():
            with patch.object(stt_client, 'transcribe_with_info', side_effect=transcribe):
                return self.url_open('/discuss/meeting/transcribe_chunk', data={
                    'channel_id': self.channel.id, 'csrf_token': http.Request.csrf_token(self),
                }, files={'file': ('audio.wav', WAV, 'audio/wav')}).json()

        # the speaker is told what to install
        result = caption()
        self.assertEqual(result['text'], '')
        self.assertIn('Whistle speech engine is not installed', result['caption_error'])
        self.assertIn('pip install cactus-needle', result['caption_error'])

    def test_settings_route(self):
        self._as_guest()
        settings = self.make_jsonrpc_request('/discuss/meeting/get_settings', {})
        self.assertEqual(settings['language'], 'en-US')

    def test_summarize_without_transcript(self):
        self.authenticate('route_alice', 'route_alice')
        result = self.make_jsonrpc_request('/discuss/meeting/summarize', {'channel_id': self.channel.id})
        self.assertIn('Nothing has been transcribed', result['error'])

    def test_upload_recording(self):
        self.authenticate('route_alice', 'route_alice')
        response = self.url_open('/discuss/meeting/upload_recording', data={
            'channel_id': self.channel.id, 'title': 'Board meeting', 'csrf_token': http.Request.csrf_token(self),
        }, files={'file': ('board.mp3', b'ID3 fake audio', 'audio/mpeg')})
        result = response.json()
        self.assertEqual(result['status'], 'success')
        meeting = self.env['discuss.meeting.summary'].browse(result['summary_id'])
        self.assertEqual((meeting.name, meeting.state), ('Board meeting', 'processing'))
        self.assertTrue(meeting.post_when_done)
        self.assertEqual(meeting.requested_by_id, self.alice)

        response = self.url_open('/discuss/meeting/upload_recording', data={
            'channel_id': self.channel.id, 'csrf_token': http.Request.csrf_token(self),
        })
        self.assertEqual(response.json()['status'], 'error')

    def test_generate_summary_link(self):
        meeting = self.env['discuss.meeting.summary'].create({
            'name': 'Finished call', 'channel_id': self.channel.id, 'state': 'draft',
            'raw_transcript': 'Alice Martin: We agreed on March.',
        })
        self.authenticate('route_alice', 'route_alice')
        page = self.url_open(f'/discuss/meeting/generate_summary_redirect?summary_id={meeting.id}')
        self.assertIn('csrf_token', page.text, "the link only asks for confirmation")
        self.assertEqual(meeting.state, 'draft')
        self.url_open('/discuss/meeting/generate_summary_redirect', data={
            'summary_id': meeting.id, 'csrf_token': http.Request.csrf_token(self),
        }, allow_redirects=False)
        self.assertEqual(meeting.state, 'posted')
        self.assertIn('We agreed on March.', meeting.decisions)
