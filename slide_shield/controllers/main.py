# -*- coding: utf-8 -*-
"""
Slide Shield – Controller
=========================
Extends the website_slides controller to inject shield configuration into
the QWeb rendering context for slide pages.

The meta-tag approach embeds a JSON config blob in <head> which the
frontend JS reads to activate the appropriate guards.

CHANGE: added 'category', 'vdocipherVideoId' and 'slideId' to the config
dict so the *non-fullscreen* lesson page can also detect a VdoCipher-
protected video slide and swap in the DRM player (previously only the
Fullscreen widget had this information, via its own slide-list payload).
Adjust the `slide.vdocipher_video_id` field name below if yours differs.
"""
import json
import requests
from odoo import http
from odoo.http import request
from odoo.addons.website_slides.controllers.main import WebsiteSlides
VDO_API_SECRET = "nShroJhj6pBXecRy97quzaxUMZAImFbE4UdD7mAnD0rm0tQfcYQx4qir4CRmHHTK"


def _build_shield_config(slide):
    """
    Build the shield config dict for a given slide record.
    Returns the JSON-serialised config string, or None if protection
    is not active.
    """
    slide = slide.sudo()
    channel = slide.channel_id

    if slide.shield_override == 'force_on':
        active = True
    elif slide.shield_override == 'force_off':
        active = False
    else:
        active = channel.shield_enabled

    if not active:
        return None

    user = request.env.user
    config = {
        'active':           True,
        'watermark':        channel.shield_watermark_enabled,
        'opacity':          float(channel.shield_watermark_opacity),
        'blockKeyboard':    channel.shield_block_keyboard,
        'blockDevtools':    channel.shield_block_devtools,
        'blurOnFocusLoss':  channel.shield_blur_on_focus_loss,
        'blockContextMenu': channel.shield_block_context_menu,
        'userName':         user.name or '',
        'userEmail':        user.email or '',
        # added for the non-fullscreen VdoCipher swap:
        'category':         slide.slide_category,
        'vdocipherVideoId': slide.vdocipher_video_id or False,
        'slideId':          slide.id,
    }
    return json.dumps(config)


class SlideShieldController(WebsiteSlides):
    """
    Extend the main website_slides controller to inject Slide Shield
    configuration into every slide page's rendering context.
    """

    @http.route()
    def slide_view(self, slide, **kwargs):
        """
        Override slide_view to inject ``slide_shield_meta`` into the
        QWeb context *before* rendering.  The parent does the heavy
        lifting; we simply intercept the response to enrich the
        template values.
        """
        # Let the parent build the full response
        response = super().slide_view(slide, **kwargs)

        # Inject shield config into qcontext so the template can emit
        # the <meta> tag.  response.qcontext is available on QWeb
        # responses returned by request.render().
        if hasattr(response, 'qcontext'):
            try:
                meta = _build_shield_config(slide)
                response.qcontext['slide_shield_meta'] = meta or ''
            except Exception:
                # Never break the page; silently skip
                response.qcontext.setdefault('slide_shield_meta', '')
        return response


class SlideShieldAPI(http.Controller):
    """
    Tiny JSON endpoint the frontend JS can call if the meta-tag approach
    doesn't fire (e.g. SPA navigation to a new slide without a full page
    reload).  Returns the shield config for a given slide ID.
    """

    @http.route(
        '/slide_shield/config/<int:slide_id>',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def shield_config(self, slide_id, **kw):
        slide = request.env['slide.slide'].sudo().browse(slide_id)
        if not slide.exists():
            return {'active': False}

        channel = slide.channel_id

        if slide.shield_override == 'force_on':
            active = True
        elif slide.shield_override == 'force_off':
            active = False
        else:
            active = channel.shield_enabled

        user = request.env.user
        return {
            'active':           active,
            'watermark':        channel.shield_watermark_enabled,
            'opacity':          float(channel.shield_watermark_opacity),
            'blockKeyboard':    channel.shield_block_keyboard,
            'blockDevtools':    channel.shield_block_devtools,
            'blurOnFocusLoss':  channel.shield_blur_on_focus_loss,
            'blockContextMenu': channel.shield_block_context_menu,
            'userName':         user.name or '',
            'userEmail':        user.email or '',
            # added for the non-fullscreen VdoCipher swap:
            'category':         slide.slide_category,
            'vdocipherVideoId': slide.vdocipher_video_id or False,
            'slideId':          slide.id,
        }


class VdoCipherController(http.Controller):

    @http.route('/vdocipher/get_video/<string:video_id>',
                type='json',
                auth='user')
    def get_video(self, video_id):

        # Verify enrollment here
        # if not enrolled:
        #     return {"error": "Unauthorized"}

        payload = {
            "ttl": 300
        }

        headers = {
            "Authorization": "Apisecret " + VDO_API_SECRET
        }

        response = requests.post(
            f"https://dev.vdocipher.com/api/videos/{video_id}/otp",
            json=payload,
            headers=headers
        )
        print(response.json())
        return response.json()