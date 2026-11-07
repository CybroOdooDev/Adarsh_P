# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FurnishingMaintenance(models.Model):
    _name = 'furnishing.maintenance'
    _description = 'Furnishing Service and Warranty Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Service Ticket Ref',
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
    request_date = fields.Date(string='Request Date', default=fields.Date.today, tracking=True)
    service_type = fields.Selection([
        ('warranty', 'Warranty Claim (Free of Charge)'),
        ('repair', 'Post-Warranty Repair / Polishing'),
        ('maintenance', 'Routine Maintenance / Inspection'),
        ('curtain_clean', 'Professional Drapery / Carpet Cleaning')
    ], string='Service Type', default='warranty', required=True, tracking=True)
    
    product_id = fields.Many2one(
        'product.product',
        string='Product / Item',
        tracking=True,
        help='Specific product or material related to this service request.'
    )
    product_has_warranty = fields.Boolean(
        string='Product Covered by Warranty',
        compute='_compute_warranty_status',
        store=True,
        help='Indicates if the selected product has warranty enabled.'
    )
    is_under_warranty = fields.Boolean(
        string='Under Warranty Coverage',
        compute='_compute_warranty_status',
        store=True
    )
    technician_id = fields.Many2one('res.users', string='Assigned Specialist / Technician', tracking=True)
    visit_date = fields.Datetime(string='Scheduled Service Visit')
    
    state = fields.Selection([
        ('draft', 'New Request'),
        ('scheduled', 'Visit Scheduled'),
        ('in_progress', 'Work In Progress'),
        ('resolved', 'Resolved / Closed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    issue_description = fields.Text(string='Reported Issue / Defect', required=True)
    resolution_notes = fields.Text(string='Service Resolution Notes')

    @api.depends('project_id.has_warranty', 'project_id.warranty_end_date', 'request_date', 'product_id', 'product_id.has_warranty')
    def _compute_warranty_status(self):
        for ticket in self:
            ticket.product_has_warranty = ticket.product_id.has_warranty if ticket.product_id else True
            # Project level warranty check
            if ticket.project_id and not ticket.project_id.has_warranty:
                ticket.is_under_warranty = False
                continue
            # Product level warranty check
            if ticket.product_id and not ticket.product_id.has_warranty:
                ticket.is_under_warranty = False
                continue
            # Date check
            if ticket.project_id and ticket.project_id.warranty_end_date and ticket.request_date:
                ticket.is_under_warranty = (ticket.request_date <= ticket.project_id.warranty_end_date)
            else:
                ticket.is_under_warranty = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furnishing.maintenance') or _('New')
        return super().create(vals_list)

    def action_schedule(self):
        self.write({'state': 'scheduled'})

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_resolve(self):
        self.write({'state': 'resolved'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
