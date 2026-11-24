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
from contextlib import suppress

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import JtlFfnCommon


@tagged('post_install', '-at_install')
class TestJtlFfnOrderSync(JtlFfnCommon):

    def setUp(self):
        super().setUp()
        self.sync = self.env['jtl.ffn.order.sync']

    def _record(self, order=None):
        return self.sync.search([
            ('config_id', '=', self.config.id),
            ('sale_order_id', '=', (order or self.order).id),
        ])

    def test_resolve_warehouse_by_country(self):
        de_wh = self.env['jtl.ffn.warehouse'].create({
            'config_id': self.config.id,
            'name': 'DE FFN',
            'odoo_warehouse_id': self.odoo_wh.id,
            'ffn_warehouse_id': 'WH-DE',
            'sequence': 1,
            'route_country_ids': [(6, 0, self.germany.ids)],
        })
        self.assertEqual(self.sync._resolve_warehouse(self.config, self.order), de_wh)

    def test_resolve_warehouse_default_and_fallback(self):
        self.assertEqual(
            self.sync._resolve_warehouse(self.config, self.order), self.ffn_wh)
        self.ffn_wh.is_default = False
        self.assertEqual(
            self.sync._resolve_warehouse(self.config, self.order), self.ffn_wh)

    def test_push_order_success(self):
        self.config.write({
            'fallback_shipping_method_id': 'SHIP-1',
            'fallback_shipping_type': 'Express',
        })
        self.env['jtl.ffn.product.sync'].create({
            'config_id': self.config.id,
            'product_id': self.product.id,
            'ffn_product_id': 'JF-1',
        })
        self.order.note = 'Please be careful'
        api = self.patch_api(return_value={'outboundId': 'OB-123'})
        self.sync._push_order(self.config, self.order)
        rec = self._record()
        self.assertEqual(rec.ffn_order_id, 'OB-123')
        self.assertEqual(rec.push_state, 'sent')
        self.assertEqual(rec.ffn_jfsku, 'JF-1')
        self.assertEqual(rec.warehouse_id, self.ffn_wh)
        payload = api.call_args.kwargs['json']
        self.assertEqual(payload['merchantOutboundNumber'], self.order.name)
        self.assertEqual(payload['warehouseId'], 'WH1')
        self.assertEqual(payload['shippingMethodId'], 'SHIP-1')
        self.assertEqual(payload['shippingType'], 'Express')
        self.assertEqual(payload['shippingAddress']['firstname'], 'John')
        self.assertEqual(payload['shippingAddress']['lastname'], 'Doe')
        self.assertEqual(payload['shippingAddress']['country'], 'DE')
        self.assertEqual(payload['shippingAddress']['extraAddressLine'], 'Apartment 2')
        self.assertEqual(len(payload['items']), 1)

    def test_push_order_updates_existing_record(self):
        rec = self.make_order_sync(push_state='error', ffn_order_id=False)
        self.patch_api(return_value={'id': 'OB-9'})
        self.sync._push_order(self.config, self.order)
        self.assertEqual(rec.ffn_order_id, 'OB-9')
        self.assertEqual(rec.push_state, 'sent')

    def test_push_order_without_ffn_warehouse(self):
        self.ffn_wh.unlink()
        self.sync._push_order(self.config, self.order)
        rec = self._record()
        self.assertEqual(rec.push_state, 'error')
        self.assertEqual(rec.retry_count, 1)
        self.sync._push_order(self.config, self.order)
        self.assertEqual(rec.retry_count, 2)

    def test_push_order_without_shippable_lines(self):
        self.sync._push_order(self.config, self.service_order)
        rec = self._record(self.service_order)
        self.assertEqual(rec.push_state, 'error')
        self.assertEqual(rec.retry_count, 1)
        self.sync._push_order(self.config, self.service_order)
        self.assertEqual(rec.retry_count, 2)

    def test_push_order_api_failure_is_recorded_and_raised(self):
        self.patch_api(side_effect=UserError('API down'))
        with self.assertRaises(UserError):
            self.sync._push_order(self.config, self.order)
        # assertRaises rolls back to a savepoint, so run it a second time by hand.
        with suppress(UserError):
            self.sync._push_order(self.config, self.order)
        rec = self._record()
        self.assertEqual(rec.push_state, 'error')
        self.assertEqual(rec.retry_count, 1)
        with suppress(UserError):
            self.sync._push_order(self.config, self.order)
        self.assertEqual(rec.retry_count, 2)
        self.assertIn('API down', rec.push_error)

    def test_push_pending_orders_filters_orders(self):
        sent = self._create_order(self.product)
        sent.action_confirm()
        exhausted = self._create_order(self.product)
        exhausted.action_confirm()
        self.make_order_sync(order=sent, ffn_order_id='X', push_state='sent')
        self.make_order_sync(
            order=exhausted, ffn_order_id='Y', push_state='error',
            retry_count=self.sync.MAX_RETRIES)
        push = self.patch_model('jtl.ffn.order.sync', '_push_order')
        pushed = self.sync.push_pending_orders(self.config)
        orders = [call.args[1] for call in push.call_args_list]
        self.assertIn(self.order, orders)
        self.assertNotIn(sent, orders)
        self.assertNotIn(exhausted, orders)
        self.assertEqual(pushed, len(orders))

    def test_push_pending_orders_survives_failures(self):
        self.patch_model('jtl.ffn.order.sync', '_push_order',
                         side_effect=UserError('fail'))
        self.assertEqual(self.sync.push_pending_orders(self.config), 0)

    def test_cron_push_orders(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        push = self.patch_model('jtl.ffn.order.sync', 'push_pending_orders')
        self.sync.cron_push_orders()
        push.assert_called_once()
        push.reset_mock()
        self.config.sync_orders = False
        self.sync.cron_push_orders()
        push.assert_not_called()

    def test_action_sync_all(self):
        self.patch_model('jtl.ffn.order.sync', 'cron_push_orders')
        action = self.sync.action_sync_all()
        self.assertEqual(action['res_model'], 'jtl.ffn.order.sync')
