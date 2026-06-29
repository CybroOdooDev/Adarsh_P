# -*- coding: utf-8 -*-
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

from odoo import api, fields, models

class StockLot(models.Model):
    """Extends stock.lot with pharma lot status, expiry, and QA traceability. Lots with status Quarantine, Rejected,
    On Hold, or Recalled are blocked from being issued to production or dispatched to customers."""
    _inherit = 'stock.lot'
    lot_status = fields.Selection(
        selection=[
            ('quarantine', 'Quarantine'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('on_hold', 'On Hold'),
            ('released', 'Released (FG)'),
            ('recalled', 'Recalled'),
        ],
        string='Lot Status',
        default='quarantine',
        required=True,
        tracking=True,
        index=True,
        help='Controls which operations are permitted for this lot. '
             'Quarantine/Rejected/On Hold/Recalled lots are blocked from '
             'production and dispatch.',
    )
    status_changed_by = fields.Many2one(
        comodel_name='res.users',
        string='Status Changed By',
        copy=False,
        tracking=True,
            help='Specifies the Status Changed By for this record.',
    )

    status_changed_on = fields.Datetime(
        string='Status Changed On',
        copy=False,
        tracking=True,
            help='Specifies the Status Changed On for this record.',
    )
    expiry_date = fields.Date(
        string='Expiry Date',
        tracking=True,
        help='Expiry date of this lot, calculated from manufacture date and shelf life.',
    )

    manufacture_date = fields.Date(
        string='Manufacture Date',
        tracking=True,
            help='Specifies the Manufacture Date for this record.',
    )

    retest_date = fields.Date(
        string='Re-test Date',
        tracking=True,
        help='Date by which this lot must be re-tested for continued use.',
    )
    qc_test_count = fields.Integer(
        string='QC Tests',
        compute='_compute_qc_test_count',
        help='Specifies the QC Tests for this record.',
    )

    def _compute_qc_test_count(self):
        """Calculates the number of Quality Control Test Orders associated with this lot."""
        for lot in self:
            lot.qc_test_count = self.env['pharma.qc.test.order'].search_count([('lot_id', '=', lot.id)])

    def action_view_qc_tests(self):
        """Returns a window action to display all QC Test Orders linked to this lot."""
        self.ensure_one()
        return {
            'name': 'QC Test Orders',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'pharma.qc.test.order',
            'domain': [('lot_id', '=', self.id)],
            'context': {'default_lot_id': self.id},
        }
    vendor_coa = fields.Binary(
        string="Vendor CoA",
        attachment=True,
        help="Vendor's Certificate of Analysis attached at goods receipt.",
    )

    vendor_coa_filename = fields.Char(
        string='CoA Filename',

            help='Specifies the CoA Filename for this record.',
    )

    vendor_lot_number = fields.Char(
        string="Vendor's Lot Number",
        help="The lot/batch number as printed on the vendor's label or CoA.",
        tracking=True,
    )
    disposition_remarks = fields.Text(
        string='Disposition Remarks',
        tracking=True,
        help='QA justification for releasing, rejecting, or holding this lot.',
    )
    produced_production_ids = fields.Many2many('mrp.production', compute='_compute_genealogy',
                                               string='Production Orders',
                                               help='Specifies the Production Orders for this record.')
    consumed_lot_ids = fields.Many2many('stock.lot', compute='_compute_genealogy',
                                        string='Raw Material Lots',
                                        help='Specifies the Raw Material Lots for this record.')
    vendor_ids = fields.Many2many('res.partner', compute='_compute_genealogy', string='Vendors',
                                  help='Specifies the Vendors for this record.')
    purchase_order_ids = fields.Many2many('purchase.order', compute='_compute_genealogy',
                                          string='Purchase Orders',
                                          help='Specifies the Purchase Orders for this record.')
    
    delivery_order_ids = fields.Many2many('stock.picking', compute='_compute_genealogy',
                                          string='Delivery Orders',
                                          help='Specifies the Delivery Orders for this record.')
    customer_ids = fields.Many2many('res.partner', compute='_compute_genealogy',
                                    string='Customers', help='Specifies the Customers for this record.')
    invoice_ids = fields.Many2many('account.move', compute='_compute_genealogy',
                                   string='Customer Invoices', help='Specifies the Customer Invoices for this record.')

    qc_test_ids = fields.Many2many('pharma.qc.test.order', compute='_compute_genealogy',
                                   string='QC Test Orders', help='Specifies the QC Test Orders for this record.')
    incoming_qc_ids = fields.Many2many('pharma.qc.test.order', compute='_compute_genealogy_qc', string='Incoming QC')
    ipqc_ids = fields.Many2many('pharma.qc.test.order', compute='_compute_genealogy_qc', string='IPQC')
    fg_qc_ids = fields.Many2many('pharma.qc.test.order', compute='_compute_genealogy_qc', string='FG QC')
    bmr_ids = fields.Many2many('pharma.bmr', compute='_compute_genealogy',
                               string='BMRs', help='Specifies the BMRs for this record.')
    deviation_ids = fields.Many2many('pharma.deviation', compute='_compute_genealogy',
                                     string='Deviations', help='Specifies the Deviations for this record.')
    capa_ids = fields.Many2many('pharma.capa', compute='_compute_genealogy',
                                string='CAPAs', help='Specifies the CAPAs for this record.')
    oos_investigation_ids = fields.Many2many('pharma.oos.investigation', compute='_compute_genealogy',
                                             string='OOS Investigations',
                                             help='Specifies the OOS Investigations for this record.')
    coa_ids = fields.Many2many('pharma.coa', compute='_compute_genealogy',
                               string='Certificates of Analysis',
                               help='Specifies the Certificates of Analysis for this record.')

    def _compute_genealogy(self):
        """Compiles the complete backward and forward traceability data for this lot, including related production
         orders, consumed raw materials, purchase orders, sales deliveries, and quality records."""
        for lot in self:
            # 1. Productions that produced this lot
            produced_sml = self.env['stock.move.line'].search([
                ('lot_id', '=', lot.id),
                ('production_id', '!=', False)
            ])
            productions = produced_sml.mapped('production_id')
            lot.produced_production_ids = productions

            # 2. Raw material lots consumed by these productions
            if productions:
                raw_sml = self.env['stock.move.line'].search([
                    ('move_id.raw_material_production_id', 'in', productions.ids),
                    ('lot_id', '!=', False),
                    ('state', '=', 'done')
                ])
                consumed_lots = raw_sml.mapped('lot_id') - lot
            else:
                consumed_lots = self.env['stock.lot']
            lot.consumed_lot_ids = consumed_lots

            # 3. POs and Vendors for this lot + consumed lots
            all_lots = lot + consumed_lots
            if all_lots:
                incoming_sml = self.env['stock.move.line'].search([
                    ('lot_id', 'in', all_lots.ids),
                    ('picking_id.picking_type_id.code', '=', 'incoming'),
                    ('state', '=', 'done')
                ])
                purchases = incoming_sml.mapped('move_id.purchase_line_id.order_id')
                vendors = purchases.mapped('partner_id')
            else:
                purchases = self.env['purchase.order']
                vendors = self.env['res.partner']
            lot.purchase_order_ids = purchases
            lot.vendor_ids = vendors
            # 1. Delivery Orders
            outgoing_sml = self.env['stock.move.line'].search([
                ('lot_id', '=', lot.id),
                ('picking_id.picking_type_id.code', '=', 'outgoing'),
                ('state', '=', 'done')
            ])
            deliveries = outgoing_sml.mapped('picking_id')
            lot.delivery_order_ids = deliveries
            
            # 2. Customers
            lot.customer_ids = deliveries.mapped('partner_id')
            
            # 3. Invoices
            if hasattr(deliveries, 'sale_id'):
                sales = deliveries.mapped('sale_id')
                invoices = sales.mapped('invoice_ids')
            else:
                invoices = self.env['account.move']
            lot.invoice_ids = invoices
            lot.qc_test_ids = self.env['pharma.qc.test.order'].search([('lot_id', '=', lot.id)])
            lot.oos_investigation_ids = self.env['pharma.oos.investigation'].search([('result_line_id.test_order_id.lot_id', '=', lot.id)])
            lot.coa_ids = self.env['pharma.coa'].search([('lot_id', '=', lot.id)])
            lot.bmr_ids = self.env['pharma.bmr'].search([('production_id', 'in', productions.ids)])
            lot.deviation_ids = self.env['pharma.deviation'].search(['|', ('batch_id', 'in', productions.ids), ('lot_id', '=', lot.id)])
            lot.capa_ids = self.env['pharma.capa'].search([('deviation_id', 'in', lot.deviation_ids.ids)])

    def _compute_genealogy_qc(self):
        """Splits QC tests into categories based on stage for genealogy view."""
        for lot in self:
            lot.incoming_qc_ids = lot.qc_test_ids.filtered(lambda q: q.stage == 'incoming')
            lot.ipqc_ids = lot.qc_test_ids.filtered(lambda q: q.stage == 'in_process')
            lot.fg_qc_ids = lot.qc_test_ids.filtered(lambda q: q.stage in ('finished', 'finished_product'))
    @api.model_create_multi
    def create(self, vals_list):
        """Overrides creation to automatically log the user and timestamp if a lot status is set."""
        for vals in vals_list:
            if vals.get('lot_status'):
                vals['status_changed_by'] = self.env.user.id
                vals['status_changed_on'] = fields.Datetime.now()
        return super().create(vals_list)

    def write(self, vals):
        """Overrides write to automatically log the user and timestamp whenever the lot status changes."""
        if 'lot_status' in vals:
            vals['status_changed_by'] = self.env.user.id
            vals['status_changed_on'] = fields.Datetime.now()
        return super().write(vals)
    def action_approve_lot(self):
        """Changes the lot status to 'Approved', indicating it is acceptable for use or dispatch."""
        self.write({'lot_status': 'approved'})


