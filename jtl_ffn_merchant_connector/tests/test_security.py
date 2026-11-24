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
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged('post_install', '-at_install')
class TestJtlFfnSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['jtl.ffn.config'].create({
            'name': 'Sec FFN',
            'client_id': 'client',
            'client_secret': 'secret',
            'refresh_token': 'refresh',
        })
        cls.plain_user = new_test_user(
            cls.env, login='ffn_plain', groups='base.group_user')
        cls.ffn_user = new_test_user(
            cls.env, login='ffn_user',
            groups='base.group_user,jtl_ffn_merchant_connector.group_jtl_ffn_user')
        cls.ffn_manager = new_test_user(
            cls.env, login='ffn_manager',
            groups='base.group_user,jtl_ffn_merchant_connector.group_jtl_ffn_manager')

    def test_plain_internal_user_has_no_access(self):
        with self.assertRaises(AccessError):
            self.config.with_user(self.plain_user).read(['name'])

    def test_ffn_user_cannot_read_credentials(self):
        config = self.config.with_user(self.ffn_user)
        self.assertEqual(config.name, 'Sec FFN')
        for field in ('client_secret', 'refresh_token', 'access_token'):
            with self.assertRaises(AccessError):
                config.read([field])

    def test_ffn_user_cannot_edit_config(self):
        with self.assertRaises(AccessError):
            self.config.with_user(self.ffn_user).write({'name': 'Changed'})

    def test_manager_has_full_access(self):
        config = self.config.with_user(self.ffn_manager)
        self.assertEqual(config.client_secret, 'secret')
        config.write({'name': 'Changed'})
        self.assertEqual(self.config.name, 'Changed')
