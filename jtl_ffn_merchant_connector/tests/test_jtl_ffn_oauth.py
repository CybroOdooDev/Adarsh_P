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
from urllib.parse import parse_qs, urlparse

from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase

from .common import fake_response

MAIN_MOD = 'odoo.addons.jtl_ffn_merchant_connector.controllers.main'
TOKEN_DATA = {
    'access_token': 'oauth-access',
    'refresh_token': 'oauth-refresh',
    'expires_in': 3600,
}


@tagged('post_install', '-at_install')
class TestJtlFfnOAuth(HttpCase):
    """Connect redirect, callback and root-page code exchange."""

    def setUp(self):
        super().setUp()
        self.config = self.env['jtl.ffn.config'].create({
            'name': 'OAuth Profile',
            'client_id': 'cid',
            'client_secret': 'csec',
            'redirect_uri': 'https://odoo.example.com',
        })
        new_test_user(
            self.env, login='ffn_oauth_admin',
            groups='base.group_system,jtl_ffn_merchant_connector.group_jtl_ffn_manager')
        self.authenticate('ffn_oauth_admin', 'ffn_oauth_admin')

    def _get(self, path):
        res = self.url_open(path, allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        return res.headers['Location']

    def _reload(self):
        self.config.invalidate_recordset()
        return self.config.sudo()

    def test_connect_redirects_to_jtl(self):
        location = self._get('/jtl_ffn/connect/%d' % self.config.id)
        self.assertTrue(location.startswith('https://oauth2.api.jtl-software.com/authorize?'))
        query = parse_qs(urlparse(location).query)
        self.assertEqual(query['client_id'], ['cid'])
        self.assertEqual(query['redirect_uri'], ['https://odoo.example.com'])
        self.assertEqual(query['state'], [str(self.config.id)])

    def test_connect_uses_base_url_when_no_redirect_uri(self):
        self.config.redirect_uri = False
        self.env['ir.config_parameter'].sudo().set_str(
            'web.base.url', 'https://base.example.com/')
        location = self._get('/jtl_ffn/connect/%d' % self.config.id)
        query = parse_qs(urlparse(location).query)
        self.assertEqual(query['redirect_uri'], ['https://base.example.com'])

    def test_connect_unknown_profile_redirects_to_list(self):
        location = self._get('/jtl_ffn/connect/999999')
        self.assertNotIn('oauth2.api.jtl-software.com', location)

    def test_callback_saves_tokens(self):
        with patch(MAIN_MOD + '.requests.post',
                   return_value=fake_response(TOKEN_DATA)) as post:
            self._get('/jtl_ffn/oauth_callback?code=abc123&state=%d' % self.config.id)
        self.assertTrue(post.called)
        config = self._reload()
        self.assertEqual(config.refresh_token, 'oauth-refresh')
        self.assertEqual(config.access_token, 'oauth-access')
        self.assertEqual(config.connection_state, 'ok')

    def test_callback_uses_session_profile_without_state(self):
        self._get('/jtl_ffn/connect/%d' % self.config.id)
        with patch(MAIN_MOD + '.requests.post',
                   return_value=fake_response(TOKEN_DATA)):
            self._get('/jtl_ffn/oauth_callback?code=abc123')
        self.assertEqual(self._reload().connection_state, 'ok')

    def test_callback_rejected_code_sets_error(self):
        resp = fake_response(
            {'error': 'invalid_grant', 'error_description': 'bad'},
            ok=False, status_code=400)
        with patch(MAIN_MOD + '.requests.post', return_value=resp):
            self._get('/jtl_ffn/oauth_callback?code=abc123&state=%d' % self.config.id)
        config = self._reload()
        self.assertEqual(config.connection_state, 'error')
        self.assertIn('rejected auth code', config.connection_error)

    def test_callback_rejected_code_with_text_body(self):
        resp = fake_response(ok=False, status_code=500, text='oops')
        resp.json.side_effect = ValueError('no json')
        with patch(MAIN_MOD + '.requests.post', return_value=resp):
            self._get('/jtl_ffn/oauth_callback?code=abc123&state=%d' % self.config.id)
        self.assertEqual(self._reload().connection_state, 'error')

    def test_callback_request_exception_sets_error(self):
        with patch(MAIN_MOD + '.requests.post', side_effect=OSError('network')):
            self._get('/jtl_ffn/oauth_callback?code=abc123&state=%d' % self.config.id)
        config = self._reload()
        self.assertEqual(config.connection_state, 'error')
        self.assertIn('network', config.connection_error)

    def test_callback_authorization_error(self):
        with patch(MAIN_MOD + '.requests.post') as post:
            self._get('/jtl_ffn/oauth_callback?error=access_denied&state=%d' % self.config.id)
        post.assert_not_called()
        config = self._reload()
        self.assertEqual(config.connection_state, 'error')
        self.assertIn('access_denied', config.connection_error)

    def test_callback_authorization_error_without_profile(self):
        with patch(MAIN_MOD + '.requests.post') as post:
            self._get('/jtl_ffn/oauth_callback?error=access_denied')
        post.assert_not_called()

    def test_callback_without_code_is_ignored(self):
        with patch(MAIN_MOD + '.requests.post') as post:
            self._get('/jtl_ffn/oauth_callback?state=%d' % self.config.id)
        post.assert_not_called()

    def test_callback_without_valid_profile_is_ignored(self):
        with patch(MAIN_MOD + '.requests.post') as post:
            self._get('/jtl_ffn/oauth_callback?code=abc123')
            self._get('/jtl_ffn/oauth_callback?code=abc123&state=999999')
        post.assert_not_called()

    def test_root_page_exchanges_code(self):
        with patch(MAIN_MOD + '.requests.post',
                   return_value=fake_response(TOKEN_DATA)) as post:
            self.url_open('/?code=abcdefghijk123&state=%d' % self.config.id,
                          allow_redirects=False)
        self.assertTrue(post.called)
        self.assertEqual(self._reload().connection_state, 'ok')

    def test_public_user_cannot_start_flow(self):
        self.logout()
        res = self.url_open('/jtl_ffn/connect/%d' % self.config.id, allow_redirects=False)
        self.assertNotIn('oauth2.api.jtl-software.com', res.headers.get('Location', ''))
