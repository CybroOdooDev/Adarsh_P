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

{
    'name': 'Discuss Meeting Live Subtitles & AI Summaries',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Discuss',
    'summary': 'Live Subtitles (Closed Captions) and AI Meeting Summaries for Odoo Discuss calls',
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'depends': ['base', 'mail', 'bus', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_cron_data.xml',
        'data/discuss_meeting_summary_templates.xml',
        'views/discuss_meeting_summary_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'discuss_meeting_subtitles_ai/static/src/discuss/call/meeting_subtitles.scss',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/speech_service.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/meeting_subtitles.xml',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/meeting_subtitles.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/meeting_summary_dialog.xml',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/meeting_summary_dialog.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/meeting_patch.xml',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/meeting_patch.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/call_actions_patch.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/call/rtc_patch.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/upload/upload_recording_dialog.xml',
            'discuss_meeting_subtitles_ai/static/src/discuss/upload/upload_recording_dialog.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/upload/thread_actions_patch.js',
            'discuss_meeting_subtitles_ai/static/src/discuss/summary/summary_copy.js',
        ],
        'web.assets_tests': [
            'discuss_meeting_subtitles_ai/static/tests/tours/*.js',
        ],
    },
    'external_dependencies': {'python': ['requests']},
    'license': 'LGPL-3',
}
