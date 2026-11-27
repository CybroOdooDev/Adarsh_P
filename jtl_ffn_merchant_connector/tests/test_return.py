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
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.jtl_ffn_return import _parse_iso_date
from .common import JtlFfnCommon


@tagged('post_install', '-at_install')
class TestJtlFfnReturn(JtlFfnCommon):

    def setUp(self):
        super().setUp()
        self.returns = self.env['jtl.ffn.return']

    def _empty_picking(self):
        """A receipt without moves: lets us exercise state handling safely."""
        return self.env['stock.picking'].create({
            'picking_type_id': self.odoo_wh.in_type_id.id,
            'location_id': self.env.ref('stock.stock_location_customers').id,
            'location_dest_id': self.odoo_wh.lot_stock_id.id,
        })

    def _ffn_return(self, **extra):
        data = {
            'returnId': 'R-1',
            'outboundId': 'OB1',
            'modificationInfo': {'createdAt': '2026-05-01T10:30:00.000Z'},
            'lines': [{
                'merchantSku': 'FFN-SKU-1',
                'quantity': 1,
                'reason': 'Damaged',
                'condition': 'bad',
                'jfsku': 'JF-1',
            }],
        }
        data.update(extra)
        return data

    def test_parse_iso_date(self):
        self.assertIsNone(_parse_iso_date(None))
        self.assertIsNone(_parse_iso_date('not a date'))
        self.assertEqual(
            _parse_iso_date('2026-05-01T10:30:00+02:00'), '2026-05-01 08:30:00')

    def test_sequence_reference(self):
        rec = self.returns.create({'config_id': self.config.id})
        self.assertNotEqual(rec.name, 'New')

    def test_import_return_matched_by_ffn_order_id(self):
        order_sync = self.make_order_sync()
        self.patch_model('jtl.ffn.return', '_create_odoo_return_picking')
        rec = self.returns._import_return(self.config, self._ffn_return())
        self.assertEqual(rec.order_sync_id, order_sync)
        self.assertEqual(rec.sale_order_id, self.order)
        self.assertEqual(rec.return_reason, 'Damaged')
        self.assertEqual(rec.return_date.year, 2026)
        self.assertEqual(len(rec.line_ids), 1)
        self.assertEqual(rec.line_ids.product_id, self.product)
        self.assertEqual(rec.line_ids.condition, 'bad')

    def test_import_return_matched_by_jfsku(self):
        order_sync = self.make_order_sync(ffn_jfsku='JF-0,JF-1')
        self.patch_model('jtl.ffn.return', '_create_odoo_return_picking')
        rec = self.returns._import_return(
            self.config, self._ffn_return(outboundId='UNKNOWN'))
        self.assertEqual(rec.order_sync_id, order_sync)

    def test_import_return_matched_by_sale_order_name(self):
        self.patch_model('jtl.ffn.return', '_create_odoo_return_picking')
        rec = self.returns._import_return(
            self.config, self._ffn_return(outboundId=self.order.name))
        self.assertEqual(rec.sale_order_id, self.order)
        self.assertFalse(rec.order_sync_id)

    def test_import_return_matched_by_sale_order_name_with_order_sync(self):
        order_sync = self.make_order_sync(ffn_order_id='OTHER')
        self.patch_model('jtl.ffn.return', '_create_odoo_return_picking')
        rec = self.returns._import_return(
            self.config, self._ffn_return(outboundId=self.order.name))
        self.assertEqual(rec.order_sync_id, order_sync)

    def test_import_return_without_matching_order(self):
        rec = self.returns._import_return(
            self.config, self._ffn_return(outboundId='NOPE'))
        self.assertFalse(rec.sale_order_id)
        self.assertEqual(rec.ffn_order_id, 'NOPE')

    def test_import_return_creates_picking_when_order_is_known(self):
        self.make_order_sync()
        create = self.patch_model('jtl.ffn.return', '_create_odoo_return_picking')
        self.returns._import_return(self.config, self._ffn_return())
        create.assert_called_once()

    def test_create_picking_without_delivery(self):
        rec = self.returns.create({
            'config_id': self.config.id,
            'sale_order_id': self.order.id,
        })
        rec._create_odoo_return_picking()
        self.assertFalse(rec.odoo_return_picking_id)
        self.assertEqual(rec.state, 'pending')

    def test_create_picking_without_sale_order(self):
        rec = self.returns.create({'config_id': self.config.id})
        self.assertIsNone(rec._create_odoo_return_picking())

    def _deliver_order(self):
        """Validate the delivery of the order (2 units of the product)."""
        self.env['stock.quant']._update_available_quantity(
            self.product, self.odoo_wh.lot_stock_id, 2)
        self.picking.action_assign()
        for move in self.picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        self.picking.button_validate()
        self.assertEqual(self.picking.state, 'done')

    def test_create_picking_from_done_delivery(self):
        """A partial return gives an incoming picking with the returned
        quantity of the product, linked to the delivery."""
        self._deliver_order()
        rec = self.returns.create({
            'config_id': self.config.id,
            'sale_order_id': self.order.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'sku': 'FFN-SKU-1',
                'quantity': 1,
            })],
        })
        rec._create_odoo_return_picking()
        picking = rec.odoo_return_picking_id
        self.assertTrue(picking)
        self.assertEqual(picking.picking_type_code, 'incoming')
        self.assertEqual(picking.return_id, self.picking)
        self.assertEqual(picking.move_ids.product_id, self.product)
        self.assertEqual(picking.move_ids.product_uom_qty, 1)
        self.assertNotEqual(picking.state, 'draft')
        self.assertEqual(rec.state, 'pending')

    def test_return_of_products_not_delivered_creates_no_picking(self):
        self._deliver_order()
        rec = self.returns.create({
            'config_id': self.config.id,
            'sale_order_id': self.order.id,
            'line_ids': [(0, 0, {'sku': 'OTHER-SKU', 'quantity': 1})],
        })
        rec._create_odoo_return_picking()
        self.assertFalse(rec.odoo_return_picking_id)
        self.assertEqual(rec.state, 'pending')
        self.assertFalse(self.picking.return_ids)

    def test_update_from_ffn_data_validates_picking(self):
        rec = self.returns.create({
            'config_id': self.config.id,
            'odoo_return_picking_id': self._empty_picking().id,
        })
        assign = self.patch_model('stock.picking', 'action_assign', return_value=True)
        validate = self.patch_model('stock.picking', 'button_validate', return_value=True)
        rec._update_from_ffn_data({'state': 'Arrived'})
        assign.assert_called_once()
        validate.assert_called_once()

    def test_update_from_ffn_data_by_line_state(self):
        rec = self.returns.create({
            'config_id': self.config.id,
            'odoo_return_picking_id': self._empty_picking().id,
        })
        self.patch_model('stock.picking', 'action_assign', return_value=True)
        validate = self.patch_model('stock.picking', 'button_validate', return_value=True)
        rec._update_from_ffn_data({'state': 'Open', 'items': [{'state': 'Completed'}]})
        validate.assert_called_once()

    def test_update_from_ffn_data_ignores_other_states(self):
        rec = self.returns.create({
            'config_id': self.config.id,
            'odoo_return_picking_id': self._empty_picking().id,
        })
        validate = self.patch_model('stock.picking', 'button_validate', return_value=True)
        rec._update_from_ffn_data({'state': 'Open'})
        validate.assert_not_called()

    def test_update_from_ffn_data_restocks_real_return(self):
        """End to end, without mocks: an 'Arrived' return validates the real
        return picking with the returned quantity and puts it back in stock."""
        self._deliver_order()
        stock = self.odoo_wh.lot_stock_id
        self.assertEqual(self.env['stock.quant']._get_available_quantity(self.product, stock), 0)
        rec = self.returns.create({
            'config_id': self.config.id,
            'sale_order_id': self.order.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'sku': 'FFN-SKU-1',
                'quantity': 1,
            })],
        })
        rec._create_odoo_return_picking()
        picking = rec.odoo_return_picking_id
        self.assertEqual(rec.state, 'pending')

        rec._update_from_ffn_data({'state': 'Arrived'})

        self.assertEqual(picking.state, 'done')
        self.assertEqual(picking.move_ids.quantity, 1)
        self.assertTrue(all(picking.move_ids.mapped('picked')))
        self.assertFalse(picking.backorder_ids)
        self.assertEqual(rec.state, 'restocked')
        self.assertEqual(self.env['stock.quant']._get_available_quantity(self.product, stock), 1)

    def test_update_from_ffn_data_skips_done_picking(self):
        """A return that is already restocked is not validated a second time."""
        self._deliver_order()
        rec = self.returns.create({
            'config_id': self.config.id,
            'sale_order_id': self.order.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'sku': 'FFN-SKU-1',
                'quantity': 1,
            })],
        })
        rec._create_odoo_return_picking()
        rec._update_from_ffn_data({'state': 'Arrived'})
        self.assertEqual(rec.state, 'restocked')
        validate = self.patch_model('stock.picking', 'button_validate', return_value=True)
        rec._update_from_ffn_data({'state': 'Completed'})
        validate.assert_not_called()

    def test_compute_state_follows_picking(self):
        picking = self._empty_picking()
        rec = self.returns.create({'config_id': self.config.id})
        rec.odoo_return_picking_id = picking
        self.assertEqual(rec.state, 'pending')
        picking.write({'state': 'done'})
        self.assertEqual(rec.state, 'restocked')
        picking.write({'state': 'cancel'})
        self.assertEqual(rec.state, 'cancelled')

    def test_compute_state_without_picking(self):
        rec = self.returns.create({'config_id': self.config.id})
        self.assertEqual(rec.state, 'new')

    def test_action_view_picking(self):
        rec = self.returns.create({'config_id': self.config.id})
        with self.assertRaises(UserError):
            rec.action_view_picking()
        picking = self._empty_picking()
        rec.odoo_return_picking_id = picking
        action = rec.action_view_picking()
        self.assertEqual(action['res_id'], picking.id)

    def test_pull_returns_imports_and_updates(self):
        self.make_order_sync()
        self.patch_model('jtl.ffn.return', '_create_odoo_return_picking')
        self.patch_api(return_value={'items': [self._ffn_return(), {'noId': True}]})
        self.assertEqual(self.returns.pull_returns(self.config), 1)
        # A second pull finds the existing record and only updates it.
        self.assertEqual(self.returns.pull_returns(self.config), 0)
        self.assertEqual(self.returns.search_count([
            ('config_id', '=', self.config.id), ('ffn_return_id', '=', 'R-1')]), 1)

    def test_pull_returns_accepts_plain_list(self):
        self.patch_api(return_value=[self._ffn_return(returnId='R-2', outboundId='X')])
        self.assertEqual(self.returns.pull_returns(self.config), 1)

    def test_pull_returns_swallows_import_errors(self):
        self.patch_model('jtl.ffn.return', '_import_return', side_effect=UserError('x'))
        self.patch_api(return_value={'items': [self._ffn_return()]})
        self.assertEqual(self.returns.pull_returns(self.config), 0)

    def test_pull_returns_swallows_update_errors(self):
        self.returns.create({
            'config_id': self.config.id,
            'ffn_return_id': 'R-1',
        })
        self.patch_model(
            'jtl.ffn.return', '_update_from_ffn_data', side_effect=UserError('x'))
        self.patch_api(return_value={'items': [self._ffn_return()]})
        self.assertEqual(self.returns.pull_returns(self.config), 0)

    def test_cron_pull_returns(self):
        self.env['jtl.ffn.config'].search([('id', '!=', self.config.id)]).write(
            {'is_active': False})
        pull = self.patch_model('jtl.ffn.return', 'pull_returns')
        self.returns.cron_pull_returns()
        pull.assert_called_once()
        pull.reset_mock()
        self.config.sync_returns = False
        self.returns.cron_pull_returns()
        pull.assert_not_called()

    def test_action_sync_all(self):
        self.patch_model('jtl.ffn.return', 'cron_pull_returns')
        action = self.returns.action_sync_all()
        self.assertEqual(action['res_model'], 'jtl.ffn.return')
