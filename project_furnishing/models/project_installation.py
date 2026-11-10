# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


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
        tracking=True,
        domain="[('is_furnishing_project', '=', True), ('state', 'not in', ('completed', 'cancelled'))]"
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
    line_ids = fields.One2many(
        'project.installation.line',
        'installation_id',
        string='Installation Items'
    )
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

    @api.constrains('project_id')
    def _check_project_id(self):
        for rec in self:
            if rec.project_id.is_furnishing_project and rec.project_id.state in ('completed', 'cancelled'):
                raise ValidationError(
                    _("Cannot create or link installations to project '%(project)s' because the project is %(state)s.") % {
                        'project': rec.project_id.name,
                        'state': dict(rec.project_id._fields['state'].selection).get(rec.project_id.state, rec.project_id.state),
                    }
                )

    @api.onchange('team_id')
    def _onchange_team_id(self):
        if self.team_id and self.team_id.leader_id:
            self.installer_id = self.team_id.leader_id

    def action_start(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft installations can be started."))
            rec.state = 'in_progress'

    def action_snagging(self):
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError(_("Snagging can only be started from an installation 'In Progress'."))
            rec.state = 'snagging'

    def action_complete(self):
        for rec in self:
            if rec.state not in ('in_progress', 'snagging'):
                raise UserError(_("Only installations 'In Progress' or in 'Snagging' can be completed."))
            incomplete_lines = rec.line_ids.filtered(lambda l: not l.is_completed)
            if incomplete_lines:
                item_names = ', '.join(incomplete_lines.mapped('name')[:5])
                if len(incomplete_lines) > 5:
                    item_names += _(" and %s more") % (len(incomplete_lines) - 5)
                raise UserError(
                    _("Cannot complete installation '%(name)s'. The following installation items are not completed: %(items)s.") % {
                        'name': rec.name,
                        'items': item_names,
                    }
                )
            unfixed_snags = rec.snag_ids.filtered(lambda s: not s.is_fixed)
            if unfixed_snags:
                snag_names = ', '.join(unfixed_snags.mapped('name')[:5])
                if len(unfixed_snags) > 5:
                    snag_names += _(" and %s more") % (len(unfixed_snags) - 5)
                raise UserError(
                    _("Cannot complete installation '%(name)s' with unresolved snags: %(snags)s. Please mark all snags as fixed before completing.") % {
                        'name': rec.name,
                        'snags': snag_names,
                    }
                )
            rec.state = 'completed'
            if not rec.completion_date:
                rec.completion_date = fields.Date.context_today(self)

    def action_cancel(self):
        for rec in self:
            if rec.state == 'completed':
                raise UserError(_("Completed installations cannot be cancelled."))
            rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('cancelled', 'completed'):
                raise UserError(_("Only cancelled or completed installations can be reset to Draft."))
            rec.state = 'draft'

    def action_load_survey_lines(self):
        """Populate installation lines from project survey measurements."""
        for rec in self:
            if not rec.project_id:
                raise UserError(_("Please select a project first."))
            surveys = rec.project_id.survey_ids.filtered(lambda s: s.state != 'cancelled')
            if not surveys:
                raise UserError(_("No site surveys found for project '%s'.") % rec.project_id.name)
            measurements = surveys.mapped('measurement_ids')
            if not measurements:
                raise UserError(_("No survey items/measurements recorded in the surveys for project '%s'.") % rec.project_id.name)
            existing_measurement_ids = set(rec.line_ids.mapped('measurement_id').ids)
            new_lines = []
            for m in measurements:
                if m.id not in existing_measurement_ids:
                    new_lines.append((0, 0, {
                        'sequence': m.sequence,
                        'name': m.name,
                        'description': m.description,
                        'type_id': m.type_id.id if m.type_id else False,
                        'measurement_id': m.id,
                        'is_completed': False,
                    }))
            if new_lines:
                rec.write({'line_ids': new_lines})
            elif existing_measurement_ids:
                raise UserError(_("All survey items have already been loaded into this installation."))


class ProjectInstallationLine(models.Model):
    _name = 'project.installation.line'
    _description = 'Installation Item'
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
    type_id = fields.Many2one(
        'project.measurement.type',
        string='Type'
    )
    measurement_id = fields.Many2one(
        'project.site.measurement',
        string='Source Measurement',
        ondelete='set null'
    )
    is_completed = fields.Boolean(
        string='Completed',
        default=False
    )


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

