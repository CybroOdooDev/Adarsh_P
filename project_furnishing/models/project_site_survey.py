# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProjectSiteSurvey(models.Model):
    _name = 'project.site.survey'
    _description = 'Site Survey'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Survey Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Visit Scheduled'),
        ('in_progress', 'In Progress'),
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
        string='Address',
        compute='_compute_address',
        store=True,
        readonly=False,
        help='Auto-filled from the project address, but can be customized.'
    )
    scheduled_date = fields.Date(
        string='Scheduled Date',
        tracking=True,
        help='Date planned for conducting the on-site survey.'
    )
    survey_date = fields.Date(
        string='Survey Date',
        default=fields.Date.context_today,
        tracking=True
    )
    surveyor_id = fields.Many2one(
        'res.users',
        string='Surveyor',
        default=lambda self: self.env.user,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        related='project_id.company_id',
        store=True,
        readonly=False
    )
    notes = fields.Html(string='Notes / Observations')

    measurement_ids = fields.One2many(
        'project.site.measurement',
        'survey_id',
        string='Measurements'
    )
    measurement_count = fields.Integer(
        string='Measurements Count',
        compute='_compute_measurement_count'
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('project.site.survey') or _('New')
        return super().create(vals_list)

    @api.depends('project_id', 'project_id.site_address')
    def _compute_address(self):
        for rec in self:
            if rec.project_id and rec.project_id.site_address:
                rec.address = rec.project_id.site_address
            elif not rec.address:
                rec.address = False

    @api.depends('measurement_ids')
    def _compute_measurement_count(self):
        for rec in self:
            rec.measurement_count = len(rec.measurement_ids)

    @api.constrains('project_id')
    def _check_project_id(self):
        for rec in self:
            if rec.project_id.is_furnishing_project and rec.project_id.state in ('completed', 'cancelled'):
                raise ValidationError(
                    _("Cannot create or link site surveys to project '%(project)s' because the project is %(state)s.") % {
                        'project': rec.project_id.name,
                        'state': dict(rec.project_id._fields['state'].selection).get(rec.project_id.state, rec.project_id.state),
                    }
                )

    # State Navigation Buttons
    def action_schedule(self):
        for rec in self:
            if rec.state not in ('draft', 'scheduled'):
                raise UserError(_("Only draft surveys can be scheduled."))
            if not rec.scheduled_date:
                raise ValidationError(_("Please specify a Scheduled Date before scheduling the visit."))
            rec.state = 'scheduled'

    def action_start(self):
        for rec in self:
            if rec.state not in ('draft', 'scheduled'):
                raise UserError(_("Cannot start survey '%s' because it is already %s.") % (rec.name, rec.state))
            rec.state = 'in_progress'

    def action_complete(self):
        for rec in self:
            if rec.state not in ('draft', 'scheduled', 'in_progress'):
                raise UserError(_("Cannot complete survey '%s' because it is %s.") % (rec.name, rec.state))
            if not rec.measurement_ids:
                raise ValidationError(_("Cannot complete survey '%s' without measurements. Please add at least one measurement line before completing.", rec.name))
            empty = rec.measurement_ids.filtered(lambda m: not m.not_required and m.quantity <= 0)
            if empty:
                raise ValidationError(_(
                    "Cannot complete survey '%(survey)s' because these items have no quantity (check their dimensions and count): %(items)s",
                    survey=rec.name,
                    items=", ".join(empty.mapped('name')),
                ))
            rec.state = 'completed'
            # Advance linked project state to 'design' only if all active surveys for this project are completed
            if rec.project_id and rec.project_id.state in ('to_do', 'survey'):
                pending_surveys = rec.project_id.survey_ids.filtered(
                    lambda s: s.id != rec.id and s.state not in ('completed', 'cancelled')
                )
                if not pending_surveys:
                    rec.project_id.state = 'design'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'completed':
                raise UserError(_("Completed surveys cannot be cancelled."))
            rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('cancelled', 'completed'):
                raise UserError(_("Only cancelled or completed surveys can be reset to Draft."))
            rec.state = 'draft'


class ProjectSiteMeasurement(models.Model):
    _name = 'project.site.measurement'
    _description = 'Site Measurement'
    _order = 'sequence, id'

    survey_id = fields.Many2one(
        'project.site.survey',
        string='Site Survey',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    room = fields.Char(string='Room / Area', index=True, help='e.g. Living Room, Master Bedroom, Reception.')
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    type_id = fields.Many2one(
        'project.measurement.type',
        string='Type',
        required=True
    )
    measure_by = fields.Selection(related='type_id.measure_by', string='Measured By', readonly=True)
    length = fields.Float(string='Length (m)', digits=(16, 2))
    width = fields.Float(string='Width (m)', digits=(16, 2))
    height = fields.Float(string='Height (m)', digits=(16, 2))
    count = fields.Integer(string='Count', default=1)
    quantity = fields.Float(
        string='Quantity',
        compute='_compute_quantity',
        store=True,
        digits=(16, 2),
        help='Calculated from the dimensions according to the measurement type, multiplied by the count.'
    )
    quantity_unit = fields.Char(related='type_id.quantity_unit', string='Unit', readonly=True)
    not_required = fields.Boolean(
        string='Not Required',
        copy=False,
        help='Item will not be installed (client cancelled, descoped, etc.).'
    )
    not_required_reason = fields.Char(string='Reason', copy=False)

    @api.constrains('not_required', 'not_required_reason')
    def _check_not_required_reason(self):
        for rec in self:
            if rec.not_required and not rec.not_required_reason:
                raise ValidationError(_("Please give a reason for excluding '%s'.") % rec.name)

    @api.depends('type_id.measure_by', 'length', 'width', 'height', 'count')
    def _compute_quantity(self):
        for rec in self:
            by = rec.type_id.measure_by
            n = rec.count or 0
            if by == 'area_lw':
                qty = rec.length * rec.width * n
            elif by == 'area_lh':
                qty = rec.length * rec.height * n
            elif by == 'linear':
                qty = rec.length * n
            elif by == 'count':
                qty = n
            else:
                qty = 0.0
            rec.quantity = round(qty, 2)

    @api.constrains('length', 'width', 'height', 'count')
    def _check_non_negative(self):
        for rec in self:
            if rec.length < 0 or rec.width < 0 or rec.height < 0 or rec.count < 0:
                raise ValidationError(_("Measurement '%s': dimensions and count cannot be negative.") % rec.name)

