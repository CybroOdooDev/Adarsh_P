# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SlideSlide(models.Model):
    """
    Extends slide.slide (Content) so individual slides can override the
    channel-level Slide Shield settings.
    """
    _inherit = 'slide.slide'

    shield_override = fields.Selection(
        selection=[
            ('inherit', 'Inherit from Course'),
            ('force_on', 'Always Protect'),
            ('force_off', 'Always Allow'),
        ],
        string='Content Protection',
        default='inherit',
        required=True,
        help='Controls whether Slide Shield is active for this specific slide.\n'
             '• Inherit from Course – uses the course-level setting.\n'
             '• Always Protect – forced on even if the course has it disabled.\n'
             '• Always Allow – exempts this slide (e.g. free preview content).',
    )

    vdocipher_video_id = fields.Char(
        string='VdoCipher Video ID',
        help='The VdoCipher video ID for DRM-protected playback. '
             'When set and shield is active, the VdoCipher player '
             'replaces the default video player.',
    )

    # Computed convenience flag consumed by the frontend template
    shield_active = fields.Boolean(
        string='Shield Active',
        compute='_compute_shield_active',
    )

    @api.depends('shield_override', 'channel_id.shield_enabled')
    def _compute_shield_active(self):
        for slide in self:
            if slide.shield_override == 'force_on':
                slide.shield_active = True
            elif slide.shield_override == 'force_off':
                slide.shield_active = False
            else:
                slide.shield_active = slide.channel_id.shield_enabled
