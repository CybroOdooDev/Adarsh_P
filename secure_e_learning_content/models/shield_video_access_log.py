# -*- coding: utf-8 -*-
"""
Slide Shield – Video Access Audit Log
======================================
Immutable audit trail for all protected-video access events.
Each row is a single event (session start, stream request,
access denied, etc.).  Logs are periodically pruned by a cron job.
"""
import json
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

SHIELD_LOG_ACTIONS = [
    ("session_start", "Session Start"),
    ("video_stream", "Video Stream"),
    ("video_init", "Video Init"),
    ("heartbeat", "Heartbeat"),
    ("complete", "Complete"),
    ("access_denied", "Access Denied"),
    ("token_invalid", "Token Invalid"),
    ("session_invalid", "Session Invalid"),
    ("enrollment_denied", "Enrollment Denied"),
    ("suspicious", "Suspicious Activity"),
]


class ShieldVideoAccessLog(models.Model):
    _name = "shield.video.access.log"
    _description = "Protected Video Access Log"
    _order = "timestamp desc"
    _log_access = False

    timestamp = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    action = fields.Selection(
        SHIELD_LOG_ACTIONS, required=True, index=True
    )
    user_id = fields.Many2one(
        "res.users", string="User", index=True, ondelete="set null"
    )
    channel_id = fields.Many2one(
        "slide.channel", string="Course", index=True, ondelete="set null"
    )
    slide_id = fields.Many2one(
        "slide.slide", string="Slide", index=True, ondelete="set null"
    )
    session_id = fields.Many2one(
        "shield.video.session", string="Session",
        index=True, ondelete="set null"
    )
    ip_address = fields.Char(size=45)
    user_agent = fields.Char(size=512)
    extra_data = fields.Text()

    @api.model
    def log_event(self, action, slide=None, user=None, session=None,
                  channel=None, ip_address=None, user_agent=None,
                  extra_data=None):
        """Create an audit log entry.  Fails silently to never break
        the main flow."""
        vals = {
            "timestamp": fields.Datetime.now(),
            "action": action,
        }
        if user:
            vals["user_id"] = user.id if hasattr(user, "id") else user
        if slide:
            vals["slide_id"] = slide.id if hasattr(slide, "id") else slide
            if hasattr(slide, "channel_id") and not channel:
                vals["channel_id"] = slide.channel_id.id
        if session:
            vals["session_id"] = (
                session.id if hasattr(session, "id") else session
            )
        if channel:
            vals["channel_id"] = (
                channel.id if hasattr(channel, "id") else channel
            )
        if ip_address:
            vals["ip_address"] = str(ip_address)[:45]
        if user_agent:
            vals["user_agent"] = str(user_agent)[:512]
        if extra_data:
            vals["extra_data"] = (
                json.dumps(extra_data, default=str)
                if isinstance(extra_data, dict)
                else str(extra_data)
            )
        try:
            return self.sudo().create(vals)
        except Exception:
            _logger.exception(
                "Unable to create shield video access log entry."
            )
            return None

    @api.model
    def _cron_cleanup(self):
        """Prune old log entries beyond the retention period."""
        days = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "slide_shield.log_retention_days", "180"
            ) or 180
        )
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.sudo().search(
            [("timestamp", "<", cutoff)], limit=5000
        )
        old_logs.unlink()
