# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FurnishingMaterialSubmittal(models.Model):
    _name = 'furnishing.material.submittal'
    _description = 'Material and Sample Submittal Approval'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Submittal Reference',
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
    room_name = fields.Char(string='Location / Room Area')
    
    material_name = fields.Char(string='Material / Item Description', required=True, tracking=True)
    material_category = fields.Selection([
        ('fabric', 'Fabric & Upholstery'),
        ('carpet', 'Carpet & Rug'),
        ('flooring', 'Wood / Resilient Flooring'),
        ('wallpaper', 'Wallcovering / Wallpaper'),
        ('leather', 'Leather'),
        ('veneer', 'Wood Veneer & Joinery Finish'),
        ('hardware', 'Drapery Track & Hardware')
    ], string='Material Category', default='fabric', required=True)
    
    supplier_id = fields.Many2one('res.partner', string='Supplier / Mill')
    country_of_origin = fields.Char(string='Country of Origin')
    dye_lot_batch = fields.Char(string='Dye-Lot / Batch Number')
    is_flame_retardant = fields.Boolean(
        string='Flame Retardant (FR Certified)',
        help='Certified under civil defense fire safety standards.'
    )
    technical_specs = fields.Text(string='Technical Specs (GSM, Rub Count, Composition)')
    swatch_photo = fields.Image(string='Physical Swatch / Sample Photo')
    
    status = fields.Selection([
        ('draft', 'Draft Sample'),
        ('submitted', 'Submitted for Approval'),
        ('approved', 'Approved'),
        ('approved_comments', 'Approved with Comments'),
        ('revise', 'Revise & Resubmit'),
        ('rejected', 'Rejected')
    ], string='Approval Status', default='draft', tracking=True)
    
    consultant_name = fields.Char(string='Approving Consultant / Designer')
    approval_date = fields.Date(string='Sign-Off Date')
    consultant_signature = fields.Binary(string='Consultant Stamp / Signature')
    comments = fields.Text(string='Consultant Comments / Modifications')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furnishing.material.submittal') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.write({'status': 'submitted'})

    def action_approve(self):
        self.write({
            'status': 'approved',
            'approval_date': fields.Date.today()
        })

    def action_reject(self):
        self.write({'status': 'rejected'})

    def action_revise(self):
        self.write({'status': 'revise'})
