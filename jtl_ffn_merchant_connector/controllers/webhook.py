# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#############################################################################
import logging
import threading
import time

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.home import Home

_logger = logging.getLogger(__name__)


class JtlFfnHome(Home):

    # Bare @route() inherits the parent's URL/auth settings (so Odoo no longer
    # warns about an undecorated override). ``readonly=False`` is required
    # because the OAuth code exchange writes the tokens to jtl.ffn.config, which
    # fails on the read-only cursor Odoo 19 uses for the parent's GET route.
    @http.route(readonly=False)
    def index(self, *args, **kw):
        code = kw.get('code')
        if code and len(code) > 10 and 'debug' not in kw:
            from .main import handle_oauth_code_exchange
            return handle_oauth_code_exchange(code, kw.get('state'))
        return super().index(*args, **kw)


# Minimum number of seconds between two webhook-triggered syncs of the same
# kind for the same configuration (per worker process).  Keeps an anonymous
# caller from using the endpoint to hammer the FFN API / the database.
WEBHOOK_SYNC_DEBOUNCE = 30

_last_trigger = {}
_last_trigger_lock = threading.Lock()


def _debounce_ok(config_id, kind):
    """Return True (and record the call) if a sync of ``kind`` may run now."""
    key = (request.env.cr.dbname, config_id, kind)
    now = time.monotonic()
    with _last_trigger_lock:
        last = _last_trigger.get(key)
        if last is not None and now - last < WEBHOOK_SYNC_DEBOUNCE:
            return False
        _last_trigger[key] = now
    return True


class JtlFfnWebhookController(http.Controller):
    """
    Receives inbound webhook events from JTL-FFN.

    SECURITY MODEL
    --------------
    The endpoint is public and FFN does not send a verifiable secret, so the
    request body is **untrusted** and is never written to the database.  The
    event name is only used as a hint for *which* synchronisation to run; the
    data itself is then pulled from the FFN API with the OAuth token stored in
    the configuration (see ``pull_stock_from_ffn``, ``pull_tracking_numbers``
    and ``pull_returns``).  A forged call can therefore, at worst, trigger a
    (rate-limited) sync of data that FFN itself reports.

    Endpoint: POST /jtl_ffn/webhook/<config_id>
    """

    # event name -> (kind, config flag, model, method)
    _EVENT_ACTIONS = {
        'stock.updated':         ('stock',    'sync_stock',    'jtl.ffn.product.sync', 'pull_stock_from_ffn'),
        'inventory.updated':     ('stock',    'sync_stock',    'jtl.ffn.product.sync', 'pull_stock_from_ffn'),
        'order.shipped':         ('tracking', 'sync_tracking', 'jtl.ffn.tracking',     'pull_tracking_numbers'),
        'fulfillment.shipped':   ('tracking', 'sync_tracking', 'jtl.ffn.tracking',     'pull_tracking_numbers'),
        'order.confirmed':       ('tracking', 'sync_tracking', 'jtl.ffn.tracking',     'pull_tracking_numbers'),
        'fulfillment.confirmed': ('tracking', 'sync_tracking', 'jtl.ffn.tracking',     'pull_tracking_numbers'),
        'return.received':       ('returns',  'sync_returns',  'jtl.ffn.return',       'pull_returns'),
        'return.registered':     ('returns',  'sync_returns',  'jtl.ffn.return',       'pull_returns'),
    }

    @http.route(
        '/jtl_ffn/webhook/<int:config_id>',
        type='jsonrpc',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def receive_webhook(self, config_id, **kwargs):
        """Entry point for inbound JTL-FFN webhook POST events.

        The response is identical for unknown configs, inactive configs,
        unknown events and debounced calls, so the endpoint leaks nothing
        about which configuration ids exist.
        """
        response = {'status': 'ok'}

        config = request.env['jtl.ffn.config'].sudo().browse(config_id)
        if not config.exists() or not config.is_active:
            _logger.warning("FFN webhook: unknown or inactive config id %d", config_id)
            return response

        try:
            payload = request.get_json_data()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        event = payload.get('event') or payload.get('eventType') or ''
        if not isinstance(event, str):
            event = ''

        action = self._EVENT_ACTIONS.get(event)
        if not action:
            _logger.info("FFN webhook: ignoring event %r for config %s", event, config.name)
            return response

        kind, flag, model, method = action
        if not config[flag]:
            return response
        if not _debounce_ok(config.id, kind):
            _logger.info("FFN webhook: %s sync for config %s debounced", kind, config.name)
            return response

        _logger.info("FFN webhook: event=%s config=%s -> pulling %s from FFN", event, config.name, kind)
        try:
            with request.env.cr.savepoint():
                getattr(request.env[model].sudo(), method)(config)
        except Exception:
            _logger.exception("FFN webhook: %s sync failed for config %s", kind, config.name)
        return response
