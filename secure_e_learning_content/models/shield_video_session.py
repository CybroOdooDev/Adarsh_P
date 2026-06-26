# -*- coding: utf-8 -*-
"""
Slide Shield – Video Playback Session
======================================
Tracks active video playback sessions.  Each row represents one
browser session watching one protected video slide.  Sessions are
used to enforce single-device / single-session policies and to bind
signed tokens to a specific browser.
"""
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessDenied

from ..utils.token_utils import hash_value


class ShieldVideoSession(models.Model):
    _name = "shield.video.session"
    _description = "Protected Video Playback Session"
    _order = "last_seen desc"
    _rec_name = "display_name"

    display_name = fields.Char(
        compute="_compute_display_name", store=True
    )
    user_id = fields.Many2one(
        "res.users", required=True, index=True, ondelete="cascade"
    )
    channel_id = fields.Many2one(
        "slide.channel", required=True, index=True, ondelete="cascade"
    )
    slide_id = fields.Many2one(
        "slide.slide", required=True, index=True, ondelete="cascade"
    )
    session_hash = fields.Char(
        required=True, index=True, copy=False,
        help="HMAC of the browser session ID.  Binds the token to this browser.",
    )
    device_hash = fields.Char(
        index=True, copy=False,
        help="HMAC of the device fingerprint / user-agent.",
    )
    ip_address = fields.Char(size=45)
    user_agent = fields.Char(size=512)
    state = fields.Selection(
        [
            ("active", "Active"),
            ("blocked", "Blocked"),
            ("expired", "Expired"),
            ("closed", "Closed"),
        ],
        default="active",
        required=True,
        index=True,
    )
    started_at = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    last_seen = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    expires_at = fields.Datetime(index=True)
    request_count = fields.Integer(default=0)
    blocked_reason = fields.Char()

    _shield_session_unique = models.Constraint(
        "UNIQUE(slide_id, user_id, session_hash)",
        "One session row per user per slide per browser session.",
    )

    @api.depends("user_id", "slide_id", "state")
    def _compute_display_name(self):
        for session in self:
            session.display_name = "%s – %s (%s)" % (
                session.user_id.name or _("User"),
                session.slide_id.name or _("Slide"),
                session.state,
            )

    @api.model
    def start_or_touch(self, slide, user, device_id=None,
                       ip_address=None, user_agent=None):
        """Create a new session or refresh an existing one.

        :returns: The session record (sudo).
        """
        from odoo.http import request as http_request

        session_hash = hash_value(
            self.env, http_request.session.sid or "", "session"
        )
        device_hash = hash_value(
            self.env, device_id or user_agent or "", "device"
        )

        # Configurable TTL
        ttl_hours = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "slide_shield.session_ttl_hours", "8"
            ) or 8
        )
        expires_at = fields.Datetime.now() + timedelta(hours=ttl_hours)

        # Enforce session policy before creating / refreshing
        self._enforce_policy(
            slide, user, session_hash, device_hash,
            ip_address, user_agent
        )

        session = self.sudo().search(
            [
                ("slide_id", "=", slide.id),
                ("user_id", "=", user.id),
                ("session_hash", "=", session_hash),
            ],
            limit=1,
        )
        vals = {
            "channel_id": slide.channel_id.id,
            "device_hash": device_hash,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:512],
            "last_seen": fields.Datetime.now(),
            "expires_at": expires_at,
            "state": "active",
            "blocked_reason": False,
        }
        if session:
            session.write(vals)
        else:
            vals.update({
                "slide_id": slide.id,
                "user_id": user.id,
                "session_hash": session_hash,
                "started_at": fields.Datetime.now(),
            })
            session = self.sudo().create(vals)
        return session

    @api.model
    def validate_current(self, slide, user, session_hash=None,
                         ip_address=None, user_agent=None):
        """Validate that the current request has an active session.

        :raises AccessDenied: If the session is missing, expired, or blocked.
        :returns: The session record (sudo).
        """
        if not session_hash:
            from odoo.http import request as http_request
            session_hash = hash_value(
                self.env, http_request.session.sid or "", "session"
            )

        session = self.sudo().search(
            [
                ("slide_id", "=", slide.id),
                ("user_id", "=", user.id),
                ("session_hash", "=", session_hash),
            ],
            limit=1,
        )
        if not session:
            raise AccessDenied(_("No active playback session found."))
        if session.state != "active":
            session.sudo().write({
                "request_count": session.request_count + 1
            })
            raise AccessDenied(_(
                "Playback session is not active (state: %s)."
            ) % session.state)

        if session.expires_at and fields.Datetime.now() > session.expires_at:
            session.sudo().write({
                "state": "expired",
                "blocked_reason": _("Session expired."),
            })
            raise AccessDenied(_("Playback session has expired."))

        # Optionally bind to IP
        bind_ip = (
            self.env["ir.config_parameter"].sudo().get_param(
                "slide_shield.bind_session_to_ip", "False"
            ) == "True"
        )
        if (bind_ip and session.ip_address and ip_address
                and session.ip_address != ip_address):
            session.sudo().write({
                "state": "blocked",
                "blocked_reason": _("IP address changed."),
            })
            raise AccessDenied(_("Playback session IP changed."))

        # Update heartbeat
        session.sudo().write({
            "last_seen": fields.Datetime.now(),
            "request_count": session.request_count + 1,
            "ip_address": ip_address or session.ip_address,
            "user_agent": (user_agent or session.user_agent or "")[:512],
        })
        return session

    @api.model
    def _enforce_policy(self, slide, user, session_hash, device_hash,
                        ip_address=None, user_agent=None):
        """Enforce one-session / one-device policies."""
        channel = slide.channel_id
        now = fields.Datetime.now()
        active_domain = [
            ("user_id", "=", user.id),
            ("state", "=", "active"),
            ("expires_at", ">", now),
        ]

        # One session per user (across all slides)
        one_session = getattr(channel, "shield_video_one_session", False)
        if one_session:
            old_sessions = self.sudo().search(
                active_domain + [("session_hash", "!=", session_hash)]
            )
            if old_sessions:
                old_sessions.write({
                    "state": "blocked",
                    "blocked_reason": _(
                        "Another browser session started."
                    ),
                })

        # One device per user
        one_device = getattr(channel, "shield_video_one_device", False)
        if one_device:
            other_device = self.sudo().search(
                active_domain + [("device_hash", "!=", device_hash)],
                limit=1,
            )
            if other_device:
                self.env["shield.video.access.log"].sudo().log_event(
                    "suspicious",
                    slide=slide,
                    user=user,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    extra_data={
                        "reason": "Different device attempted playback."
                    },
                )
                raise AccessDenied(_(
                    "Another device already has an active session."
                ))

    @api.model
    def _cron_cleanup(self):
        """Expire stale sessions and prune old records."""
        now = fields.Datetime.now()

        # Expire active sessions past their expires_at
        expired = self.sudo().search(
            [("state", "=", "active"), ("expires_at", "<", now)],
            limit=5000,
        )
        expired.write({
            "state": "expired",
            "blocked_reason": _("Expired by cleanup cron."),
        })

        # Prune old non-active sessions
        days = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "slide_shield.session_retention_days", "30"
            ) or 30
        )
        cutoff = now - timedelta(days=days)
        old = self.sudo().search(
            [("last_seen", "<", cutoff), ("state", "!=", "active")],
            limit=5000,
        )
        old.unlink()

        # Also clean up access logs
        self.env["shield.video.access.log"].sudo()._cron_cleanup()
