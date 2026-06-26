# -*- coding: utf-8 -*-
"""
Slide Shield – Controllers
===========================
1. SlideShieldController  – Injects shield config into slide pages.
2. SlideShieldAPI          – JSON endpoint for SPA-style config fetch.
3. SlideShieldVideoController – Protected video streaming with signed URLs.
"""
import base64
import json
import logging
import os

from odoo import http, fields, _
from odoo.exceptions import AccessDenied
from odoo.http import Response, request
from odoo.addons.website_slides.controllers.main import WebsiteSlides

from ..utils.token_utils import (
    generate_video_token,
    get_session_hash,
    verify_video_token,
)

_logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_ip():
    """Extract the real client IP, respecting X-Forwarded-For."""
    forwarded = request.httprequest.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:45]
    return (request.httprequest.remote_addr or "")[:45]


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
        'category':         slide.slide_category,
        'slideId':          slide.id,
        # Video protection flag for the frontend
        'videoProtected':   bool(
            slide.slide_category == 'video'
            and slide.shield_video_file
        ),
    }
    return json.dumps(config)


def _check_enrollment(slide, user):
    """Verify the user is enrolled in the slide's course.

    :raises AccessDenied: If not enrolled.
    """
    if user._is_public():
        raise AccessDenied(_("Please sign in to watch this video."))

    enrollment = request.env["slide.channel.partner"].sudo().search(
        [
            ("channel_id", "=", slide.channel_id.id),
            ("partner_id", "=", user.partner_id.id),
        ],
        limit=1,
    )
    if not enrollment:
        raise AccessDenied(_("You are not enrolled in this course."))


# ── 1. Slide Shield Controller ────────────────────────────────────────────────

class SlideShieldController(WebsiteSlides):
    """
    Extend the main website_slides controller to inject Slide Shield
    configuration into every slide page's rendering context.
    """

    @http.route()
    def slide_view(self, slide, **kwargs):
        """
        Override slide_view to inject ``slide_shield_meta`` into the
        QWeb context *before* rendering.
        """
        response = super().slide_view(slide, **kwargs)

        if hasattr(response, 'qcontext'):
            try:
                meta = _build_shield_config(slide)
                response.qcontext['slide_shield_meta'] = meta or ''
            except Exception:
                response.qcontext.setdefault('slide_shield_meta', '')
        return response


# ── 2. Shield Config API ─────────────────────────────────────────────────────

