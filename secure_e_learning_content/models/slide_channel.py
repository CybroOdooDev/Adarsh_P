# -*- coding: utf-8 -*-
from odoo import models, fields


class SlideChannel(models.Model):
    """
    Extends slide.channel (Course) with per-course content-protection settings.
    These act as the channel-level defaults; individual slides can override them.
    """
    _inherit = 'slide.channel'

    # ── Master switch ──────────────────────────────────────────────────────────
    shield_enabled = fields.Boolean(
        string='Enable Content Protection',
        default=False,
        help='Activate Slide Shield for every content item in this course. '
             'Individual slides can still be exempted below.',
    )

    # ── Watermark ──────────────────────────────────────────────────────────────
    shield_watermark_enabled = fields.Boolean(
        string='Show User Watermark',
        default=True,
        help='Overlay a semi-transparent watermark carrying the viewer\'s name '
             'and e-mail so that any captured frame can be traced back.',
    )
    shield_watermark_opacity = fields.Float(
        string='Watermark Opacity',
        default=0.08,
        digits=(4, 2),
        help='Canvas watermark opacity (0.01 – 0.30).  '
             'Lower values are less distracting but easier to crop out.',
    )

    # ── Keyboard / capture guards ──────────────────────────────────────────────
    shield_block_keyboard = fields.Boolean(
        string='Block Capture Shortcuts',
        default=True,
        help='Intercept Print Screen, Win+Shift+S, Cmd+Shift+3/4 and similar '
             'OS-level screenshot key combinations.',
    )
    shield_block_devtools = fields.Boolean(
        string='Blur on DevTools',
        default=True,
        help='Detect when browser DevTools are open and blur the content area.',
    )

    # ── Visibility / focus guards ──────────────────────────────────────────────
    shield_blur_on_focus_loss = fields.Boolean(
        string='Blur When Tab Loses Focus',
        default=True,
        help='Blur slide content when the viewer switches away from the browser '
             'tab (common during screen-recording workflows).',
    )

    # ── Right-click / drag guard ───────────────────────────────────────────────
    shield_block_context_menu = fields.Boolean(
        string='Disable Right-Click on Content',
        default=True,
        help='Suppress the browser context-menu inside the content player so '
             '"Save image as…" / "Save video as…" options are unavailable.',
    )

    # ── Video protection settings ──────────────────────────────────────────────
    shield_video_token_ttl = fields.Integer(
        string='Video Token Lifetime (seconds)',
        default=300,
        help='How long a signed video URL remains valid. Shorter values '
             'are more secure but may cause issues on slow connections.',
    )
    shield_video_one_session = fields.Boolean(
        string='One Active Session Per User',
        default=False,
        help='When enabled, starting a new browser session blocks previous '
             'sessions. Prevents link sharing between browsers.',
    )
    shield_video_one_device = fields.Boolean(
        string='One Active Device Per User',
        default=False,
        help='When enabled, only one device fingerprint can have an active '
             'session at a time. Useful for strict anti-sharing policies.',
    )

