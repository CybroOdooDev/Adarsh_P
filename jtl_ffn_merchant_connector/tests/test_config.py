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
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import MODULE, JtlFfnCommon, fake_response

CONFIG_MOD = MODULE + '.jtl_ffn_config'
TOKEN_DATA = {
    'access_token': 'new-access',
    'refresh_token': 'new-refresh',
    'expires_in': 3600,
}


@tagged('post_install', '-at_install')
class TestJtlFfnConfig(JtlFfnCommon):

    def test_get_access_token_requires_refresh_token(self):
        self.config.refresh_token = False
        with self.assertRaises(UserError):
            self.config._get_access_token()

    def test_get_access_token_success(self):
        with patch(CONFIG_MOD + '.requests.post',
                   return_value=fake_response(TOKEN_DATA)) as post:
            token = self.config._get_access_token()
        self.assertEqual(token, 'new-access')
        self.assertTrue(post.called)
        self.assertEqual(self.config.access_token, 'new-access')
        self.assertEqual(self.config.refresh_token, 'new-refresh')
        self.assertEqual(self.config.connection_state, 'ok')
        self.assertTrue(self.config.token_expiry)

    def test_get_access_token_without_new_refresh_token(self):
        data = {'access_token': 'only-access'}
        with patch(CONFIG_MOD + '.requests.post', return_value=fake_response(data)):
            self.config._get_access_token()
        self.assertEqual(self.config.refresh_token, 'refresh')

    def test_get_access_token_rejected_with_json_body(self):
        resp = fake_response(
            {'error': 'invalid_grant', 'error_description': 'expired'},
            ok=False, status_code=400)
        with patch(CONFIG_MOD + '.requests.post', return_value=resp):
            with self.assertRaises(UserError):
                self.config._get_access_token()

    def test_get_access_token_rejected_with_text_body(self):
        resp = fake_response(ok=False, status_code=500, text='server down')
        resp.json.side_effect = ValueError('no json')
        with patch(CONFIG_MOD + '.requests.post', return_value=resp):
            with self.assertRaises(UserError):
                self.config._get_access_token()

    def test_get_access_token_unexpected_exception(self):
        with patch(CONFIG_MOD + '.requests.post', side_effect=OSError('network')):
            with self.assertRaises(UserError):
                self.config._get_access_token()

    def test_get_valid_token_uses_cache(self):
        self.config.write({
            'access_token': 'cached',
            'token_expiry': '2999-01-01 00:00:00',
        })
        with patch.object(type(self.config), '_get_access_token') as refresh:
            self.assertEqual(self.config._get_valid_token(), 'cached')
        refresh.assert_not_called()

    def test_get_valid_token_refreshes_when_expired(self):
        self.config.write({
            'access_token': 'stale',
            'token_expiry': '2000-01-01 00:00:00',
        })
        with patch.object(type(self.config), '_get_access_token',
                          return_value='fresh') as refresh:
            self.assertEqual(self.config._get_valid_token(), 'fresh')
        refresh.assert_called_once()

    def test_api_request_success_and_path_rewrite(self):
        resp = fake_response({'ok': True})
        with patch.object(type(self.config), '_get_valid_token', return_value='tok'), \
                patch(CONFIG_MOD + '.requests.request', return_value=resp) as request:
            result = self.config._api_request('GET', '/v1/products', params={'a': 1})
        self.assertEqual(result, {'ok': True})
        url = request.call_args.args[1]
        self.assertTrue(url.endswith('/api/v1/merchant/products'), url)

    def test_api_request_empty_body(self):
        resp = fake_response(content=False)
        with patch.object(type(self.config), '_get_valid_token', return_value='tok'), \
                patch(CONFIG_MOD + '.requests.request', return_value=resp):
            self.assertEqual(self.config._api_request('DELETE', '/other'), {})

    def test_api_request_error(self):
        resp = fake_response(ok=False, status_code=500, text='bad')
        with patch.object(type(self.config), '_get_valid_token', return_value='tok'), \
                patch(CONFIG_MOD + '.requests.request', return_value=resp):
            with self.assertRaises(UserError):
                self.config._api_request('GET', '/other')

    def test_api_request_retries_after_401(self):
        unauthorized = fake_response(ok=False, status_code=401)
        good = fake_response({'done': 1})
        with patch.object(type(self.config), '_get_valid_token', return_value='old'), \
                patch.object(type(self.config), '_get_access_token',
                             return_value='new') as refresh, \
                patch(CONFIG_MOD + '.requests.request',
                      side_effect=[unauthorized, good]) as request:
            result = self.config._api_request('GET', '/other')
        self.assertEqual(result, {'done': 1})
        refresh.assert_called_once()
        self.assertEqual(request.call_count, 2)

    def test_exchange_auth_code_requires_code(self):
        with self.assertRaises(UserError):
            self.config.action_exchange_auth_code()

    def test_exchange_auth_code_success(self):
        self.config.auth_code = 'code-123'
        with patch(CONFIG_MOD + '.requests.post', return_value=fake_response(TOKEN_DATA)):
            action = self.config.action_exchange_auth_code()
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(self.config.refresh_token, 'new-refresh')
        self.assertFalse(self.config.auth_code)

    def test_exchange_auth_code_rejected(self):
        self.config.auth_code = 'code-123'
        resp = fake_response(
            {'error': 'invalid_grant', 'error_description': 'bad code'},
            ok=False, status_code=400)
        with patch(CONFIG_MOD + '.requests.post', return_value=resp):
            action = self.config.action_exchange_auth_code()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(self.config.connection_state, 'error')

    def test_exchange_auth_code_rejected_with_text_body(self):
        self.config.auth_code = 'code-123'
        resp = fake_response(ok=False, status_code=500, text='oops')
        resp.json.side_effect = ValueError('no json')
        with patch(CONFIG_MOD + '.requests.post', return_value=resp):
            action = self.config.action_exchange_auth_code()
        self.assertEqual(action['params']['type'], 'danger')

    def test_connect_requires_credentials(self):
        action = self.config.action_connect_jtl()
        self.assertEqual(action['url'], '/jtl_ffn/connect/%d' % self.config.id)
        self.config.sudo().client_secret = ''
        with self.assertRaises(UserError):
            self.config.action_connect_jtl()

    def test_test_connection(self):
        with patch.object(type(self.config), '_get_access_token', return_value='t'):
            action = self.config.action_test_connection()
        self.assertEqual(action['params']['type'], 'success')
        with patch.object(type(self.config), '_get_access_token',
                          side_effect=UserError('nope')):
            action = self.config.action_test_connection()
        self.assertEqual(action['params']['type'], 'danger')

    def test_run_full_sync_success(self):
        self.patch_model('jtl.ffn.product.sync', 'sync_products_to_ffn', return_value=2)
        self.patch_model('jtl.ffn.product.sync', 'pull_stock_from_ffn', return_value=3)
        self.patch_model('jtl.ffn.order.sync', 'push_pending_orders', return_value=1)
        self.patch_model('jtl.ffn.tracking', 'pull_tracking_numbers', return_value=4)
        self.patch_model('jtl.ffn.return', 'pull_returns', return_value=5)
        action = self.config.action_run_full_sync()
        self.assertEqual(action['params']['type'], 'success')
        self.assertIn('Products pushed: 2', action['params']['message'])

    def test_run_full_sync_with_error(self):
        self.patch_model('jtl.ffn.product.sync', 'sync_products_to_ffn',
                         side_effect=UserError('fail'))
        self.patch_model('jtl.ffn.product.sync', 'pull_stock_from_ffn', return_value=0)
        self.patch_model('jtl.ffn.order.sync', 'push_pending_orders', return_value=0)
        self.patch_model('jtl.ffn.tracking', 'pull_tracking_numbers', return_value=0)
        self.patch_model('jtl.ffn.return', 'pull_returns', return_value=0)
        action = self.config.action_run_full_sync()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertTrue(action['params']['sticky'])

    def test_run_full_sync_nothing_enabled(self):
        self.config.write({
            'sync_products': False,
            'sync_stock': False,
            'sync_orders': False,
            'sync_tracking': False,
            'sync_returns': False,
        })
        action = self.config.action_run_full_sync()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('Nothing to sync', action['params']['message'])

    def test_redirect_uri_defaults_to_base_url(self):
        self.env['ir.config_parameter'].sudo().set_str(
            'web.base.url', 'https://odoo.example.com/')
        config = self.env['jtl.ffn.config'].create({
            'name': 'Default URI', 'client_id': 'c', 'client_secret': 's'})
        self.assertEqual(config.redirect_uri, 'https://odoo.example.com')

    def test_redirect_uri_falls_back_to_localhost(self):
        self.env['ir.config_parameter'].sudo().set_str('web.base.url', '')
        config = self.env['jtl.ffn.config'].create({
            'name': 'Fallback URI', 'client_id': 'c', 'client_secret': 's'})
        self.assertEqual(config.redirect_uri, 'http://localhost:8018')

    def test_redirect_uri_keeps_manual_value(self):
        config = self.env['jtl.ffn.config'].create({
            'name': 'Manual URI', 'client_id': 'c', 'client_secret': 's',
            'redirect_uri': 'https://my.example.com/cb'})
        self.assertEqual(config.redirect_uri, 'https://my.example.com/cb')

    def test_exchange_auth_code_sends_profile_redirect_uri(self):
        self.config.write({'auth_code': 'code-123',
                           'redirect_uri': 'https://odoo.example.com/'})
        with patch(CONFIG_MOD + '.requests.post',
                   return_value=fake_response(TOKEN_DATA)) as post:
            self.config.action_exchange_auth_code()
        self.assertEqual(
            post.call_args.kwargs['data']['redirect_uri'],
            'https://odoo.example.com')

    def test_exchange_auth_code_base_url_fallback(self):
        self.env['ir.config_parameter'].sudo().set_str('web.base.url', '')
        self.config.write({'auth_code': 'code-123', 'redirect_uri': False})
        with patch(CONFIG_MOD + '.requests.post',
                   return_value=fake_response(TOKEN_DATA)) as post:
            self.config.action_exchange_auth_code()
        self.assertEqual(
            post.call_args.kwargs['data']['redirect_uri'],
            'http://localhost:8018')

    def test_write_isolated_in_test_mode_uses_plain_write(self):
        self.config._write_isolated({'access_token': 'abc'})
        self.assertEqual(self.config.access_token, 'abc')

    def test_write_isolated_falls_back_when_cursor_fails(self):
        registry_cls = type(self.env.registry)
        with patch('odoo.modules.module.current_test', None), \
                patch.object(registry_cls, 'cursor', side_effect=RuntimeError('no cursor')):
            self.config._write_isolated({'access_token': 'fallback'})
        self.assertEqual(self.config.access_token, 'fallback')

    def test_cron_refresh_expiring_tokens(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        self.config.token_expiry = False
        with patch.object(type(self.config), '_get_access_token',
                          return_value='t') as refresh:
            self.env['jtl.ffn.config'].cron_refresh_expiring_tokens()
        refresh.assert_called_once()

    def test_cron_refresh_expiring_tokens_swallows_errors(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        self.config.token_expiry = False
        with patch.object(type(self.config), '_get_access_token',
                          side_effect=UserError('x')) as refresh:
            self.env['jtl.ffn.config'].cron_refresh_expiring_tokens()
        refresh.assert_called_once()

    def test_cron_refresh_expiring_tokens_skips_fresh_tokens(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        self.config.write({'access_token': 'ok', 'token_expiry': '2999-01-01 00:00:00'})
        with patch.object(type(self.config), '_get_access_token') as refresh:
            self.env['jtl.ffn.config'].cron_refresh_expiring_tokens()
        refresh.assert_not_called()

    def test_cron_refresh_expiring_tokens_skips_profiles_without_refresh_token(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        self.config.refresh_token = False
        with patch.object(type(self.config), '_get_access_token') as refresh:
            self.env['jtl.ffn.config'].cron_refresh_expiring_tokens()
        refresh.assert_not_called()

    def test_inactive_profile_is_not_refreshed(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        self.config.write({'is_active': False, 'token_expiry': False})
        with patch.object(type(self.config), '_get_access_token') as refresh:
            self.env['jtl.ffn.config'].cron_refresh_expiring_tokens()
        refresh.assert_not_called()

    def test_warehouse_unique_constraint(self):
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env['jtl.ffn.warehouse'].create({
                'config_id': self.config.id,
                'name': 'Duplicate',
                'odoo_warehouse_id': self.odoo_wh.id,
                'ffn_warehouse_id': 'WH1',
            })

    def test_stock_line(self):
        line = self.env['jtl.ffn.stock.line'].create({
            'warehouse_id': self.ffn_wh.id,
            'product_id': self.product.id,
            'sku': 'FFN-SKU-1',
            'ffn_quantity': 7,
        })
        self.assertIn(line, self.ffn_wh.stock_line_ids)
