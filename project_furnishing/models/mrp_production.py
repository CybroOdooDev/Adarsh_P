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

    @api.depends('bom_id', 'sale_line_id.order_id.project_id', 'origin')
    def _compute_project_id(self):
        super()._compute_project_id()
        for production in self:
            if not production.project_id:
                if hasattr(production, 'sale_line_id') and production.sale_line_id and production.sale_line_id.order_id.project_id:
                    production.project_id = production.sale_line_id.order_id.project_id
                elif production.origin:
                    so = self.env['sale.order'].search([('name', '=', production.origin)], limit=1)
                    if so and so.project_id:
                        production.project_id = so.project_id

    def _update_furnishing_qc_location(self):
        for prod in self:
            if prod.project_id and prod.project_id.is_furnishing_project and prod.state not in ('done', 'cancel'):
                company = prod.company_id or prod.project_id.company_id or self.env.company
                qc_loc = company._get_furnishing_qc_location()
                if qc_loc and prod.location_dest_id != qc_loc:
                    prod.location_dest_id = qc_loc.id
                    moves_to_update = prod.move_finished_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
                    if moves_to_update:
                        moves_to_update.write({'location_dest_id': qc_loc.id})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            project_id = vals.get('project_id')
            if project_id and not vals.get('location_dest_id'):
                project = self.env['project.project'].browse(project_id)
                if project.is_furnishing_project:
                    company = project.company_id or self.env.company
                    qc_loc = company._get_furnishing_qc_location()
                    if qc_loc:
                        vals['location_dest_id'] = qc_loc.id
        productions = super().create(vals_list)
        productions._update_furnishing_qc_location()
        for prod in productions:
            if prod.project_id and prod.project_id.is_furnishing_project and not prod.quality_check_ids:
                prod._create_furnishing_quality_check()
        return productions

    def write(self, vals):
        res = super().write(vals)
        if 'project_id' in vals:
            self._update_furnishing_qc_location()
        if 'project_id' in vals or vals.get('state') == 'done':
            for prod in self:
                if prod.project_id and prod.project_id.is_furnishing_project and not prod.quality_check_ids:
                    prod._create_furnishing_quality_check()
        return res

    def _create_furnishing_quality_check(self):
        self.ensure_one()
        template = self.env['furnishing.quality.check.template'].search([
            ('active', '=', True),
            ('stage', 'in', ('pre_dispatch', 'all')),
        ], order='sequence, id', limit=1)

        vals = {
            'production_id': self.id,
            'project_id': self.project_id.id,
            'product_id': self.product_id.id,
            'product_qty': self.product_qty or 1.0,
            'stage': 'pre_dispatch',
            'state': 'draft',
            'company_id': self.company_id.id or self.project_id.company_id.id or self.env.company.id,
        }
        if template:
            vals['template_id'] = template.id
        return self.env['furnishing.quality.check'].create(vals)

    def action_view_quality_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('project_furnishing.action_furnishing_quality_check')
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {
            'default_production_id': self.id,
            'default_product_id': self.product_id.id if self.product_id else False,
            'default_product_qty': self.product_qty or 1.0,
            'default_project_id': self.project_id.id if self.project_id else False,
        }
        if len(self.quality_check_ids) == 1:
            form_view_id = self.env.ref('project_furnishing.view_furnishing_quality_check_form').id
            action['views'] = [(form_view_id, 'form')]
            action['res_id'] = self.quality_check_ids.id
        return action

    def action_create_quality_check(self):
        self.ensure_one()
        if self.state == 'cancel':
            raise UserError(_(
                "A quality check cannot be created for cancelled manufacturing orders. "
                "Order '%s' is currently cancelled."
            ) % self.name)

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
                'default_project_id': self.project_id.id if self.project_id else False,
            },
        }
