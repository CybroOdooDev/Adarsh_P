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

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    meeting_stt_engine = fields.Selection(
        [
            ('whisper', 'Whisper (most accurate, 99 languages)'),
            ('whistle', 'Whistle (tiny and fast; English, German, French, Spanish, Italian, Dutch, Polish only)'),
            ('auto', 'Auto (Whistle first, Whisper if it hears nothing or is unsure)'),
            ('grok', 'Grok STT (xAI cloud: most accurate, no server load)'),
        ],
        string='Speech-to-Text Engine',
        default='whisper',
        config_parameter='discuss_meeting_subtitles_ai.stt_engine',
    )
    meeting_xai_api_key = fields.Char(
        string='xAI API Key',
        config_parameter='discuss_meeting_subtitles_ai.xai_api_key',
        help='Key of the xAI account used by Grok STT. Meeting audio is sent to xAI to be transcribed.',
    )
    meeting_subtitles_keywords = fields.Char(
        string='Subtitle Keywords',
        config_parameter='discuss_meeting_subtitles_ai.keywords',
        help='Comma-separated names and terms to recognize correctly (e.g. Odoo, Cybrosys). '
             'Participant names are added automatically.',
    )
    meeting_partial_captions = fields.Boolean(
        string='Live Partial Captions',
        config_parameter='discuss_meeting_subtitles_ai.partial_captions',
        help='Show words while the speaker is still talking, refined into the final caption when they pause. '
             'Transcribes each utterance several times, so it needs noticeably more server CPU; partial '
             'captions are skipped whenever the speech engine is busy, so they never delay final captions. '
             'Not used with Grok STT, where each one would be a billed request.',
    )
    meeting_stt_openai_fallback = fields.Boolean(
        string='OpenAI Speech Fallback',
        config_parameter='discuss_meeting_subtitles_ai.stt_openai_fallback',
        help='When the local speech engine fails on a live caption or an uploaded recording (error, busy, '
             'not installed), send that audio to the OpenAI Whisper API instead, with the OpenAI API Key. '
             'Meeting audio then leaves this server.',
    )
    meeting_save_debug_audio = fields.Boolean(
        string='Save Subtitle Debug Audio',
        config_parameter='discuss_meeting_subtitles_ai.save_debug_audio',
        help='Keep the last 50 received utterances as WAV files in the server temp folder (odoo_subtitle_debug) '
             'to diagnose recognition problems. Disable in production: it stores meeting audio.',
    )
    meeting_whisper_model = fields.Selection(
        [
            ('tiny', 'Tiny (fastest, least accurate)'),
            ('base', 'Base (fast, basic accuracy)'),
            ('small', 'Small (recommended balance)'),
            ('medium', 'Medium (accurate, needs a strong CPU/GPU)'),
            ('distil-large-v3', 'Distil Large v3 (very accurate, English only)'),
            ('large-v3', 'Large v3 (best accuracy, needs a GPU)'),
        ],
        string='Whisper Model',
        default='small',
        config_parameter='discuss_meeting_subtitles_ai.whisper_model',
        help='Local speech-to-text model. Bigger models are far more accurate but slower. Downloaded on first use.',
    )
    meeting_ai_provider = fields.Selection(
        [
            ('internal', 'Built-in Smart Summarizer (No API Key Required)'),
            ('openai', 'OpenAI (ChatGPT)'),
            ('ollama', 'Ollama / Local Engine (Needle / Llama 3)'),
        ],
        string='Meeting AI Provider',
        default='internal',
        config_parameter='discuss_meeting_subtitles_ai.ai_provider',
        help='Engine used to summarize meeting transcripts',
    )
    meeting_openai_api_key = fields.Char(
        string='OpenAI API Key',
        config_parameter='discuss_meeting_subtitles_ai.openai_api_key',
    )
    meeting_openai_model = fields.Char(
        string='OpenAI Model',
        default='gpt-4o-mini',
        config_parameter='discuss_meeting_subtitles_ai.openai_model',
    )
    meeting_ollama_endpoint = fields.Char(
        string='Ollama Endpoint URL',
        default='http://localhost:11434',
        config_parameter='discuss_meeting_subtitles_ai.ollama_endpoint',
    )
    meeting_ollama_model = fields.Char(
        string='Ollama Model',
        default='llama3',
        config_parameter='discuss_meeting_subtitles_ai.ollama_model',
    )
    meeting_main_language = fields.Selection(
        lambda self: [option for option in self._fields['meeting_subtitles_default_language'].selection if option[0] != 'auto'],
        string='Main Meeting Language',
        default='en-US',
        config_parameter='discuss_meeting_subtitles_ai.main_language',
        help='With auto-detect, this language is assumed whenever the detection is unsure, so short or '
             'accented phrases are not mistaken for another language. Other languages are still recognized '
             'when clearly spoken.',
    )
    meeting_subtitles_default_language = fields.Selection(
        [
            ('auto', 'Auto-Detect (less accurate on short phrases)'),
            ('en-US', 'English (US)'),
            ('en-GB', 'English (UK)'),
            ('es-ES', 'Spanish'),
            ('fr-FR', 'French'),
            ('de-DE', 'German'),
            ('it-IT', 'Italian'),
            ('nl-NL', 'Dutch'),
            ('pl-PL', 'Polish'),
            ('pt-PT', 'Portuguese'),
            ('hi-IN', 'Hindi'),
            ('ml-IN', 'Malayalam'),
            ('ta-IN', 'Tamil'),
            ('ar-SA', 'Arabic'),
        ],
        string='Subtitles Speech Language',
        default='en-US',
        config_parameter='discuss_meeting_subtitles_ai.subtitles_language',
    )
