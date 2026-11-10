# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProjectServiceRequest(models.Model):
    _name = 'project.service.request'
    _description = 'Service & Warranty Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Request Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        tracking=True,
        ondelete='cascade',
        index=True,
        domain="[('is_furnishing_project', '=', True), ('state', '!=', 'cancelled')]"
    )
    partner_id = fields.Many2one(
        'res.partner',
        related='project_id.partner_id',
        string='Customer',
        readonly=True,
        store=True
    )
    site_address = fields.Text(
        string='Site Address',
        compute='_compute_site_address',
        store=True,
        readonly=False,
        help='Auto-filled from the project site address, but can be customized.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        related='project_id.company_id',
        store=True,
        readonly=False
    )

    # Warranty Toggle & Project Warranty Details
    is_under_warranty = fields.Boolean(
        string='Under Warranty',
        default=False,
        tracking=True,
        help='Toggle whether this service request is covered under the project warranty or is a billable / paid service.'
    )
    project_has_warranty = fields.Boolean(
        related='project_id.has_warranty',
        string='Project Has Warranty',
        readonly=True
    )
    warranty_end_date = fields.Date(
        related='project_id.warranty_end_date',
        string='Warranty Expiry Date',
        readonly=True
    )

    service_type = fields.Selection([
        ('repair', 'Repair & Rectification'),
        ('replacement', 'Part / Fabric Replacement'),
        ('touch_up', 'Touch-Up & Polishing'),
        ('inspection', 'Inspection & Audit'),
        ('other', 'Other Service'),
    ], string='Service Type', default='repair', required=True, tracking=True)

    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1', tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Visit Scheduled'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False)

    technician_id = fields.Many2one(
        'res.users',
        string='Assigned Technician',
        tracking=True,
        default=lambda self: self.env.user
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        tracking=True
    )
    scheduled_date = fields.Date(
        string='Scheduled Visit Date',
        tracking=True
    )
    resolution_date = fields.Date(
        string='Resolution Date',
        tracking=True
    )

    issue_description = fields.Text(string='Issue / Defect Description')
    resolution_notes = fields.Text(string='Resolution / Work Done')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('project.service.request') or _('New')
        return super().create(vals_list)

    @api.depends('project_id', 'project_id.site_address')
    def _compute_site_address(self):
        for rec in self:
            if rec.project_id and rec.project_id.site_address:
                rec.site_address = rec.project_id.site_address
            elif not rec.site_address:
                rec.site_address = False

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id:
            today = fields.Date.context_today(self)
            self.is_under_warranty = bool(
                self.project_id.has_warranty and
                (not self.project_id.warranty_end_date or self.project_id.warranty_end_date >= today)
            )

    @api.constrains('project_id')
    def _check_project_id(self):
        for rec in self:
            if rec.project_id.is_furnishing_project and rec.project_id.state == 'cancelled':
                raise ValidationError(_("Cannot log service requests for cancelled project '%s'.") % rec.project_id.name)

    def action_schedule(self):
        for rec in self:
            if rec.state not in ('draft', 'scheduled'):
                raise UserError(_("Only draft service requests can be scheduled."))
            if not rec.scheduled_date:
                rec.scheduled_date = fields.Date.context_today(self)
            rec.state = 'scheduled'

    def action_start(self):
        for rec in self:
            if rec.state not in ('draft', 'scheduled'):
                raise UserError(_("Cannot start service request '%s' because it is already %s.") % (rec.name, rec.state))
            rec.state = 'in_progress'

    def action_resolve(self):
        for rec in self:
            if rec.state not in ('draft', 'scheduled', 'in_progress'):
                raise UserError(_("Only service requests in progress or scheduled can be marked as resolved."))
            rec.state = 'resolved'
            if not rec.resolution_date:
                rec.resolution_date = fields.Date.context_today(self)

    def action_cancel(self):
        for rec in self:
            if rec.state == 'resolved':
                raise UserError(_("Resolved service requests cannot be cancelled."))
            rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('cancelled', 'resolved'):
                raise UserError(_("Only cancelled or resolved service requests can be reset to Draft."))
            rec.state = 'draft'
