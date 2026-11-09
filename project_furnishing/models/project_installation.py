# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ProjectInstallation(models.Model):
    _name = 'project.installation'
    _description = 'Furnishing Installation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Installation Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('snagging', 'Snagging'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False)

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        related='project_id.partner_id',
        string='Customer',
        readonly=True,
        store=True
    )
    address = fields.Text(
        string='Site Address',
        compute='_compute_address',
        store=True,
        readonly=False,
        help='Auto-filled from project site address, but can be customized.'
    )
    installer_id = fields.Many2one(
        'res.users',
        string='Lead Installer / Supervisor',
        default=lambda self: self.env.user,
        tracking=True
    )
    team_id = fields.Many2one(
        'project.installation.team',
        string='Installation Team',
        tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        related='project_id.company_id',
        store=True,
        readonly=False
    )
    start_date = fields.Date(
        string='Installation Start Date',
        default=fields.Date.context_today,
        tracking=True
    )
    completion_date = fields.Date(
        string='Completion Date',
        tracking=True
    )
    notes = fields.Html(string='Installation Notes & Scope')
    snag_ids = fields.One2many(
        'project.installation.snag',
        'installation_id',
        string='Snag List'
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('project.installation') or _('New')
        return super().create(vals_list)

    @api.depends('project_id', 'project_id.site_address')
    def _compute_address(self):
        for rec in self:
            if rec.project_id and rec.project_id.site_address:
                rec.address = rec.project_id.site_address
            elif not rec.address:
                rec.address = False

    @api.onchange('team_id')
    def _onchange_team_id(self):
        if self.team_id and self.team_id.leader_id and not self.installer_id:
            self.installer_id = self.team_id.leader_id

    def action_start(self):
        for rec in self:
            rec.state = 'in_progress'

    def action_snagging(self):
        for rec in self:
            rec.state = 'snagging'

    def action_complete(self):
        for rec in self:
            rec.state = 'completed'
            if not rec.completion_date:
                rec.completion_date = fields.Date.context_today(self)

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'


class ProjectInstallationSnag(models.Model):
    _name = 'project.installation.snag'
    _description = 'Installation Snag Item'
    _order = 'sequence, id'

    installation_id = fields.Many2one(
        'project.installation',
        string='Installation',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    is_fixed = fields.Boolean(string='Fixed', default=False)

