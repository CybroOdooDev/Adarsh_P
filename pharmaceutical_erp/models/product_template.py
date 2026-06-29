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
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class ProductTemplate(models.Model):
    """Extension of the standard Product Template to include pharmaceutical-specific properties
    such as shelf life and storage conditions."""
    _inherit = 'product.template'
    product_type_pharma = fields.Selection(
        selection=[
            ('api', 'API (Active Pharmaceutical Ingredient)'),
            ('excipient', 'Excipient'),
            ('finished_goods', 'Finished Goods'),
            ('packaging', 'Packaging Material'),
            ('intermediate', 'Intermediate / Bulk'),
        ],
        string='Pharma Material Type',
        help='Classifies this product within the pharmaceutical manufacturing context.',
        tracking=True,
    )

    pharmacopoeial_ref = fields.Selection(
        selection=[
            ('bp', 'BP (British Pharmacopoeia)'),
            ('usp', 'USP (United States Pharmacopeia)'),
            ('ep', 'EP (European Pharmacopoeia)'),
            ('ip', 'IP (Indian Pharmacopoeia)'),
            ('inhouse', 'In-House Specification'),
        ],
        string='Pharmacopoeial Reference',
        help='International standard this product is tested against.',
        tracking=True,
    )


    storage_conditions = fields.Char(
        string='Storage Conditions',
        help='Temperature, light, and humidity conditions (e.g. "Store below 25°C, protect from light").',
        tracking=True,
    )
    drug_license_no = fields.Char(
        string='Drug License No.',
        help='Regulatory license number for this product.',
        tracking=True,
    )

    hsn_code = fields.Char(
        string='HSN Code',
        help='Harmonised System Nomenclature code for customs and GST.',
    )
    avl_ids = fields.One2many(
        comodel_name='pharma.avl',
        inverse_name='product_id',
        string='Approved Vendor List',
        help='Vendors approved by QA to supply this material.',
    )

    avl_count = fields.Integer(
        string='AVL Count',
        compute='_compute_avl_count',
            help='Specifies the AVL Count for this record.',
    )
    qc_spec_ids = fields.One2many(
        comodel_name='pharma.qc.spec',
        inverse_name='product_id',
        string='QC Specifications',
        help='All quality control specifications linked to this product.',
    )

    qc_spec_count = fields.Integer(
        string='QC Spec Count',
        compute='_compute_qc_spec_count',
            help='Specifies the QC Spec Count for this record.',
    )

    has_passed_qc_test = fields.Boolean(
        string='Has Passed QC Test',
        compute='_compute_has_passed_qc_test',
        search='_search_has_passed_qc_test',
        help='Indicates if this product has at least one passed QC test order.'
    )

    has_approved_bom = fields.Boolean(
        string='Has Approved BOM',
        compute='_compute_has_approved_bom',
        search='_search_has_approved_bom',
        help='Indicates if this product has at least one approved Bill of Materials.'
    )

    @api.depends('avl_ids')
    def _compute_avl_count(self):
        """Calculates the number of Approved Vendor List (AVL) entries associated with this product."""
        for rec in self:
            rec.avl_count = len(rec.avl_ids)

    @api.depends('qc_spec_ids')
    def _compute_qc_spec_count(self):
        """Calculates the total number of Quality Control Specifications linked to this product."""
        for rec in self:
            rec.qc_spec_count = len(rec.qc_spec_ids)

    def _compute_has_passed_qc_test(self):
        """Calculates whether this product has at least one passed QC test order."""
        for record in self:
            count = self.env['pharma.qc.test.order'].search_count([
                ('product_id', '=', record.id),
                ('status', '=', 'passed')
            ])
            record.has_passed_qc_test = bool(count)

    def _compute_has_approved_bom(self):
        """Calculates whether this product has an approved Bill of Materials."""
        for record in self:
            count = self.env['mrp.bom'].search_count([
                ('product_tmpl_id', '=', record.id),
                ('formula_status', '=', 'approved')
            ])
            record.has_approved_bom = bool(count)

    def _search_has_passed_qc_test(self, operator, value):
        """Allows searching for products that have at least one passed QC test order."""
        is_true = (operator == '=' and value) or (operator == '!=' and not value) or (operator == 'in' and True in value) or (operator == 'not in' and False in value)
        if is_true:
            tests = self.env['pharma.qc.test.order'].search([('status', '=', 'passed')])
            if not tests:
                return [(0, '=', 1)]
            if self._name == 'product.product':
                return [('product_tmpl_id', 'in', tests.mapped('product_id.id'))]
            return [('id', 'in', tests.mapped('product_id.id'))]
        else:
            tests = self.env['pharma.qc.test.order'].search([('status', '=', 'passed')])
            if not tests:
                return [(1, '=', 1)]
            if self._name == 'product.product':
                return [('product_tmpl_id', 'not in', tests.mapped('product_id.id'))]
            return [('id', 'not in', tests.mapped('product_id.id'))]

    def _search_has_approved_bom(self, operator, value):
        """Allows searching for products with an approved BOM."""
        is_true = (operator == '=' and value) or (operator == '!=' and not value) or (operator == 'in' and True in value) or (operator == 'not in' and False in value)
        if is_true:
            boms = self.env['mrp.bom'].search([('formula_status', '=', 'approved')])
            if not boms:
                return [(0, '=', 1)]
            if self._name == 'product.product':
                return [('product_tmpl_id', 'in', boms.mapped('product_tmpl_id.id'))]
            return [('id', 'in', boms.mapped('product_tmpl_id.id'))]
        boms = self.env['mrp.bom'].search([('formula_status', '=', 'approved')])
        if not boms:
            return [(1, '=', 1)]
        if self._name == 'product.product':
            return [('product_tmpl_id', 'not in', boms.mapped('product_tmpl_id.id'))]
        return [('id', 'not in', boms.mapped('product_tmpl_id.id'))]

    @api.onchange('product_type_pharma')
    def _onchange_product_type_pharma(self):
        """Automatically sets product tracking to 'lot' when a pharmaceutical product type is selected."""
        if self.product_type_pharma:
            self.tracking = 'lot'

    @api.constrains('product_type_pharma', 'tracking')
    def _check_pharma_tracking(self):
        """Ensures that all pharmaceutical products enforce lot/batch tracking."""
        for rec in self:
            if rec.product_type_pharma and rec.tracking != 'lot':
                raise ValidationError(_('Pharmaceutical products must be tracked by lot/batch.'))

