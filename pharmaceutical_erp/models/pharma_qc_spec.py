# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

class PharmaQcSpec(models.Model):
    """QC Specification — one record per product per testing stage. Holds parameter lines (acceptance criteria)
    used by QC test orders. Must be QA-approved before it can be linked to any test order."""
    _name = 'pharma.qc.spec'
    _description = 'QC Specification'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'product_id, stage'
    name = fields.Char(
        string='Specification Name',
        readonly=True,
        copy=False,
        tracking=True,
        default='/',
        help='Specifies the Specification Name for this record.',
    )

    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
            help='Specifies the Product for this record.',
    )

    stage = fields.Selection(
        selection=[
            ('incoming', 'Incoming / Raw Material'),
            ('finished', 'Finished Goods'),
        ],
        string='Testing Stage',
        required=True,
        tracking=True,
            help='Specifies the Testing Stage for this record.',
    )

    pharmacopoeial_ref = fields.Selection(
        selection=[
            ('bp', 'BP'),
            ('usp', 'USP'),
            ('ep', 'EP'),
            ('ip', 'IP'),
            ('inhouse', 'In-House'),
        ],
        string='Pharmacopoeial Reference',
        tracking=True,
            help='Specifies the Pharmacopoeial Reference for this record.',
    )

    version = fields.Char(
        string='Version',
        default='1.0',
        required=True,
        tracking=True,
            help='Specifies the Version for this record.',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('review', 'Under Review'),
            ('approved', 'Approved'),
            ('obsolete', 'Obsolete'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
            help='Specifies the Status for this record.',
    )

    approved_by = fields.Many2one(
        comodel_name='res.users',
        string='Approved By',
        tracking=True,
        readonly=True,
        help='Specifies the Approved By for this record.',
    )

    approval_date = fields.Date(
        string='Approval Date',
        tracking=True,
        readonly=True,
        help='Specifies the Approval Date for this record.',
    )

    effective_date = fields.Date(
        string='Valid Until Date',
        tracking=True,
        help='Date until which this specification version is active and can be used for new test orders.',
    )
    parameter_ids = fields.One2many(
        comodel_name='pharma.qc.spec.line',
        inverse_name='spec_id',
        string='Test Parameters',
            help='Specifies the Test Parameters for this record.',
    )

    notes = fields.Text(

        string='Notes / Sampling Instructions',

            help='Specifies the Notes / Sampling Instructions for this record.',
    )
    _unique_product_stage_version = models.Constraint(
        'UNIQUE(product_id, stage, version)',
        'A specification with this version already exists for this product and stage.',
    )

    @api.constrains('state', 'approved_by', 'approval_date')
    def _check_approval(self):
        """Validates that both an approver and an approval date are provided when a specification is approved."""
        for rec in self:
            if rec.state == 'approved' and not (rec.approved_by and rec.approval_date):
                raise ValidationError(
                    _('Approved By and Approval Date are required when approving a specification.')
                )

    @api.constrains('effective_date')
    def _check_effective_date(self):
        for rec in self:
            if rec.effective_date and rec.effective_date < fields.Date.today():
                raise ValidationError(_("The Valid Until Date cannot be less than today."))

    @api.constrains('parameter_ids')
    def _check_parameter_ids(self):
        for rec in self:
            if not rec.parameter_ids:
                raise ValidationError(_("At least one test parameter is required to save the specification."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                product = self.env['product.template'].browse(vals.get('product_id'))
                stage = vals.get('stage', '')
                seq = self.env['ir.sequence'].next_by_code('pharma.qc.spec') or '/'
                vals['name'] = f"SPEC/{product.name}/{stage}/{seq}".upper()
        return super().create(vals_list)

    def action_submit_review(self):
        """Transitions the specification to the Under Review state."""
        self.write({'state': 'review'})

    def action_approve(self):
        """Approves the specification, logging the current user and date, and makes it available for use."""
        self.write({
            'state': 'approved',
            'approved_by': self.env.user.id,
            'approval_date': fields.Date.today(),
        })

    def action_obsolete(self):
        """Marks the specification as obsolete, preventing its future use in new QC test orders."""
        self.write({'state': 'obsolete'})

    def action_reset_draft(self):
        """Reverts the specification back to Draft state for further editing."""
        self.write({'state': 'draft'})
