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
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import JtlFfnCommon


@tagged('post_install', '-at_install')
class TestJtlFfnProductSync(JtlFfnCommon):

    def setUp(self):
        super().setUp()
        self.sync = self.env['jtl.ffn.product.sync']

    def _sync_rec(self):
        return self.sync.search([
            ('config_id', '=', self.config.id),
            ('product_id', '=', self.product.id),
        ])

    def test_push_creates_product(self):
        api = self.patch_api(return_value={'jfsku': 'JF-1'})
        self.sync._push_single_product(self.config, self.product)
        rec = self._sync_rec()
        self.assertEqual(rec.ffn_product_id, 'JF-1')
        self.assertEqual(rec.sync_state, 'synced')
        payload = api.call_args.kwargs['json']
        self.assertEqual(payload['merchantSku'], 'FFN-SKU-1')
        self.assertEqual(payload['identifier'], {'ean': '4006381333931'})
        self.assertEqual(payload['note'], 'Sale description')

    def test_push_updates_existing_product(self):
        self.sync.create({
            'config_id': self.config.id,
            'product_id': self.product.id,
            'ffn_product_id': 'JF-1',
        })
        api = self.patch_api(return_value={})
        self.sync._push_single_product(self.config, self.product)
        self.assertEqual(api.call_args.args[0], 'PATCH')
        self.assertEqual(self._sync_rec().sync_state, 'synced')

    def test_push_recovers_from_stale_jfsku(self):
        rec = self.sync.create({
            'config_id': self.config.id,
            'product_id': self.product.id,
            'ffn_product_id': 'STALE',
        })

        def fake_api(method, path, json=None, params=None):
            if method == 'PATCH' and path.endswith('/STALE'):
                raise UserError(self.env._('Products_ProductNotFound'))
            if method == 'GET':
                return {'items': [{'merchantSku': 'FFN-SKU-1', 'jfsku': 'REAL'}]}
            return {}

        self.patch_api(side_effect=fake_api)
        self.sync._push_single_product(self.config, self.product)
        self.assertEqual(rec.ffn_product_id, 'REAL')
        self.assertEqual(rec.sync_state, 'synced')

    def test_push_stale_jfsku_not_found_anywhere(self):
        self.sync.create({
            'config_id': self.config.id,
            'product_id': self.product.id,
            'ffn_product_id': 'STALE',
        })

        def fake_api(method, path, json=None, params=None):
            if method == 'PATCH':
                raise UserError(self.env._('Products_ProductNotFound'))
            return {'items': []}

        self.patch_api(side_effect=fake_api)
        with self.assertRaises(UserError):
            self.sync._push_single_product(self.config, self.product)

    def test_push_duplicate_product_is_adopted(self):
        def fake_api(method, path, json=None, params=None):
            if method == 'POST':
                raise UserError(self.env._('Products_DuplicateProduct {"Jfsku": "DUP-1"}'))
            return {}

        self.patch_api(side_effect=fake_api)
        self.sync._push_single_product(self.config, self.product)
        rec = self._sync_rec()
        self.assertEqual(rec.ffn_product_id, 'DUP-1')
        self.assertEqual(rec.sync_state, 'synced')

    def test_push_duplicate_product_with_existing_record(self):
        rec = self.sync.create({
            'config_id': self.config.id,
            'product_id': self.product.id,
            'sync_state': 'error',
        })

        def fake_api(method, path, json=None, params=None):
            if method == 'POST':
                raise UserError(self.env._('Products_DuplicateProduct {"Jfsku": "DUP-2"}'))
            return {}

        self.patch_api(side_effect=fake_api)
        self.sync._push_single_product(self.config, self.product)
        self.assertEqual(rec.ffn_product_id, 'DUP-2')

    def test_push_other_errors_are_raised(self):
        self.patch_api(side_effect=UserError('something else'))
        with self.assertRaises(UserError):
            self.sync._push_single_product(self.config, self.product)

    def test_push_existing_record_without_jfsku_posts_again(self):
        rec = self.sync.create({
            'config_id': self.config.id,
            'product_id': self.product.id,
            'sync_state': 'error',
        })
        self.patch_api(return_value={'id': 'JF-9'})
        self.sync._push_single_product(self.config, self.product)
        self.assertEqual(rec.ffn_product_id, 'JF-9')

    def test_find_product_by_sku(self):
        self.patch_api(return_value={
            'items': [{'merchantSku': 'FFN-SKU-1', 'id': 'JF-ID'}]})
        self.assertEqual(
            self.sync._find_ffn_product_by_sku(self.config, 'FFN-SKU-1'), 'JF-ID')
        self.assertIsNone(self.sync._find_ffn_product_by_sku(self.config, 'OTHER'))

    def test_find_product_by_sku_handles_errors(self):
        self.patch_api(side_effect=UserError('down'))
        self.assertIsNone(self.sync._find_ffn_product_by_sku(self.config, 'X'))

    def test_sync_products_records_success_and_failure(self):
        light = self.env['product.product'].create({
            'name': 'Weightless',
            'default_code': 'FFN-NOWEIGHT',
            'type': 'consu',
            'weight': 0,
        })
        self.patch_api(return_value={'jfsku': 'JF-X'})
        pushed = self.sync.sync_products_to_ffn(self.config)
        self.assertGreaterEqual(pushed, 1)
        self.assertEqual(self._sync_rec().sync_state, 'synced')
        failed = self.sync.search([
            ('config_id', '=', self.config.id),
            ('product_id', '=', light.id),
        ])
        self.assertEqual(failed.sync_state, 'error')
        # A second run updates the existing error record instead of creating one.
        self.sync.sync_products_to_ffn(self.config)
        self.assertEqual(self.sync.search_count([
            ('config_id', '=', self.config.id),
            ('product_id', '=', light.id),
        ]), 1)

    def test_pull_stock(self):
        update = self.patch_model('stock.quant', '_update_available_quantity')
        self.patch_api(return_value={'items': [
            {'merchantSku': 'FFN-SKU-1', 'stockLevel': 5},
            {'merchantSku': 'UNKNOWN-SKU', 'stockLevel': 1},
        ]})
        self.sync.create({
            'config_id': self.config.id,
            'product_id': self.product.id,
            'ffn_product_id': 'JF-1',
        })
        updated = self.sync.pull_stock_from_ffn(self.config)
        self.assertEqual(updated, 1)
        update.assert_called_once()
        line = self.env['jtl.ffn.stock.line'].search([
            ('warehouse_id', '=', self.ffn_wh.id),
            ('product_id', '=', self.product.id),
        ])
        self.assertEqual(line.ffn_quantity, 5)
        self.assertTrue(self.ffn_wh.last_sync)
        self.assertTrue(self._sync_rec().last_pulled)

    def test_pull_stock_updates_existing_snapshot(self):
        self.patch_model('stock.quant', '_update_available_quantity')
        self.patch_api(return_value={'items': [
            {'merchantSku': 'FFN-SKU-1', 'stockLevel': 3}]})
        self.sync.pull_stock_from_ffn(self.config)
        self.patch_api(return_value={'inventory': [
            {'sku': 'FFN-SKU-1', 'quantity': 8}]})
        self.sync.pull_stock_from_ffn(self.config)
        lines = self.env['jtl.ffn.stock.line'].search([
            ('warehouse_id', '=', self.ffn_wh.id),
            ('product_id', '=', self.product.id),
        ])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.ffn_quantity, 8)

    def test_pull_stock_swallows_api_errors(self):
        self.patch_api(side_effect=UserError('down'))
        self.assertEqual(self.sync.pull_stock_from_ffn(self.config), 0)

    def test_cron_sync_all(self):
        push = self.patch_model('jtl.ffn.product.sync', 'sync_products_to_ffn')
        pull = self.patch_model('jtl.ffn.product.sync', 'pull_stock_from_ffn')
        self.sync.cron_sync_all()
        self.assertTrue(push.called)
        self.assertTrue(pull.called)

    def test_cron_sync_all_respects_flags(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        self.config.write({'sync_products': False, 'sync_stock': False})
        push = self.patch_model('jtl.ffn.product.sync', 'sync_products_to_ffn')
        pull = self.patch_model('jtl.ffn.product.sync', 'pull_stock_from_ffn')
        self.sync.cron_sync_all()
        push.assert_not_called()
        pull.assert_not_called()

    def test_action_sync_all(self):
        self.patch_model('jtl.ffn.product.sync', 'cron_sync_all')
        action = self.sync.action_sync_all()
        self.assertEqual(action['res_model'], 'jtl.ffn.product.sync')
