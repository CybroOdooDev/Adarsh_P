# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    furnishing_default_warranty_months = fields.Integer(
        string='Default Warranty Duration (Months)',
        default=12,
        help='Default Defects Liability Period (DLP) / warranty duration in months for new furnishing projects.'
    )
    furnishing_qc_location_id = fields.Many2one(
        'stock.location',
        string='Furnishing Quality Inspection Location',
        domain=[('usage', '=', 'internal')],
        help='Default quarantine holding location for finished manufactured items undergoing Quality Inspection before release to stock.'
    )

    def _get_furnishing_qc_location(self):
        self.ensure_one()
        if self.furnishing_qc_location_id and self.furnishing_qc_location_id.active:
            return self.furnishing_qc_location_id
        warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', self.id)], limit=1)
        parent_loc = warehouse.view_location_id if warehouse else False
        if not parent_loc:
            parent_loc = self.env['stock.location'].sudo().search([
                ('usage', '=', 'view'),
                ('company_id', 'in', (self.id, False)),
            ], limit=1)

        loc = self.env['stock.location'].sudo().search([
            ('name', '=', 'Quality Inspection'),
            ('usage', '=', 'internal'),
            ('company_id', 'in', (self.id, False)),
        ], limit=1)
        if not loc:
            loc_vals = {
                'name': 'Quality Inspection',
                'usage': 'internal',
                'company_id': self.id,
            }
            if parent_loc:
                loc_vals['location_id'] = parent_loc.id
            loc = self.env['stock.location'].sudo().create(loc_vals)
        elif not loc.active:
            loc.sudo().write({'active': True})

        self.sudo().write({'furnishing_qc_location_id': loc.id})
        return loc
