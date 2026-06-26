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

    # True when this video slide should use the protected player
    shield_video_protected = fields.Boolean(
        string='Video Protected',
        compute='_compute_shield_video_protected',
        store=True,
        help='Automatically True when the shield is active, slide category '
             'is video, and a protected video file has been uploaded.',
    )

    # Reverse link for session management
    shield_video_session_ids = fields.One2many(
        'shield.video.session',
        'slide_id',
        string='Video Sessions',
    )

    # Computed convenience flag consumed by the frontend template
    shield_active = fields.Boolean(
        string='Shield Active',
        compute='_compute_shield_active',
        store=True,
    )

    shield_video_file = fields.Binary(
        string='Protected Video File',
        attachment=True,
        help='Upload a protected video file. Only visible when category is video and content protection is enabled.',
    )
    shield_video_filename = fields.Char(string='Video Filename')

    @api.depends('shield_override', 'channel_id.shield_enabled')
    def _compute_shield_active(self):
        for slide in self:
            if slide.shield_override == 'force_on':
                slide.shield_active = True
            elif slide.shield_override == 'force_off':
                slide.shield_active = False
            else:
                slide.shield_active = slide.channel_id.shield_enabled

    @api.model_create_multi
    def create(self, vals_list):
        records = super(SlideSlide, self).create(vals_list)
        records._clear_invalid_shield_video()
        return records

    def write(self, vals):
        res = super(SlideSlide, self).write(vals)
        self._clear_invalid_shield_video()
        return res

    def _clear_invalid_shield_video(self):
        for slide in self:
            if not (slide.slide_category == 'video' and slide.shield_active):
                if slide.shield_video_file:
                    slide.sudo().write({
                        'shield_video_file': False,
                        'shield_video_filename': False,
                    })

    @api.depends('shield_active', 'slide_category', 'shield_video_file')
    def _compute_shield_video_protected(self):
        for slide in self:
            slide.shield_video_protected = (
                slide.shield_active
                and slide.slide_category == 'video'
                and bool(slide.shield_video_file)
            )

    @api.depends('shield_video_protected', 'shield_video_file')
    def _compute_embed_code(self):
        super()._compute_embed_code()
        from markupsafe import Markup
        for slide in self:
            if slide.shield_video_protected:
                embed_html = Markup(
                    '<div class="o_shield_video_wrapper o_shield_video_wrapper_std w-100 h-100" '
                    'data-slide-id="%s" data-shield-protected="1">'
                    '    <div class="o_shield_video_box h-100" style="position: relative;">'
                    '        <video class="o_shield_video w-100 h-100" '
                    '               controls playsinline preload="metadata" '
                    '               controlsList="nodownload noplaybackrate" '
                    '               disablePictureInPicture style="max-height: 100%%; object-fit: contain;">'
                    '        </video>'
                    '        <div class="o_shield_video_status d-flex align-items-center justify-content-center" style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); color: #fff; z-index: 10;">Loading protected video…</div>'
                    '    </div>'
                    '</div>'
                ) % slide.id
                slide.embed_code = embed_html
                slide.embed_code_external = embed_html

