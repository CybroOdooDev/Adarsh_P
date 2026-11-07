# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FurnishingSiteSurvey(models.Model):
    _name = 'furnishing.site.survey'
    _description = 'Site Survey & Dimension Measurement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Survey Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    project_id = fields.Many2one(
        'furnishing.project',
        string='Project',
        required=True,
        tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        related='project_id.partner_id',
        string='Customer',
        readonly=True,
        store=True
    )
    surveyor_id = fields.Many2one(
        'res.users',
        string='Surveyor / Engineer',
        default=lambda self: self.env.user,
        tracking=True
    )
    survey_date = fields.Datetime(
        string='Survey Date & Time',
        default=fields.Datetime.now,
        tracking=True
    )
    property_type = fields.Selection([
        ('villa', 'Luxury Villa'),
        ('penthouse', 'Penthouse / Apartment'),
        ('commercial', 'Commercial / Corporate Office'),
        ('hospitality', 'Hotel / Restaurant / Hospitality'),
        ('retail', 'Retail Showroom')
    ], string='Property Type', default='villa')
    site_address = fields.Text(
        string='Site Address',
        related='project_id.site_address',
        readonly=False
    )

    # Site Readiness & Logistics
    site_readiness = fields.Selection([
        ('bare_shell', 'Bare Shell / Core'),
        ('civil_work', 'Civil Work In Progress'),
        ('flooring_ready', 'Flooring Sub-base Ready'),
        ('fully_ready', 'Fully Ready for Fit-Out')
    ], string='Site Readiness', default='civil_work', tracking=True)
    ac_operational = fields.Boolean(
        string='AC Operational',
        help='AC must be functional for wood flooring and fabrics.'
    )
    power_available = fields.Boolean(string='Power & Electricity Available')
    access_constraints = fields.Text(string='Logistics & Access Constraints')

    # State & Signatures
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Visit Scheduled'),
        ('in_progress', 'Survey In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    surveyor_signature = fields.Binary(string='Surveyor Signature')
    customer_signature = fields.Binary(string='Customer / Site Contractor Signature')

    # Lines
    line_ids = fields.One2many(
        'furnishing.site.survey.line',
        'survey_id',
        string='Measurement Lines'
    )
    total_floor_area_sqm = fields.Float(
        string='Total Measured Floor Area (m²)',
        compute='_compute_total_floor_area',
        store=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furnishing.site.survey') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.floor_area_sqm')
    def _compute_total_floor_area(self):
        for record in self:
            record.total_floor_area_sqm = sum(record.line_ids.mapped('floor_area_sqm'))

    def action_schedule(self):
        self.write({'state': 'scheduled'})

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_complete(self):
        self.write({'state': 'completed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_create_quotation(self):
        self.ensure_one()
        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'project_id': self.project_id.id,
            'origin': self.name,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generated Quotation'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }


class FurnishingSiteSurveyLine(models.Model):
    _name = 'furnishing.site.survey.line'
    _description = 'Site Survey Room Measurement Line'
    _order = 'id'

    survey_id = fields.Many2one(
        'furnishing.site.survey',
        string='Survey',
        required=True,
        ondelete='cascade'
    )
    room_name = fields.Char(string='Room / Zone Name', required=True)
    room_type_id = fields.Many2one('furnishing.room.type', string='Room Preset')
    floor_level = fields.Selection([
        ('basement', 'Basement'),
        ('ground', 'Ground Floor'),
        ('first', '1st Floor'),
        ('second', '2nd Floor'),
        ('penthouse', 'Penthouse / Rooftop'),
        ('other', 'Other Level')
    ], string='Floor Level', default='ground')
    service_scope = fields.Selection([
        ('flooring', 'Flooring & Carpets'),
        ('curtains', 'Curtains & Drapery'),
        ('wallcovering', 'Wallcoverings & Paint'),
        ('furniture', 'Bespoke Furniture'),
        ('full', 'Full Scope')
    ], string='Primary Scope', default='full', required=True)

    # Flooring & Room Dimensions (meters)
    room_length = fields.Float(string='Length (m)')
    room_width = fields.Float(string='Width (m)')
    room_height = fields.Float(string='Ceiling Height (m)')
    floor_area_sqm = fields.Float(
        string='Area (m²)',
        compute='_compute_floor_area',
        store=True
    )
    skirting_perimeter_lm = fields.Float(
        string='Skirting (lm)',
        compute='_compute_floor_area',
        store=True
    )
    subfloor_condition = fields.Selection([
        ('smooth', 'Smooth Screed (Ready)'),
        ('tiles', 'Existing Tiles (Sound)'),
        ('uneven', 'Uneven - Needs Self-Leveling Screed'),
        ('damp', 'Moisture Detected - Needs DPM Barrier')
    ], string='Subfloor Condition', default='smooth')

    # Window & Curtain Specs (cm)
    window_reference = fields.Char(string='Window Ref (e.g. W1)')
    window_width = fields.Float(string='Window Width (cm)')
    curtain_drop_height = fields.Float(string='Curtain Drop (cm)')
    fixing_type = fields.Selection([
        ('ceiling', 'Ceiling Recess Box'),
        ('wall', 'Wall Mounted'),
        ('pelmet', 'Decorative Pelmet Box')
    ], string='Fixing Type', default='ceiling')
    motorized_curtains = fields.Boolean(string='Motorized Required')
    power_point_ready = fields.Boolean(string='Power Point Ready')

    # Wallcovering Specs (meters)
    wall_width = fields.Float(string='Wall Width (m)')
    wall_height = fields.Float(string='Wall Height (m)')
    wall_deductions_sqm = fields.Float(string='Door/Window Deduction (m²)')
    wall_area_sqm = fields.Float(
        string='Net Wall Area (m²)',
        compute='_compute_wall_area',
        store=True
    )

    special_notes = fields.Text(string='Observations & Obstacles')

    @api.depends('room_length', 'room_width')
    def _compute_floor_area(self):
        for line in self:
            line.floor_area_sqm = line.room_length * line.room_width
            line.skirting_perimeter_lm = 2.0 * (line.room_length + line.room_width) if (line.room_length and line.room_width) else 0.0

    @api.depends('wall_width', 'wall_height', 'wall_deductions_sqm')
    def _compute_wall_area(self):
        for line in self:
            gross = line.wall_width * line.wall_height
            line.wall_area_sqm = max(0.0, gross - line.wall_deductions_sqm)
