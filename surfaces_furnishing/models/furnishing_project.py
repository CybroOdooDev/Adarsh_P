# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class FurnishingProject(models.Model):
    _name = 'furnishing.project'
    _description = 'Furnishing and Fit-Out Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Project Title',
        required=True,
        tracking=True,
        default=lambda self: _('New Project')
    )
    code = fields.Char(
        string='Project Reference',
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True
    )
    stage_id = fields.Many2one(
        'furnishing.stage',
        string='Stage',
        tracking=True,
        group_expand='_read_group_stage_ids',
        default=lambda self: self._default_stage_id()
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True
    )
    user_id = fields.Many2one(
        'res.users',
        string='Project Manager',
        default=lambda self: self.env.user,
        tracking=True
    )
    surveyor_id = fields.Many2one(
        'res.users',
        string='Site Surveyor / Engineer',
        tracking=True
    )
    designer_id = fields.Many2one(
        'res.users',
        string='3D Designer / Stylist',
        tracking=True
    )
    property_type = fields.Selection([
        ('villa', 'Luxury Villa'),
        ('penthouse', 'Penthouse / Apartment'),
        ('commercial', 'Commercial / Corporate Office'),
        ('hospitality', 'Hotel / Restaurant / Hospitality'),
        ('retail', 'Retail Showroom')
    ], string='Property Type', default='villa', required=True, tracking=True)
    site_address = fields.Text(string='Site Location / Address')
    target_completion_date = fields.Date(string='Target Handover Date', tracking=True)
    actual_handover_date = fields.Date(string='Actual Handover Date', tracking=True)

    # Site Readiness Checkpoints
    site_ac_operational = fields.Boolean(
        string='AC / Climate Operational',
        help='HVAC/AC must be running before wood flooring or delicate fabrics are delivered/installed.'
    )
    site_civil_completed = fields.Boolean(
        string='Civil & Painting Completed',
        help='Plastering, painting, and major wet trades must be finished to avoid dust damage.'
    )
    site_cleaning_done = fields.Boolean(string='Deep Cleaning Done')
    site_access_approved = fields.Boolean(
        string='Service Elevator & Gate Pass Approved',
        help='Community/Building permits and loading bay bookings verified.'
    )

    # Financials & Profitability
    estimated_budget = fields.Monetary(string='Estimated Budget', currency_field='currency_id')
    total_quoted_amount = fields.Monetary(
        string='Total Quoted Revenue',
        compute='_compute_financials',
        currency_field='currency_id',
        store=True
    )
    total_cost_amount = fields.Monetary(
        string='Total Actual Cost',
        compute='_compute_financials',
        currency_field='currency_id',
        store=True
    )
    profit_margin = fields.Monetary(
        string='Profit Margin',
        compute='_compute_financials',
        currency_field='currency_id',
        store=True
    )
    profit_margin_percentage = fields.Float(
        string='Margin %',
        compute='_compute_financials',
        store=True
    )

    # Warranty & DLP
    has_warranty = fields.Boolean(
        string='Warranty / DLP Applicable',
        default=True,
        tracking=True,
        help='Toggle whether this project includes a Defects Liability Period (DLP) or warranty coverage.'
    )
    warranty_start_date = fields.Date(string='Warranty Start Date')
    warranty_end_date = fields.Date(string='Warranty Expiry Date')
    retention_amount = fields.Monetary(
        string='Retention Held',
        currency_field='currency_id',
        help='Amount held by customer during Defects Liability Period (DLP).'
    )
    retention_release_date = fields.Date(string='Retention Due Date')
    warranty_notes = fields.Text(string='Warranty & Guarantee Terms')

    # Relations
    survey_ids = fields.One2many('furnishing.site.survey', 'project_id', string='Site Surveys')
    submittal_ids = fields.One2many('furnishing.material.submittal', 'project_id', string='Material Submittals')
    snag_ids = fields.One2many('furnishing.snag', 'project_id', string='Snags')
    order_ids = fields.One2many('sale.order', 'project_id', string='Sales Orders')
    purchase_ids = fields.One2many('purchase.order', 'project_id', string='Procurement & Subcontractor Orders')
    maintenance_ids = fields.One2many('furnishing.maintenance', 'project_id', string='Maintenance Tickets')

    # Smart Counts
    survey_count = fields.Integer(compute='_compute_counts')
    submittal_count = fields.Integer(compute='_compute_counts')
    snag_count = fields.Integer(compute='_compute_counts')
    open_snag_count = fields.Integer(compute='_compute_counts', search='_search_open_snag_count')
    sale_order_count = fields.Integer(compute='_compute_counts')
    purchase_order_count = fields.Integer(compute='_compute_counts')
    maintenance_count = fields.Integer(compute='_compute_counts')

    def _search_open_snag_count(self, operator, value):
        if operator in ('>', '!=') and value == 0:
            return [('snag_ids.state', 'in', ('open', 'in_progress'))]
        elif operator in ('=', '<=') and value == 0:
            return [('snag_ids.state', 'not in', ('open', 'in_progress'))]
        return []

    def _default_stage_id(self):
        return self.env['furnishing.stage'].search([], limit=1, order='sequence, id')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return self.env['furnishing.stage'].search([], order='sequence, id')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('furnishing.project') or _('New')
        return super().create(vals_list)

    @api.depends('survey_ids', 'submittal_ids', 'snag_ids', 'snag_ids.state', 'order_ids', 'purchase_ids', 'maintenance_ids')
    def _compute_counts(self):
        for project in self:
            project.survey_count = len(project.survey_ids)
            project.submittal_count = len(project.submittal_ids)
            project.snag_count = len(project.snag_ids)
            project.open_snag_count = len(project.snag_ids.filtered(lambda s: s.state in ('open', 'in_progress')))
            project.sale_order_count = len(project.order_ids)
            project.purchase_order_count = len(project.purchase_ids)
            project.maintenance_count = len(project.maintenance_ids)

    @api.depends('order_ids.amount_total', 'order_ids.state', 'purchase_ids.amount_total', 'purchase_ids.state')
    def _compute_financials(self):
        for project in self:
            confirmed_sales = project.order_ids.filtered(lambda s: s.state in ('sale', 'done'))
            revenue = sum(confirmed_sales.mapped('amount_total')) if confirmed_sales else sum(project.order_ids.mapped('amount_total'))
            confirmed_purchases = project.purchase_ids.filtered(lambda p: p.state in ('purchase', 'done'))
            cost = sum(confirmed_purchases.mapped('amount_total')) if confirmed_purchases else sum(project.purchase_ids.mapped('amount_total'))
            
            project.total_quoted_amount = revenue
            project.total_cost_amount = cost
            project.profit_margin = revenue - cost
            project.profit_margin_percentage = (project.profit_margin / revenue * 100.0) if revenue > 0 else 0.0

    def action_view_surveys(self):
        self.ensure_one()
        action = self.env.ref('surfaces_furnishing.action_furnishing_site_survey').read()[0]
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id, 'default_partner_id': self.partner_id.id}
        return action

    def action_view_submittals(self):
        self.ensure_one()
        action = self.env.ref('surfaces_furnishing.action_furnishing_material_submittal').read()[0]
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id, 'default_partner_id': self.partner_id.id}
        return action

    def action_view_snags(self):
        self.ensure_one()
        action = self.env.ref('surfaces_furnishing.action_furnishing_snags').read()[0]
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id}
        return action

    def action_view_sale_orders(self):
        self.ensure_one()
        action = self.env.ref('sale.action_quotations_with_onboarding').read()[0]
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id, 'default_partner_id': self.partner_id.id}
        return action

    def action_view_purchase_orders(self):
        self.ensure_one()
        action = self.env.ref('purchase.purchase_form_action').read()[0]
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id}
        return action

    def action_view_maintenance(self):
        self.ensure_one()
        action = self.env.ref('surfaces_furnishing.action_furnishing_maintenance').read()[0]
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id, 'default_partner_id': self.partner_id.id}
        return action

    def action_create_survey(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Site Survey'),
            'res_model': 'furnishing.site.survey',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_property_type': self.property_type,
            }
        }

    def action_create_quotation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Quotation'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }

    def action_complete_handover(self):
        self.ensure_one()
        if self.open_snag_count > 0:
            raise ValidationError(
                _("Cannot complete handover! There are still %s unresolved snags. Please rectify all defects first.") % self.open_snag_count
            )
        today = fields.Date.today()
        self.write({
            'actual_handover_date': today,
            'warranty_start_date': today,
            'warranty_end_date': today + timedelta(days=365),
            'retention_release_date': today + timedelta(days=180),
        })
        handover_stage = self.env['furnishing.stage'].search([('stage_type', '=', 'completed')], limit=1)
        if handover_stage:
            self.stage_id = handover_stage.id
        return True
