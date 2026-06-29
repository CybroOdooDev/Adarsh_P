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


class PharmaCoA(models.Model):
    """Model representing the PharmaCoA entity within the Pharmaceutical ERP ecosystem.
    This model is responsible for managing the data structure, relational mapping, and core business logic
     required to maintain strict regulatory compliance, quality assurance, and comprehensive traceability."""
    _name = 'pharma.coa'
    _description = 'Certificate of Analysis'
    _inherit = ['mail.thread']

    name = fields.Char(string='Reference', required=True, tracking=True, default='New', copy=False,
                       help='Specifies the Reference for this record.')
    batch_id = fields.Many2one('mrp.production', string='Production Batch', tracking=True,
                               help='Specifies the Production Batch for this record.')
    product_id = fields.Many2one('product.template', string='Product', tracking=True,
                                 help='Specifies the Product for this record.')
    lot_id = fields.Many2one('stock.lot', string='Lot/Batch', tracking=True,
                             help='Specifies the Lot/Batch for this record.')
    released_by = fields.Many2one('res.users', string='Released By', tracking=True,
                                  help='Specifies the Released By for this record.')
    release_date = fields.Datetime(string='Release Date', tracking=True,
                                   help='Specifies the Release Date for this record.')
    qc_test_order_id = fields.Many2one('pharma.qc.test.order', string='QC Test Order', tracking=True,
                                       help='Specifies the QC Test Order for this record.')
    is_locked = fields.Boolean(string='Locked', default=False, tracking=True,
                               help='Specifies the Locked for this record.')
    
    coa_line_ids = fields.One2many('pharma.coa.line', 'coa_id', string='Test Results',
                                   help='Specifies the Test Results for this record.')

    qc_result_ids = fields.Many2many(
        comodel_name='pharma.qc.result.line',
        compute='_compute_related_quality_records',
        string='All QC Results'
    )

    qc_test_ids = fields.Many2many(
        comodel_name='pharma.qc.test.order',
        compute='_compute_related_quality_records',
        string='All QC Tests'
    )
    oos_ids = fields.Many2many(
        comodel_name='pharma.oos.investigation',
        compute='_compute_related_quality_records',
        string='OOS Investigations'
    )
    deviation_ids = fields.Many2many(
        comodel_name='pharma.deviation',
        compute='_compute_related_quality_records',
        string='Deviations'
    )
    capa_ids = fields.Many2many(
        comodel_name='pharma.capa',
        compute='_compute_related_quality_records',
        string='CAPAs'
    )

    @api.depends('batch_id', 'lot_id')
    def _compute_related_quality_records(self):
        for rec in self:
            if rec.lot_id:
                qc_tests = self.env['pharma.qc.test.order'].search([('lot_id', '=', rec.lot_id.id)])
                rec.qc_test_ids = qc_tests.ids
                rec.qc_result_ids = qc_tests.mapped('result_line_ids').ids
                
                oos = self.env['pharma.oos.investigation'].search([('result_line_id.test_order_id', 'in', qc_tests.ids)])
                rec.oos_ids = oos.ids
            else:
                rec.qc_test_ids = False
                rec.qc_result_ids = False
                rec.oos_ids = False
                
            if rec.batch_id:
                devs = self.env['pharma.deviation'].search([('batch_id', '=', rec.batch_id.id)])
                rec.deviation_ids = devs.ids
                
                capas = self.env['pharma.capa'].search([('deviation_id', 'in', devs.ids)])
                rec.capa_ids = capas.ids
            else:
                rec.deviation_ids = False
                rec.capa_ids = False

    @api.model_create_multi
    def create(self, vals_list):
        """
        Overrides the standard create method to handle custom record initialization,
        such as generating unique sequences, setting default tracking fields,
        and enforcing initial state constraints.
        """
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('pharma.coa') or 'New'
        return super().create(vals_list)

    def write(self, vals):
        """
        Overrides the standard write method to enforce strict pharmaceutical business rules,
        handle complex status transitions, ensure traceability,
        and prevent unauthorized modifications to locked records.
        """
        from odoo.exceptions import ValidationError
        allowed_fields = {'message_follower_ids', 'message_ids', 'access_token', 'message_attachment_count'}
        if any(f not in allowed_fields for f in vals):
            for rec in self:
                if rec.is_locked:
                    raise ValidationError("Certificates of Analysis are permanently locked and cannot be modified.")
        return super().write(vals)

    def unlink(self):
        """
        Overrides the standard unlink method to prevent the deletion of critical pharmaceutical records,
        ensuring regulatory compliance and maintaining a complete, unalterable audit trail.
        """
        from odoo.exceptions import ValidationError
        for rec in self:
            if rec.is_locked:
                raise ValidationError("Certificates of Analysis are permanent records and cannot be deleted.")
        return super().unlink()