class SlideShieldAPI(http.Controller):
    """
    JSON endpoint for SPA-style config fetch when the meta-tag approach
    doesn't fire (e.g. fullscreen navigation without page reload).
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
            'category':         slide.slide_category,
            'slideId':          slide.id,
            'videoProtected':   bool(
                slide.slide_category == 'video'
                and slide.shield_video_file
            ),
        }


# ── 3. Protected Video Controller ────────────────────────────────────────────

class SlideShieldVideoController(http.Controller):
    """
    Secure video delivery: signed URLs, enrollment checks, session
    validation, and HTTP Range support for seeking.
    """

    # ── Init: get a signed video URL ──────────────────────────────────────────

    @http.route(
        "/slide_shield/video/init/<int:slide_id>",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
        website=True,
    )
    def video_init(self, slide_id, **kwargs):
        """Return a signed video URL and watermark data."""
        user = request.env.user
        ip_address = _get_client_ip()
        user_agent = request.httprequest.headers.get("User-Agent", "")
        device_id = kwargs.get("device_id") or ""

        slide = request.env["slide.slide"].sudo().browse(slide_id)
        if not slide.exists():
            return {"error": "Slide not found."}

        # Must be a shield-protected video
        if not (slide.shield_active
                and slide.slide_category == "video"
                and slide.shield_video_file):
            return {"error": "This slide is not a protected video."}

        # Check enrollment
        try:
            _check_enrollment(slide, user)
        except AccessDenied as exc:
            self._log("enrollment_denied", slide=slide, user=user,
                      ip_address=ip_address, user_agent=user_agent,
                      extra_data={"reason": str(exc)})
            return {"error": str(exc)}

        # Create / refresh session
        try:
            session = request.env["shield.video.session"].sudo()\
                .start_or_touch(
                    slide=slide,
                    user=user,
                    device_id=device_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
        except AccessDenied as exc:
            self._log("access_denied", slide=slide, user=user,
                      ip_address=ip_address, user_agent=user_agent,
                      extra_data={"reason": str(exc)})
            return {"error": str(exc)}

        # Generate signed token
        session_hash = get_session_hash(request.env, request)
        ttl = slide.channel_id.shield_video_token_ttl or 300
        token = generate_video_token(
            request.env,
            user_id=user.id,
            slide_id=slide.id,
            session_hash=session_hash,
            ttl=ttl,
        )

        video_url = "/slide_shield/video/stream/%s?token=%s" % (
            slide.id, token
        )

        self._log("video_init", slide=slide, user=user, session=session,
                  ip_address=ip_address, user_agent=user_agent)

        return {
            "url": video_url,
            "token": token,
            "watermark": {
                "name": user.name or "",
                "email": user.email or user.login or "",
                "server_time": fields.Datetime.now().isoformat(),
            },
            "slide_name": slide.name,
        }

    # ── Stream: serve video bytes with Range support ──────────────────────────

    @http.route(
        "/slide_shield/video/stream/<int:slide_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        website=True,
    )
    def video_stream(self, slide_id, token=None, **kwargs):
        """Stream the video file with HTTP Range support."""
        user = request.env.user
        ip_address = _get_client_ip()
        user_agent = request.httprequest.headers.get("User-Agent", "")

        slide = request.env["slide.slide"].sudo().browse(slide_id)
        if not slide.exists():
            return self._error_response("Not found.", 404)

        # Verify token
        try:
            payload = verify_video_token(
                request.env, token, slide_id=slide_id
            )
        except ValueError as exc:
            self._log("token_invalid", slide=slide, user=user,
                      ip_address=ip_address, user_agent=user_agent,
                      extra_data={"reason": str(exc)})
            return self._error_response("Forbidden.", 403)

        # Verify token belongs to current user + session
        session_hash = get_session_hash(request.env, request)
        if int(payload["uid"]) != user.id:
            self._log("token_invalid", slide=slide, user=user,
                      ip_address=ip_address, user_agent=user_agent,
                      extra_data={"reason": "Token UID mismatch"})
            return self._error_response("Forbidden.", 403)
        if payload["sh"] != session_hash:
            self._log("token_invalid", slide=slide, user=user,
                      ip_address=ip_address, user_agent=user_agent,
                      extra_data={"reason": "Token session mismatch"})
            return self._error_response("Forbidden.", 403)

        # Verify enrollment is still valid
        try:
            _check_enrollment(slide, user)
        except AccessDenied:
            self._log("enrollment_denied", slide=slide, user=user,
                      ip_address=ip_address, user_agent=user_agent)
            return self._error_response("Forbidden.", 403)

        # Verify session is still active
        try:
            session = request.env["shield.video.session"].sudo()\
                .validate_current(
                    slide=slide, user=user,
                    session_hash=session_hash,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
        except AccessDenied as exc:
            self._log("session_invalid", slide=slide, user=user,
                      ip_address=ip_address, user_agent=user_agent,
                      extra_data={"reason": str(exc)})
            return self._error_response("Forbidden.", 403)

        # Get video data — try filestore first for performance
        video_data = self._get_video_bytes(slide)
        if video_data is None:
            return self._error_response("Video not found.", 404)

        self._log("video_stream", slide=slide, user=user, session=session,
                  ip_address=ip_address, user_agent=user_agent)

        # Determine content type
        content_type = "video/mp4"  # default

        # HTTP Range support for seeking
        total_size = len(video_data)
        range_header = request.httprequest.headers.get("Range")

        if range_header:
            return self._range_response(
                video_data, total_size, range_header, content_type
            )

        # Full response
        headers = self._security_headers(content_type)
        headers.append(("Content-Length", str(total_size)))
        headers.append(("Accept-Ranges", "bytes"))
        return Response(video_data, status=200, headers=headers)

    # ── Heartbeat: keep session alive ─────────────────────────────────────────

    @http.route(
        "/slide_shield/video/heartbeat",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
        website=True,
    )
    def video_heartbeat(self, **kwargs):
        """Session keepalive + position tracking."""
        slide_id = int(kwargs.get("slide_id") or 0)
        token = kwargs.get("token") or ""
        position = kwargs.get("position")

        user = request.env.user
        ip_address = _get_client_ip()
        user_agent = request.httprequest.headers.get("User-Agent", "")

        slide = request.env["slide.slide"].sudo().browse(slide_id)
        if not slide.exists():
            return {"success": False, "error": "Slide not found."}

        try:
            if token:
                verify_video_token(request.env, token, slide_id=slide_id)
            session = request.env["shield.video.session"].sudo()\
                .validate_current(
                    slide=slide, user=user,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
        except (AccessDenied, ValueError) as exc:
            return {"success": False, "error": str(exc)}

        self._log("heartbeat", slide=slide, user=user, session=session,
                  ip_address=ip_address, user_agent=user_agent,
                  extra_data={"position": position} if position else None)

        return {"success": True}

    # ── Complete: mark slide as done ──────────────────────────────────────────

    @http.route(
        "/slide_shield/video/complete",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
        website=True,
    )
    def video_complete(self, **kwargs):
        """Mark the slide as completed for the current user."""
        slide_id = int(kwargs.get("slide_id") or 0)
        token = kwargs.get("token") or ""

        user = request.env.user
        ip_address = _get_client_ip()
        user_agent = request.httprequest.headers.get("User-Agent", "")

        slide = request.env["slide.slide"].sudo().browse(slide_id)
        if not slide.exists():
            return {"success": False, "error": "Slide not found."}

        try:
            if token:
                verify_video_token(request.env, token, slide_id=slide_id)
            _check_enrollment(slide, user)
        except (AccessDenied, ValueError) as exc:
            return {"success": False, "error": str(exc)}

        # Mark completed via slide.slide.partner
        completion = request.env["slide.slide.partner"].sudo().search(
            [
                ("slide_id", "=", slide.id),
                ("partner_id", "=", user.partner_id.id),
            ],
            limit=1,
        )
        if completion:
            if not completion.completed:
                completion.write({"completed": True})
        else:
            request.env["slide.slide.partner"].sudo().create({
                "slide_id": slide.id,
                "partner_id": user.partner_id.id,
                "completed": True,
            })

        self._log("complete", slide=slide, user=user,
                  ip_address=ip_address, user_agent=user_agent)

        return {"success": True}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_video_bytes(self, slide):
        """Get the raw video bytes from the slide's shield_video_file.

        Tries to read from the filestore attachment for performance;
        falls back to base64 decoding.
        """
        if not slide.shield_video_file:
            return None

        # Try filestore path (avoids base64 decode of large files)
        try:
            attachment = request.env["ir.attachment"].sudo().search(
                [
                    ("res_model", "=", "slide.slide"),
                    ("res_id", "=", slide.id),
                    ("res_field", "=", "shield_video_file"),
                ],
                limit=1,
            )
            if attachment and attachment.store_fname:
                filestore_path = attachment._full_path(
                    attachment.store_fname
                )
                if os.path.isfile(filestore_path):
                    with open(filestore_path, "rb") as f:
                        return f.read()
        except Exception:
            _logger.debug(
                "Filestore read failed for slide %s, falling back to "
                "base64 decode.", slide.id, exc_info=True
            )

        # Fallback: base64 decode
        try:
            return base64.b64decode(slide.shield_video_file)
        except Exception:
            _logger.exception(
                "Failed to decode shield_video_file for slide %s", slide.id
            )
            return None

    def _range_response(self, data, total_size, range_header, content_type):
        """Handle HTTP Range requests for video seeking."""
        try:
            ranges = range_header.replace("bytes=", "").strip()
            start_str, end_str = ranges.split("-", 1)
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else total_size - 1
        except (ValueError, IndexError):
            return self._error_response("Invalid Range.", 416)

        if start >= total_size or end >= total_size or start > end:
            headers = self._security_headers(content_type)
            headers.append(
                ("Content-Range", "bytes */%s" % total_size)
            )
            return Response("", status=416, headers=headers)

        chunk = data[start:end + 1]
        headers = self._security_headers(content_type)
        headers.extend([
            ("Content-Range", "bytes %s-%s/%s" % (start, end, total_size)),
            ("Content-Length", str(len(chunk))),
            ("Accept-Ranges", "bytes"),
        ])
        return Response(chunk, status=206, headers=headers)

    def _security_headers(self, content_type):
        """Return security headers that prevent caching and misuse."""
        return [
            ("Content-Type", content_type),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Pragma", "no-cache"),
            ("Expires", "0"),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Disposition", "inline"),
            ("X-Frame-Options", "SAMEORIGIN"),
        ]

    def _error_response(self, message, status):
        """Return a plain-text error response."""
        return Response(
            message, status=status,
            headers=[("Content-Type", "text/plain")],
        )

    def _log(self, action, **kwargs):
        """Create an access log entry."""
        request.env["shield.video.access.log"].sudo().log_event(
            action=action, **kwargs
        )