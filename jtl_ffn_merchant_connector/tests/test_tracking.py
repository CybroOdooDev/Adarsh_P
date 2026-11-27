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
from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import JtlFfnCommon


@tagged('post_install', '-at_install')
class TestJtlFfnTracking(JtlFfnCommon):

    def setUp(self):
        super().setUp()
        self.tracking = self.env['jtl.ffn.tracking']
        self.order_sync = self.make_order_sync()
        # Validating a real delivery needs stock moves; the tracking logic only
        # needs to know that validation was requested.
        self.validate = self.patch_model(
            'stock.picking', 'button_validate',
            side_effect=lambda: self.picking.write({'state': 'done'}))

    def test_sequence_reference(self):
        rec = self.tracking.create({'config_id': self.config.id})
        self.assertNotEqual(rec.name, 'New')

    def test_apply_tracking_from_list(self):
        self.patch_api(return_value=[{
            'outboundShippingNotificationId': 'SN-1',
            'trackingNumber': 'TRK-1',
            'carrierName': 'DHL Express',
            'trackingUrl': 'https://track.example.com/TRK-1',
        }])
        applied = self.tracking._fetch_and_apply_tracking(self.config, self.order_sync)
        self.assertEqual(applied, 1)
        rec = self.tracking.search([('order_sync_id', '=', self.order_sync.id)])
        self.assertEqual(rec.state, 'applied')
        self.assertEqual(rec.tracking_number, 'TRK-1')
        self.assertEqual(rec.picking_id, self.picking)
        self.assertEqual(self.picking.carrier_tracking_ref, 'TRK-1')
        self.assertEqual(self.picking.carrier_id.name, 'DHL Express')
        self.assertEqual(self.order_sync.push_state, 'shipped')
        self.assertTrue(self.validate.called)

    def test_delivery_left_open_keeps_tracking_new(self):
        self.validate.side_effect = None
        self.patch_api(return_value=[{
            'outboundShippingNotificationId': 'SN-4', 'trackingNumber': 'TRK-5'}])
        self.assertEqual(
            self.tracking._fetch_and_apply_tracking(self.config, self.order_sync), 1)
        rec = self.tracking.search([('order_sync_id', '=', self.order_sync.id)])
        self.assertEqual(rec.state, 'new')
        self.assertEqual(self.picking.carrier_tracking_ref, 'TRK-5')

    def test_apply_tracking_from_dict_and_deduplicate(self):
        self.patch_api(return_value={'shippingNotifications': [{
            'outboundShippingNotificationId': 'SN-2',
            'trackingNumber': 'TRK-2',
        }]})
        self.assertEqual(
            self.tracking._fetch_and_apply_tracking(self.config, self.order_sync), 1)
        self.assertEqual(
            self.tracking._fetch_and_apply_tracking(self.config, self.order_sync), 0)

    def test_iso_shipping_date_is_stored_in_utc(self):
        self.patch_api(return_value=[{
            'outboundShippingNotificationId': 'SN-3',
            'trackingNumber': 'TRK-4',
            'shippedAt': '2026-05-01T10:30:00.000+02:00',
        }])
        self.assertEqual(
            self.tracking._fetch_and_apply_tracking(self.config, self.order_sync), 1)
        rec = self.tracking.search([('order_sync_id', '=', self.order_sync.id)])
        self.assertEqual(rec.shipped_at, datetime(2026, 5, 1, 8, 30))
        self.assertEqual(rec.state, 'applied')

    def test_shipment_without_identifiers_is_skipped(self):
        self.patch_api(return_value={'shipments': [{'carrierName': 'DHL'}]})
        self.assertEqual(
            self.tracking._fetch_and_apply_tracking(self.config, self.order_sync), 0)

    def test_shipment_without_picking_stays_new(self):
        order_sync = self.make_order_sync(
            order=self.service_order, ffn_order_id='OB-NOPICK')
        self.patch_api(return_value=[{'shipmentId': 'S-9'}])
        self.assertEqual(
            self.tracking._fetch_and_apply_tracking(self.config, order_sync), 1)
        rec = self.tracking.search([('order_sync_id', '=', order_sync.id)])
        self.assertEqual(rec.state, 'new')
        self.assertFalse(rec.picking_id)

    def test_find_or_create_carrier(self):
        self.assertFalse(self.tracking._find_or_create_carrier(''))
        first = self.tracking._find_or_create_carrier('Parcel Fast')
        second = self.tracking._find_or_create_carrier('Parcel Fast')
        self.assertTrue(first)
        self.assertEqual(first, second)

    def test_pull_tracking_numbers(self):
        self.patch_api(return_value=[{
            'outboundShippingNotificationId': 'SN-3',
            'trackingNumber': 'TRK-3',
        }])
        self.assertEqual(self.tracking.pull_tracking_numbers(self.config), 1)

    def test_pull_tracking_numbers_swallows_errors(self):
        self.patch_api(side_effect=UserError('down'))
        self.assertEqual(self.tracking.pull_tracking_numbers(self.config), 0)

    def test_cron_pull_tracking(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        pull = self.patch_model('jtl.ffn.tracking', 'pull_tracking_numbers')
        self.tracking.cron_pull_tracking()
        pull.assert_called_once()
        pull.reset_mock()
        self.config.sync_tracking = False
        self.tracking.cron_pull_tracking()
        pull.assert_not_called()

    def test_action_sync_all(self):
        self.patch_model('jtl.ffn.tracking', 'cron_pull_tracking')
        action = self.tracking.action_sync_all()
        self.assertEqual(action['res_model'], 'jtl.ffn.tracking')
