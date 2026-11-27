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
import json
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.jtl_ffn_merchant_connector.controllers import webhook as webhook_ctrl

PS = 'odoo.addons.jtl_ffn_merchant_connector.models.jtl_ffn_product_sync.JtlFfnProductSync'
TR = 'odoo.addons.jtl_ffn_merchant_connector.models.jtl_ffn_tracking.JtlFfnTracking'
RT = 'odoo.addons.jtl_ffn_merchant_connector.models.jtl_ffn_return.JtlFfnReturn'


@tagged('post_install', '-at_install')
class TestJtlFfnWebhook(HttpCase):
    """The public webhook must never trust its payload."""

    def setUp(self):
        super().setUp()
        webhook_ctrl._last_trigger.clear()
        self.config = self.env['jtl.ffn.config'].create({
            'name': 'Webhook Profile',
            'environment': 'sandbox',
            'client_id': 'cid',
            'client_secret': 'csec',
            'refresh_token': 'rtoken',
            'is_active': True,
        })
        self.odoo_wh = self.env['stock.warehouse'].search([], limit=1)
        self.ffn_wh = self.env['jtl.ffn.warehouse'].create({
            'config_id': self.config.id,
            'name': 'Webhook WH',
            'odoo_warehouse_id': self.odoo_wh.id,
            'ffn_warehouse_id': 'WH-1',
            'is_default': True,
        })
        self.product = self.env['product.product'].create({
            'name': 'Webhook Product',
            'type': 'consu',
            'is_storable': True,
            'default_code': 'WH-SKU',
        })

    def _post(self, payload, config_id=None):
        return self.url_open(
            '/jtl_ffn/webhook/%d' % (config_id or self.config.id),
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
        )

    def _qty(self):
        return self.env['stock.quant']._get_available_quantity(
            self.product, self.odoo_wh.lot_stock_id)

    # -- forged data must be ignored ------------------------------------
    def test_forged_stock_payload_does_not_change_stock(self):
        before = self._qty()
        with patch(PS + '.pull_stock_from_ffn', return_value=0):
            res = self._post({
                'event': 'stock.updated', 'warehouseId': 'WH-1',
                'items': [{'merchantSku': 'WH-SKU', 'quantity': 99999}],
            })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._qty(), before)

    def test_forged_shipped_payload_creates_nothing(self):
        n_tracking = self.env['jtl.ffn.tracking'].search_count([])
        with patch(TR + '.pull_tracking_numbers', return_value=0):
            self._post({'event': 'order.shipped', 'outboundId': 'X1',
                        'trackingNumber': 'EVIL', 'trackingUrl': 'http://evil'})
        self.assertEqual(self.env['jtl.ffn.tracking'].search_count([]), n_tracking)

    def test_forged_return_payload_creates_nothing(self):
        n_returns = self.env['jtl.ffn.return'].search_count([])
        with patch(RT + '.pull_returns', return_value=0):
            self._post({'event': 'return.received', 'returnId': 'R-EVIL',
                        'items': [{'merchantSku': 'WH-SKU', 'quantity': 5}]})
        self.assertEqual(self.env['jtl.ffn.return'].search_count([]), n_returns)

    # -- webhook triggers an authenticated pull -------------------------
    def test_events_trigger_matching_pull(self):
        cases = [
            ('stock.updated', PS + '.pull_stock_from_ffn'),
            ('order.shipped', TR + '.pull_tracking_numbers'),
            ('return.registered', RT + '.pull_returns'),
        ]
        for event, target in cases:
            webhook_ctrl._last_trigger.clear()
            with patch(target, return_value=0) as mocked:
                self._post({'event': event})
            self.assertEqual(mocked.call_count, 1, event)

    def test_respects_config_sync_flags(self):
        self.config.sync_stock = False
        with patch(PS + '.pull_stock_from_ffn', return_value=0) as mocked:
            self._post({'event': 'stock.updated'})
        mocked.assert_not_called()

    def test_debounce(self):
        with patch(PS + '.pull_stock_from_ffn', return_value=0) as mocked:
            for _i in range(5):
                self._post({'event': 'stock.updated'})
        self.assertEqual(mocked.call_count, 1)

    # -- no information leak / robustness -------------------------------
    def test_same_response_for_unknown_and_known_config(self):
        known = self._post({'event': 'nothing'}).json()
        unknown = self._post({'event': 'nothing'}, config_id=99999999).json()
        self.assertEqual(known.get('result'), unknown.get('result'))

    def test_inactive_config_does_nothing(self):
        self.config.is_active = False
        with patch(PS + '.pull_stock_from_ffn', return_value=0) as mocked:
            self._post({'event': 'stock.updated'})
        mocked.assert_not_called()

    def test_failing_pull_does_not_break_response(self):
        with patch(PS + '.pull_stock_from_ffn', side_effect=RuntimeError('boom')):
            res = self._post({'event': 'stock.updated'})
        self.assertEqual(res.status_code, 200)

    def test_garbage_payload(self):
        """A body that is not a JSON object, or a non-string event, must
        never trigger a sync."""
        with patch(PS + '.pull_stock_from_ffn', return_value=0) as mocked:
            res = self.url_open('/jtl_ffn/webhook/%d' % self.config.id,
                                data='[1,2,3]',
                                headers={'Content-Type': 'application/json'})
            self.assertIn(res.status_code, (200, 400))
            res = self._post({'event': {'nested': 'stock.updated'}})
            self.assertEqual(res.status_code, 200)
        mocked.assert_not_called()
