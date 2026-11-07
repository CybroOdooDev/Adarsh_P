# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    project_id = fields.Many2one(
        'furnishing.project',
        string='Furnishing Project',
        tracking=True,
        index=True
    )
    is_variation = fields.Boolean(
        string='Variation Order (Change Request)',
        help='Check if this quotation represents a scope variation / change order for an existing project.'
    )
    variation_reason = fields.Text(string='Variation Scope Justification')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    room_type_id = fields.Many2one('furnishing.room.type', string='Room / Zone')
    dimension_length = fields.Float(string='Length (m)')
    dimension_width = fields.Float(string='Width (m)')
    waste_percentage = fields.Float(string='Waste %', default=0.0)
    calculated_area_sqm = fields.Float(
        string='Net Area (m²)',
        compute='_compute_calculated_area',
        store=True
    )
    has_warranty = fields.Boolean(
        string='Warranty',
        compute='_compute_warranty_info',
        store=True,
        readonly=False,
        precompute=True,
        help='Indicates if this line item has warranty coverage. Defaults from product but can be adjusted.'
    )
    warranty_duration_months = fields.Integer(
        string='Warranty (Mo.)',
        compute='_compute_warranty_info',
        store=True,
        readonly=False,
        precompute=True,
        help='Warranty period in months.'
    )

    @api.depends('product_id', 'product_template_id')
    def _compute_warranty_info(self):
        for line in self:
            prod = line.product_id or line.product_template_id
            if prod:
                line.has_warranty = prod.has_warranty
                line.warranty_duration_months = prod.warranty_duration_months if prod.has_warranty else 0
            else:
                line.has_warranty = False
                line.warranty_duration_months = 0

    @api.onchange('room_type_id')
    def _onchange_room_type_id(self):
        if self.room_type_id and not self.waste_percentage:
            self.waste_percentage = self.room_type_id.default_waste_percentage

    @api.depends('dimension_length', 'dimension_width', 'waste_percentage')
    def _compute_calculated_area(self):
        for line in self:
            if line.dimension_length and line.dimension_width:
                gross = line.dimension_length * line.dimension_width
                line.calculated_area_sqm = gross * (1.0 + (line.waste_percentage / 100.0))
            else:
                line.calculated_area_sqm = 0.0

    @api.onchange('calculated_area_sqm')
    def _onchange_calculated_area_sqm(self):
        if self.calculated_area_sqm > 0.0:
            self.product_uom_qty = self.calculated_area_sqm
