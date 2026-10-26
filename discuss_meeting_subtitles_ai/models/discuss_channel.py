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

from datetime import datetime

from odoo import api, fields, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    meeting_summary_ids = fields.One2many(
        'discuss.meeting.summary',
        'channel_id',
        string='Meeting Summaries',
        help='Summaries and notes generated from meetings in this channel',
    )
    meeting_summary_count = fields.Integer(
        string='Summary Count',
        compute='_compute_meeting_summary_count',
    )

    @api.depends('meeting_summary_ids')
    def _compute_meeting_summary_count(self):
        for channel in self:
            channel.meeting_summary_count = len(channel.meeting_summary_ids)

    def _broadcast_meeting_subtitle(self, partner_name, text, is_final=False, partner_id=None, member_id=None,
                                    seq=None):
        """Broadcasts real-time meeting subtitles to all active members of this channel.

        Private (not callable over RPC): only the transcription endpoint may caption, with the
        speaker identity it checked itself.

        ``member_id`` tells speakers apart even when they share a partner (all guests use the
        public partner). ``seq`` is the speaker's utterance number: receivers use it to ignore a
        partial caption that arrives after the final caption of the same utterance.
        """
        self.ensure_one()
        payload = {
            'channel_id': self.id,
            'partner_id': partner_id or self.env.user.partner_id.id,
            'partner_name': partner_name or self.env.user.partner_id.name or "Participant",
            'text': text,
            'is_final': is_final,
            'member_id': member_id,
            'seq': seq,
            'time': datetime.now().strftime("%H:%M:%S"),
        }
        self._bus_send("discuss.channel/meeting_subtitle", payload)
        return True

    def _get_meeting_ai_state(self):
        """What the running call needs from every participant's microphone.

        ``transcribe``: the call is being transcribed into its meeting summary (anyone in the
        call turns it on for everyone). ``subtitles``: at least one participant watches
        Subtitle(CC), so everyone's speech is captioned.
        """
        self.ensure_one()
        meeting = self.env['discuss.meeting.summary'].sudo()._get_live_meeting(self)
        return {
            'channel_id': self.id,
            'transcribe': bool(meeting.transcribe_enabled),
            'subtitles': any(self.sudo().rtc_session_ids.mapped('meeting_subtitles_on')),
        }

    def _broadcast_meeting_ai_state(self):
        for channel in self:
            channel._bus_send("discuss.channel/meeting_ai_state", channel._get_meeting_ai_state())

    def action_view_meeting_summaries(self):
        self.ensure_one()
        action = self.env.ref('discuss_meeting_subtitles_ai.action_discuss_meeting_summary').read()[0]
        action['domain'] = [('channel_id', '=', self.id)]
        action['context'] = {'default_channel_id': self.id}
        return action
