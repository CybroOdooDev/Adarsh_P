# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    quality_check_ids = fields.One2many(
        'furnishing.quality.check',
        'production_id',
        string='Furnishing Quality Checks'
    )
    quality_check_count = fields.Integer(
        string='Quality Checks Count',
        compute='_compute_quality_check_count'
    )

    @api.depends('quality_check_ids')
    def _compute_quality_check_count(self):
        for order in self:
            order.quality_check_count = len(order.quality_check_ids)

    def action_view_quality_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('project_furnishing.action_furnishing_quality_check')
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {
            'default_production_id': self.id,
            'default_product_id': self.product_id.id if self.product_id else False,
            'default_product_qty': self.product_qty or 1.0,
            'default_project_id': self.project_id.id if hasattr(self, 'project_id') and self.project_id else False,
        }
        if len(self.quality_check_ids) == 1:
            form_view_id = self.env.ref('project_furnishing.view_furnishing_quality_check_form').id
            action['views'] = [(form_view_id, 'form')]
            action['res_id'] = self.quality_check_ids.id
        return action

    def action_create_quality_check(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_(
                "A quality check can only be created for completed manufacturing orders. "
                "Order '%s' is currently in '%s' state."
            ) % (
                self.name,
                dict(self._fields['state'].selection).get(self.state, self.state)
            ))

        form_view_id = self.env.ref('project_furnishing.view_furnishing_quality_check_form').id
        return {
            'name': _('Create Quality Check'),
            'type': 'ir.actions.act_window',
            'res_model': 'furnishing.quality.check',
            'view_mode': 'form',
            'views': [(form_view_id, 'form')],
            'target': 'current',
            'context': {
                'default_production_id': self.id,
                'default_product_id': self.product_id.id if self.product_id else False,
                'default_product_qty': self.product_qty or 1.0,
                'default_stage': 'pre_dispatch',
                'default_project_id': self.project_id.id if hasattr(self, 'project_id') and self.project_id else False,
            },
        }
