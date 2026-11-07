# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FurnishingSnag(models.Model):
    _name = 'furnishing.snag'
    _description = 'Site Installation Snag and Defect'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Snag Reference',
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
    room_type_id = fields.Many2one('furnishing.room.type', string='Room / Zone Preset')
    location_detail = fields.Char(
        string='Specific Location',
        required=True
    )
    defect_type_id = fields.Many2one('furnishing.snag.type', string='Defect Category', required=True)
    description = fields.Text(string='Defect Description', required=True)
    
    photo = fields.Image(string='Defect Photo (Proof)')
    rectification_photo = fields.Image(string='Rectification Photo (After Fix)')
    
    severity = fields.Selection([
        ('minor', 'Minor Cosmetic'),
        ('medium', 'Noticeable Flaw'),
        ('critical', 'Critical (Blocks Handover)')
    ], string='Severity', default='medium', required=True, tracking=True)
    
    responsible_trade = fields.Char(string='Responsible Subcontractor / Trade')
    assigned_to_id = fields.Many2one('res.users', string='Assigned Technician / Lead')
    
    reported_date = fields.Date(string='Reported Date', default=fields.Date.today)
    target_date = fields.Date(string='Target Resolution Date')
    resolved_date = fields.Date(string='Resolution Date', readonly=True)
    
    state = fields.Selection([
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Rectified'),
        ('verified', 'Verified & Cleared')
    ], string='Status', default='open', tracking=True)
    
    resolution_notes = fields.Text(string='Resolution Action Taken')

    @api.onchange('defect_type_id')
    def _onchange_defect_type_id(self):
        if self.defect_type_id and self.defect_type_id.default_trade:
            self.responsible_trade = self.defect_type_id.default_trade

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furnishing.snag') or _('New')
        return super().create(vals_list)

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_resolve(self):
        self.write({
            'state': 'resolved',
            'resolved_date': fields.Date.today()
        })

    def action_verify(self):
        self.write({'state': 'verified'})

    def action_reopen(self):
        self.write({'state': 'open', 'resolved_date': False})
