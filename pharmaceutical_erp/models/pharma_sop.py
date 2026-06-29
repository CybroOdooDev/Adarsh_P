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


class PharmaSop(models.Model):
    """Standard Operating Procedure (SOP) — created manually by a document author. When the SOP reaches Effective
    status the system auto-generates pharma.training records for every employee whose HR job role is linked to this SOP."""
    _name = 'pharma.sop'
    _description = 'Standard Operating Procedure'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'sop_code'
    _order = 'sop_code desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='SOP Title',
        required=True,
        copy=False,
        tracking=True,
        help='Descriptive title of this Standard Operating Procedure.',
    )

    sop_code = fields.Char(
        string='SOP Code',
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help='Auto-generated unique SOP reference code (e.g. SOP/0001).',
    )

    version = fields.Integer(
        string='Version',
        default=1,
        required=True,
        copy=False,
        tracking=True,
        help='Auto-increments each time an archived SOP is revised and approved again.',
    )

    # ── Document ──────────────────────────────────────────────────────────────
    document = fields.Binary(
        string='SOP Document',
        attachment=True,
        help='Upload the SOP file (PDF, DOCX, etc.).',
    )

    filename = fields.Char(
        string='Filename',
        help='Original filename of the uploaded SOP document.',
    )

    # ── Workflow State ────────────────────────────────────────────────────────
    status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('review', 'Under Review'),
            ('effective', 'Effective'),
            ('archived', 'Archived'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        help='Workflow state of this SOP. Only Effective SOPs can be linked to BMR steps.',
    )

    # ── People ────────────────────────────────────────────────────────────────
    author_id = fields.Many2one(
        comodel_name='res.users',
        string='Author',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        help='Creator of this SOP. The author cannot approve their own SOP.',
    )

    reviewer_id = fields.Many2one(
        comodel_name='res.users',
        string='Reviewer',
        tracking=True,
        help='User who reviewed the SOP before it was submitted for QA approval.',
    )

    approved_by = fields.Many2one(
        comodel_name='res.users',
        string='Approved By',
        copy=False,
        tracking=True,
        help='QA approver. Must be a different user from the author.',
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    effective_date = fields.Date(
        string='Effective Date',
        copy=False,
        tracking=True,
        help='Date from which this SOP version is active and usable.',
    )

    review_due_date = fields.Date(
        string='Review Due Date',
        tracking=True,
        help='Periodic review date — the SOP should be re-evaluated before this date.',
    )

    # ── Assigned Employees ────────────────────────────────────────────────────
    employee_ids = fields.Many2many(
        comodel_name='hr.employee',
        relation='pharma_sop_employee_rel',
        column1='sop_id',
        column2='employee_id',
        string='Assigned Employees',
        help='Employees who must be trained on this SOP. '
             'When the SOP reaches Effective status, one training record '
             'is created for each employee listed here.',
    )

    employee_count = fields.Integer(
        string='Assigned Employees',
        compute='_compute_employee_count',
            help='Specifies the Assigned Employees for this record.',
    )

    # ── Training Records ──────────────────────────────────────────────────────
    training_ids = fields.One2many(
        comodel_name='pharma.training',
        inverse_name='sop_id',
        string='Training Records',
        help='Auto-generated training records for assigned employees.',
    )

    training_count = fields.Integer(
        string='Training Count',
        compute='_compute_training_count',
            help='Specifies the Training Count for this record.',
    )

    notes = fields.Text(
        string='Notes',
        help='Additional remarks, change history summary, or cross-references.',
    )

    # ── Computes ──────────────────────────────────────────────────────────────
    @api.depends('employee_ids')
    def _compute_employee_count(self):
        """Calculates the total number of employees assigned to this SOP."""
        for rec in self:
            rec.employee_count = len(rec.employee_ids)

    @api.depends('training_ids')
    def _compute_training_count(self):
        """Calculates the total number of training records associated with this SOP."""
        for rec in self:
            rec.training_count = len(rec.training_ids)

    # ── ORM Override — auto-assign SOP Code on create ─────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        """
        Assign a sequential SOP Code from ir.sequence on every new record.
        The sequence 'pharma.sop.sequence' must exist in pharma_sequences.xml.
        Pattern:  SOP/0001, SOP/0002, …
        """
        for vals in vals_list:
            if vals.get('sop_code', _('New')) == _('New'):
                vals['sop_code'] = self.env['ir.sequence'].next_by_code(
                    'pharma.sop.sequence'
                ) or _('New')
        return super().create(vals_list)

    # ── Constraints ───────────────────────────────────────────────────────────
    # @api.constrains('author_id', 'approved_by')
    # def _check_author_approver(self):
    #     for rec in self:
    #         if rec.approved_by and rec.author_id == rec.approved_by:
    #             raise ValidationError(
    #                 _('The SOP author cannot approve their own SOP. '
    #                   'Please assign a different user as the approver.')
    #             )

    @api.constrains('employee_ids')
    def _check_employee_ids(self):
        for rec in self:
            if not rec.employee_ids:
                raise ValidationError(_("Assigned Employees is a required field. You must assign at least one employee to the SOP."))

    @api.constrains('status', 'approved_by', 'effective_date')
    def _check_effective_fields(self):
        """Validates that an Approved By user and Effective Date are provided when marking the SOP as Effective."""
        for rec in self:
            if rec.status == 'effective' and not (
                    rec.approved_by and rec.effective_date):
                raise ValidationError(
                    _('Approved By and Effective Date are required when '
                      'setting the SOP status to Effective.')
                )

    # ── Workflow Actions ──────────────────────────────────────────────────────
    def action_submit_review(self):
        """Transitions the SOP state to 'Under Review' to begin the QA approval process."""
        self.write({'status': 'review'})

    def action_approve(self):
        """
        QA approver marks the SOP as Effective.
        - Sets approved_by, effective_date (today if not already set).
        - Triggers auto-generation of training records for applicable employees.
        """
        for rec in self:
            vals = {
                'status': 'effective',
                'approved_by': self.env.user.id,
            }
            if not rec.effective_date:
                vals['effective_date'] = fields.Date.today()
            rec.write(vals)
            rec._generate_training_records()

    def action_archive_sop(self):
        """Changes the SOP status to 'Archived', indicating it is no longer active."""
        self.write({'status': 'archived'})

    def action_revise(self):
        """
        Start a new revision cycle from an Archived SOP.
        Increments the version number and resets state to Draft so the
        revised SOP can go through the full review / approval process again.
        """
        for rec in self:
            rec.write({
                'status': 'draft',
                'version': rec.version + 1,
                'approved_by': False,
                'effective_date': False,
            })

    def action_reset_draft(self):
        """Reverts the SOP status back to 'Draft' for further editing without creating a new version."""
        self.write({'status': 'draft'})

    # ── Training Auto-Generation ──────────────────────────────────────────────
    def _generate_training_records(self):
        """
        Called when an SOP reaches Effective status.
        Creates one pharma.training record per employee whose HR job role
        is in applicable_job_ids — only if a record does not already exist
        for the same (sop, employee) pair.
        """
        Training = self.env['pharma.training']
        for sop in self:
            if not sop.employee_ids:
                continue
            for employee in sop.employee_ids:
                existing = Training.search([
                    ('sop_id', '=', sop.id),
                    ('employee_id', '=', employee.id),
                ], limit=1)
                if not existing:
                    Training.create({
                        'sop_id': sop.id,
                        'employee_id': employee.id,
                        'status': 'pending',
                    })

    # ── Smart Button ──────────────────────────────────────────────────────────
    def action_view_trainings(self):
        """Returns a window action to display all training records related to this SOP."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Training Records'),
            'res_model': 'pharma.training',
            'view_mode': 'list,form',
            'domain': [('sop_id', '=', self.id)],
            'context': {'default_sop_id': self.id},
        }
