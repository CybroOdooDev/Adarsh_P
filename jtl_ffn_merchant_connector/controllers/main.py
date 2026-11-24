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
import urllib.parse
import requests
from datetime import timedelta

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

FFN_TOKEN_URL = 'https://oauth2.api.jtl-software.com/token'


def handle_oauth_code_exchange(code, state=None, redirect_uri_override=None):
    """Core function to exchange auth code for tokens and redirect to Odoo backend."""
    config_id_str = state or str(request.session.get('jtl_ffn_config_id') or '')

    if not config_id_str.isdigit():
        _logger.error("JTL OAuth callback: missing valid config ID (state=%s).", state)
        return request.redirect("/odoo/jtl.ffn.config")

    config_id = int(config_id_str)
    config = request.env['jtl.ffn.config'].sudo().browse(config_id)
    if not config.exists():
        _logger.error("JTL OAuth callback: Config record %d not found.", config_id)
        return request.redirect("/odoo/jtl.ffn.config")

    base_url = (request.env['ir.config_parameter'].sudo().get_str('web.base.url') or '').rstrip('/')
    if not base_url:
        base_url = 'http://localhost:8018'

    redirect_uri = redirect_uri_override or (config.redirect_uri or base_url).rstrip('/')

    try:
        c_id = (config.client_id or '').strip()
        c_secret = (config.client_secret or '').strip()

        resp = requests.post(
            FFN_TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'code': code.strip(),
                'redirect_uri': redirect_uri,
                'client_id': c_id,
                'client_secret': c_secret,
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15,
        )

        if not resp.ok:
            try:
                err_detail = resp.json()
                err_msg = "%s - %s" % (err_detail.get('error'), err_detail.get('error_description'))
            except Exception:
                err_msg = resp.text
            config.sudo().write({
                'connection_state': 'error',
                'connection_error': f"JTL OAuth rejected auth code: {err_msg} (HTTP {resp.status_code})",
            })
        else:
            data = resp.json()
            token = data.get('access_token')
            new_refresh = data.get('refresh_token')
            expires_in = data.get('expires_in', 1800)
            expiry = fields.Datetime.now() + timedelta(seconds=max(expires_in - 600, 60))
            config.sudo().write({
                'refresh_token': new_refresh,
                'access_token': token,
                'token_expiry': expiry,
                'connection_state': 'ok',
                'connection_error': False,
                'auth_code': False,
            })
    except Exception as exc:
        _logger.exception("Error processing JTL OAuth callback")
        config.sudo().write({
            'connection_state': 'error',
            'connection_error': str(exc),
        })

    return request.redirect(f"/odoo/jtl.ffn.config/{config.id}")


class JtlFfnOAuthController(http.Controller):
    """Handles OAuth 2.0 redirect callbacks from JTL Software."""

    @http.route('/jtl_ffn/connect/<int:config_id>', type='http', auth='user', website=False, csrf=False)
    def connect_jtl(self, config_id, **kwargs):
        """Store config ID in session and redirect to JTL OAuth authorize endpoint."""
        config = request.env['jtl.ffn.config'].sudo().browse(config_id)
        if not config.exists():
            return request.redirect("/odoo/jtl.ffn.config")

        request.session['jtl_ffn_config_id'] = config.id

        base_url = (request.env['ir.config_parameter'].sudo().get_str('web.base.url') or '').rstrip('/')
        if not base_url:
            base_url = 'http://localhost:8018'

        redirect_uri = (config.redirect_uri or base_url).rstrip('/')
        c_id = (config.client_id or '').strip()

        auth_url = (
            "https://oauth2.api.jtl-software.com/authorize?"
            f"response_type=code"
            f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
            f"&client_id={urllib.parse.quote(c_id, safe='')}"
            f"&scope=ffn.merchant.read%20ffn.merchant.write"
            f"&state={config.id}"
        )
        return request.redirect(auth_url, local=False)

    @http.route('/jtl_ffn/oauth_callback', type='http', auth='user', website=False, csrf=False,
                readonly=False)
    def oauth_callback(self, **kwargs):
        """Callback handler for JTL OAuth authorization grant."""
        code = kwargs.get('code')
        state = kwargs.get('state')
        error = kwargs.get('error')

        if error:
            _logger.error("JTL OAuth authorization error: %s", error)
            config_id_str = state or str(request.session.get('jtl_ffn_config_id') or '')
            if config_id_str.isdigit():
                config = request.env['jtl.ffn.config'].sudo().browse(int(config_id_str))
                if config.exists():
                    config.sudo().write({
                        'connection_state': 'error',
                        'connection_error': f"JTL OAuth Error: {error}",
                    })
                    return request.redirect(f"/odoo/jtl.ffn.config/{config.id}")
            return request.redirect("/odoo/jtl.ffn.config")

        if not code:
            _logger.error("JTL OAuth callback missing authorization code.")
            return request.redirect("/odoo/jtl.ffn.config")

        return handle_oauth_code_exchange(code, state)
