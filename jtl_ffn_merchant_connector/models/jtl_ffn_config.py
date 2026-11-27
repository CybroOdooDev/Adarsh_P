# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#############################################################################
import logging
import requests
from datetime import timedelta
from odoo import models, fields, api, modules
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

FFN_TOKEN_URL = 'https://oauth2.api.jtl-software.com/token'

FFN_API_URLS = {
    'sandbox':    'https://ffn-sbx.api.jtl-software.com',
    'production': 'https://ffn2.api.jtl-software.com',
}


class JtlFfnConfig(models.Model):
    """JTL FFN Configuration and Connection Manager.

    One record = one FFN tenant / credential set.
    Multiple records are supported for multi-warehouse/multi-tenant setups.
    """
    _name = 'jtl.ffn.config'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'JTL FFN Configuration and Connection Manager'

    name = fields.Char(
        string="Profile Name", required=True, default="JTL FFN Live",
        help="Name of this configuration profile."
    )
    environment = fields.Selection([
        ('sandbox',    'Sandbox / Testing'),
        ('production', 'Production / Live'),
    ], default='sandbox', required=True,
        help="Choose whether this configuration connects to the sandbox for testing or the production system for live operations."
    )

    client_id     = fields.Char(string="Client ID", required=True, help="The Client ID provided by JTL.")
    client_secret = fields.Char(
        required=True, help="The Client Secret provided by JTL.",
        groups="jtl_ffn_merchant_connector.group_jtl_ffn_manager",
    )

    redirect_uri  = fields.Char(
        string="Redirect URI", compute="_compute_redirect_uri",
        store=True,
        readonly=False,
        help="The exact Redirect URI registered for your OAuth client in the JTL Customer Center (e.g. http://localhost:8018)."
    )

    @api.depends('environment')
    def _compute_redirect_uri(self):
        base_url = (self.env['ir.config_parameter'].sudo().get_str('web.base.url') or '').rstrip('/')
        if not base_url:
            base_url = 'http://localhost:8018'
        for record in self:
            if not record.redirect_uri:
                record.redirect_uri = base_url

    refresh_token = fields.Char(
        copy=False,
        groups="jtl_ffn_merchant_connector.group_jtl_ffn_manager",
        help="Paste the refresh_token obtained from a one-time manual OAuth login at "
             "https://oauth2.api.jtl-software.com/authorize. "
             "The connector uses this to obtain access tokens automatically."
    )

    access_token = fields.Char(
        string="Active Token", copy=False, help="The active OAuth access token.",
        groups="jtl_ffn_merchant_connector.group_jtl_ffn_manager",
    )

    token_expiry = fields.Datetime(string="Token Expires At", copy=False, help="Expiration time of the current access token.")
    is_active    = fields.Boolean(string="Active", default=True, help="Check this to make the profile active.")
    auth_code    = fields.Char(
        string="Authorization Code", copy=False,
        help="The one-time authorization code used to retrieve the initial tokens.",
        groups="jtl_ffn_merchant_connector.group_jtl_ffn_manager",
    )

    sync_products = fields.Boolean(default=True, help="If enabled, product data will be pushed to FFN.")
    sync_stock    = fields.Boolean(default=True, help="If enabled, stock levels will be pulled from FFN.")
    sync_orders   = fields.Boolean(string="Push Orders",    default=True, help="If enabled, pending orders will be pushed to FFN.")
    sync_tracking = fields.Boolean(string="Pull Tracking",  default=True, help="If enabled, tracking numbers will be pulled from FFN.")
    sync_returns  = fields.Boolean(default=True, help="If enabled, returns data will be synchronized from FFN.")

    fallback_shipping_method_id = fields.Char(string="Fallback Shipping Method ID", help="Used when no mapping exists.")
    fallback_shipping_type = fields.Selection([
        ('Standard', 'Standard'),
        ('Express', 'Express'),
        ('Freight', 'Freight'),
        ('Postal', 'Postal')
    ], default='Standard', help="The fallback shipping type to use when a specific mapping isn't found.")

    warehouse_ids = fields.One2many(
        'jtl.ffn.warehouse', 'config_id', string="Fulfillment Warehouses",
        help="Warehouses associated with this FFN configuration."
    )

    connection_state = fields.Selection([
        ('not_tested', 'Not Tested'),
        ('ok',         'Connected'),
        ('error',      'Error'),
    ], string="Connection Status", default='not_tested', copy=False, help="Current state of the API connection.")
    connection_error = fields.Char(string="Last Error", copy=False, help="Last error message encountered during connection, if any.")

    def action_connect_jtl(self):
        """Initiate direct OAuth authorization flow with JTL."""
        self.ensure_one()
        if not self.client_id or not self.client_secret:
            raise UserError(self.env._("Please enter Client ID and Client Secret before connecting to JTL."))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/jtl_ffn/connect/{self.id}',
            'target': 'self',
        }

    def _write_isolated(self, vals):
        """Write ``vals`` in their own transaction.

        Tokens (a rotated refresh token in particular) and connection errors
        must survive a rollback of the calling transaction.  Falls back to a
        plain write when a separate cursor cannot be used (e.g. in tests).
        """
        self.ensure_one()
        if modules.module.current_test:
            return self.write(vals)
        try:
            with self.env.registry.cursor() as new_cr:
                new_env = api.Environment(new_cr, self.env.uid, self.env.context)
                self.with_env(new_env).write(vals)
        except Exception as write_err:
            _logger.warning(
                "Failed to write FFN connection data with new cursor: %s. "
                "Falling back to standard write.", write_err)
            self.write(vals)
        return True

    def _get_access_token(self):
        """Fetch a fresh access token using the OAuth2 Refresh Token Grant."""
        self.ensure_one()
        if not self.refresh_token:
            raise UserError(self.env._(
                "JTL FFN: No Refresh Token configured. "
                "Please click 'Connect to JTL' to log in and authorize your connection."
            ))
        try:
            c_id = (self.client_id or '').strip()
            c_secret = (self.client_secret or '').strip()
            r_token = (self.refresh_token or '').strip()

            resp = requests.post(
                FFN_TOKEN_URL,
                data={
                    'grant_type':    'refresh_token',
                    'refresh_token': r_token,
                    'client_id':     c_id,
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
                raise UserError(self.env._(
                    "JTL OAuth Server rejected credentials: %(error)s (HTTP %(status)s)",
                    error=err_msg, status=resp.status_code))

            data = resp.json()
            token         = data.get('access_token')
            new_refresh   = data.get('refresh_token')
            expires_in    = data.get('expires_in', 1800)
            expiry        = fields.Datetime.now() + timedelta(seconds=max(expires_in - 600, 60))
            write_vals = {
                'access_token':     token,
                'token_expiry':     expiry,
                'connection_state': 'ok',
                'connection_error': False,
            }
            if new_refresh:
                write_vals['refresh_token'] = new_refresh

            # Persist tokens in their own transaction so a rotated refresh
            # token survives a rollback of the calling transaction.
            self._write_isolated(write_vals)
            return token
        except UserError as err:
            self._write_isolated({
                'connection_state': 'error',
                'connection_error': str(err.args[0] if err.args else err),
            })
            raise
        except Exception as exc:
            self._write_isolated({
                'connection_state': 'error',
                'connection_error': str(exc),
            })
            raise UserError(self.env._("JTL FFN auth failed: %s", exc)) from exc

    def _get_valid_token(self):
        """Return a cached token, refreshing it when expired."""
        self.ensure_one()
        self.invalidate_recordset()
        if (
            not self.access_token
            or not self.token_expiry
            or fields.Datetime.now() >= self.token_expiry
        ):
            return self._get_access_token()
        return self.access_token

    def _api_request(self, method, path, json=None, params=None):
        """Make an authenticated HTTP request to the JTL FFN REST API."""
        self.ensure_one()
        base   = FFN_API_URLS[self.environment]
        token  = self._get_valid_token()

        if path.startswith('/v1/'):
            path = '/api/v1/merchant/' + path[4:]

        url    = "%s%s" % (base, path)
        headers = {
            'Authorization': 'Bearer %s' % token,
            'Content-Type':  'application/json',
            'Accept':        'application/json',
        }
        resp = requests.request(
            method, url, json=json, params=params,
            headers=headers, timeout=30,
        )
        if resp.status_code == 401:
            _logger.warning("FFN: 401 on %s, forcing token refresh", path)
            self.invalidate_recordset()
            token = self._get_access_token()
            headers['Authorization'] = 'Bearer %s' % token
            resp = requests.request(
                method, url, json=json, params=params,
                headers=headers, timeout=30,
            )
        if not resp.ok:
            raise UserError(self.env._(
                "JTL FFN API error [%(status)s %(path)s]: %(body)s",
                status=resp.status_code, path=path, body=resp.text[:400],
            ))
        if resp.content:
            return resp.json()
        return {}

    def action_exchange_auth_code(self):
        """Exchange a one-time OAuth authorization code for access and refresh tokens."""
        self.ensure_one()
        if not self.auth_code:
            raise UserError(self.env._("Please enter an Authorization Code first."))
        try:
            c_id = (self.client_id or '').strip()
            c_secret = (self.client_secret or '').strip()
            code = (self.auth_code or '').strip()
            base_url = (self.env['ir.config_parameter'].sudo().get_str('web.base.url') or '').rstrip('/')
            if not base_url:
                base_url = 'http://localhost:8018'
            # the code was issued for the Redirect URI of the authorize request
            redirect_uri = (self.redirect_uri or base_url).rstrip('/')
            resp = requests.post(
                FFN_TOKEN_URL,
                data={
                    'grant_type':    'authorization_code',
                    'code':          code,
                    'redirect_uri':  redirect_uri,
                    'client_id':     c_id,
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
                raise UserError(self.env._("JTL OAuth Server rejected auth code: %(error)s (HTTP %(status)s)", error=err_msg, status=resp.status_code))
            data = resp.json()
            token = data.get('access_token')
            new_refresh = data.get('refresh_token')
            expires_in = data.get('expires_in', 1800)
            expiry = fields.Datetime.now() + timedelta(seconds=max(expires_in - 600, 60))
            self.write({
                'refresh_token': new_refresh,
                'access_token': token,
                'token_expiry': expiry,
                'connection_state': 'ok',
                'connection_error': False,
                'auth_code': False,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': self.env._('Exchange Successful'),
                    'message': self.env._('Refresh token received and saved.'),
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }
        except Exception as exc:
            self.write({
                'connection_state': 'error',
                'connection_error': str(exc.args[0] if hasattr(exc, 'args') and exc.args else exc),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': self.env._('Exchange Failed'),
                    'message': str(exc.args[0] if hasattr(exc, 'args') and exc.args else exc),
                    'type': 'danger',
                    'sticky': True,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }

    def action_test_connection(self):
        """Test the connection by fetching a fresh access token."""
        self.ensure_one()
        try:
            self._get_access_token()
            return {
                'type':   'ir.actions.client',
                'tag':    'display_notification',
                'params': {
                    'title':   self.env._('Connection Successful'),
                    'message': self.env._('Token retrieved and cached. Profile "%s" is ready.') % self.name,
                    'type':    'success',
                    'sticky':  False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }
        except Exception as exc:
            return {
                'type':   'ir.actions.client',
                'tag':    'display_notification',
                'params': {
                    'title':   self.env._('Connection Failed'),
                    'message': str(exc.args[0] if hasattr(exc, 'args') and exc.args else exc),
                    'type':    'danger',
                    'sticky':  True,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }

    def action_run_full_sync(self):
        """Trigger all enabled sync operations manually."""
        self.ensure_one()
        results = []
        errors = []

        def _run(label, fn):
            """Execute a single sync function and track errors."""
            try:
                count = fn()
                results.append("%s: %d" % (label, count or 0))
            except Exception as exc:
                errors.append("%s failed: %s" % (label, str(exc)[:120]))
                _logger.error("FFN manual sync — %s failed: %s", label, exc)

        if self.sync_products:
            _run("Products pushed", lambda: self.env['jtl.ffn.product.sync'].sync_products_to_ffn(self))
        if self.sync_stock:
            _run("Stock lines updated", lambda: self.env['jtl.ffn.product.sync'].pull_stock_from_ffn(self))
        if self.sync_orders:
            _run("Orders sent", lambda: self.env['jtl.ffn.order.sync'].push_pending_orders(self))
        if self.sync_tracking:
            _run("Tracking numbers imported", lambda: self.env['jtl.ffn.tracking'].pull_tracking_numbers(self))
        if self.sync_returns:
            _run("Returns synced", lambda: self.env['jtl.ffn.return'].pull_returns(self))

        if not results and not errors:
            msg = self.env._("Nothing to sync — all sync options are disabled.")
            notif_type = "warning"
        elif errors:
            msg = " | ".join(results + errors)
            notif_type = "warning"
        else:
            msg = " | ".join(results)
            notif_type = "success"

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Full Sync Complete'),
                'message': msg,
                'type': notif_type,
                'sticky': bool(errors),
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                },
            },
        }

    @api.model
    def cron_refresh_expiring_tokens(self):
        """Automatically refresh tokens that are close to expiring for all active profiles."""
        configs = self.search([('is_active', '=', True)])
        for config in configs:
            if not config.refresh_token:
                continue
            # If the token is already expired or about to expire in the next 10 minutes (600 seconds)
            buffer = timedelta(minutes=10)
            if (
                not config.access_token
                or not config.token_expiry
                or fields.Datetime.now() + buffer >= config.token_expiry
            ):
                try:
                    _logger.info("Cron: Auto-refreshing FFN token for profile %s", config.name)
                    config._get_access_token()
                except Exception as exc:
                    _logger.error("Cron: Auto-refresh of FFN token failed for profile %s: %s", config.name, exc)
