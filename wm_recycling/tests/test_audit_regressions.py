#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestRecyclingAuditRegressions(TransactionCase):
    """Regression tests for recycling defects confirmed by the 2026-10 ERP audit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_bool('wm_collection.use_batch_approval', False)
        cls.env['ir.config_parameter'].sudo().set_bool('wm_collection.use_batch_inspection', False)
        cls.uom_unit = cls.env.ref('uom.product_uom_unit')
        cls.warehouse = cls.env['stock.warehouse'].create({'name': 'Audit Recycling WH', 'code': 'AURW'})
        cls.location = cls.warehouse.lot_stock_id
        cls.material = cls.env['product.product'].create({
            'name': 'Audit PET Flakes', 'is_waste_material': True, 'type': 'consu',
            'is_storable': True, 'uom_id': cls.uom_unit.id,
        })
        cls.output_bin = cls.env['stock.location'].create({'name': 'Audit Output Bin', 'usage': 'internal'})

    def _on_hand(self, location):
        return sum(self.env['stock.quant'].search([
            ('product_id', '=', self.material.id), ('location_id', 'child_of', location.id),
        ]).mapped('quantity'))

    # AUD-050: each reserved move line was set to the full consumed quantity
    def test_consumption_split_across_quants_is_not_multiplied(self):
        # Older stock of the same material in a sub-location of the batch
        # location makes the consumption reservation span two quants.
        shelf = self.env['stock.location'].create({
            'name': 'Audit Shelf', 'usage': 'internal', 'location_id': self.location.id})
        self.env['stock.quant']._update_available_quantity(self.material, shelf, 30.0)

        batch = self.env['waste.batch'].create({
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'line_ids': [(0, 0, {'product_id': self.material.id, 'quantity': 100.0})],
        })
        batch.action_receive_batch()
        batch.action_move_to_stock()
        self.assertAlmostEqual(self._on_hand(self.location), 130.0)

        order = self.env['recycling.order'].create({
            'waste_batch_id': batch.id,
            'line_ids': [(0, 0, {
                'product_id': self.material.id,
                'uom_id': self.uom_unit.id,
                'dest_location_id': self.output_bin.id,
                'expected_qty': 100.0,
                'recovered_qty': 60.0,
            })],
        })
        order.action_confirm()
        order.action_start()
        order.action_done()

        # 100 in: 60 recovered + 40 residue leave the warehouse; the 30 older units stay.
        self.assertAlmostEqual(self._on_hand(self.location), 30.0)
        self.assertAlmostEqual(self._on_hand(self.output_bin), 60.0)
        negative = self.env['stock.quant'].search([
            ('product_id', '=', self.material.id), ('quantity', '<', 0),
            ('location_id.usage', '=', 'internal')])
        self.assertFalse(negative, "No negative internal quants")

    # H5: Recycling mass balance with explicit residual_qty and exceeding input check
    def test_recycling_residual_mass_balance_and_exceeded_check(self):
        batch = self.env['waste.batch'].create({
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'line_ids': [(0, 0, {'product_id': self.material.id, 'quantity': 100.0})],
        })
        batch.action_receive_batch()
        batch.action_move_to_stock()

        order = self.env['recycling.order'].create({
            'waste_batch_id': batch.id,
            'residual_qty': 15.0,
            'line_ids': [(0, 0, {
                'product_id': self.material.id,
                'uom_id': self.uom_unit.id,
                'dest_location_id': self.output_bin.id,
                'expected_qty': 100.0,
                'recovered_qty': 80.0,
            })],
        })
        # 100 input - 80 recovered - 15 residual = 5 unaccounted loss
        self.assertAlmostEqual(order.unaccounted_loss_qty, 5.0)

        self.assertFalse(order.process_loss_warning, "5% loss is within tolerance")

        # The notice follows the stored totals: over-recovery, then a large loss
        order.residual_qty = 30.0
        self.assertIn('exceeds input batch weight', order.process_loss_warning)
        order.residual_qty = 0.0
        order.line_ids.recovered_qty = 50.0  # 50% unaccounted
        self.assertIn('exceeds standard 15% tolerance', order.process_loss_warning)

        # Reading the notice does not recompute the stored totals
        order.flush_recordset()
        order.invalidate_recordset()
        with patch.object(type(order), '_compute_totals', autospec=True) as compute_totals:
            self.assertIn('exceeds standard 15% tolerance', order.process_loss_warning)
        compute_totals.assert_not_called()
        self.assertAlmostEqual(order.unaccounted_loss_qty, 50.0)
        self.assertAlmostEqual(order.total_recovered_qty, 50.0)

        # When recovered + residual exceeds input, error is raised
        order.line_ids.recovered_qty = 80.0
        order.residual_qty = 30.0  # 80 + 30 = 110 > 100
        order.action_confirm()
        order.action_start()
        with self.assertRaises(UserError):
            order.action_done()
