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


class PharmaOosInvestigation(models.Model):
    """
    OOS Investigation — tracks investigations when QC results fall out of spec.
    """
    _name = 'pharma.oos.investigation'
    _description = 'OOS Investigation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(
        string='Investigation Number',
        required=True,
        copy=False,
        readonly=True,
        default='/',
            help='Specifies the Investigation Number for this record.',
    )

    result_line_id = fields.Many2one(
        comodel_name='pharma.qc.result.line',
        string='OOS Result Line',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        help='The specific OOS result that triggered this investigation.'
    )

    phase = fields.Selection(
        selection=[
            ('phase_1', 'Phase I'),
            ('phase_2', 'Phase II'),
        ],
        string='Phase',
        default='phase_1',
        required=True,
        tracking=True,
        help='Phase I checks for lab error, Phase II checks the full batch.'
    )

    lab_error_found = fields.Boolean(
        string='Lab Error Found',
        default=False,
        tracking=True,
        help='If True in Phase I, result is invalidated and re-tested.'
    )

    conclusion = fields.Text(
        string='Conclusion',
        tracking=True,
        help='Final conclusion of the investigation.'
    )

    disposition = fields.Selection(
        selection=[
            ('release', 'Release'),
            ('reject', 'Reject'),
        ],
        string='Disposition',
        tracking=True,
        help='Final decision on the batch after investigation.'
    )

    investigated_by = fields.Many2one(
        comodel_name='res.users',
        string='Investigated By',
        tracking=True,
        help='QA person who led the investigation.'
    )

    closed_on = fields.Datetime(
        string='Closed On',
        tracking=True,
        help='Date and time the investigation was formally closed.'
    )

    test_order_id = fields.Many2one(
        comodel_name='pharma.qc.test.order',
        string='Test Order',
        related='result_line_id.test_order_id',
        store=True,
            help='Specifies the Test Order for this record.',
    )

    def action_view_test_order(self):
        """Returns a window action to open the associated QC Test Order form."""
        self.ensure_one()
        if self.test_order_id:
            return {
                'name': 'QC Test Order',
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'pharma.qc.test.order',
                'res_id': self.test_order_id.id,
            }

    def action_escalate_to_phase_2(self):
        """Escalates a Phase I investigation to Phase II when no direct lab error can be confirmed."""
        for rec in self:
            if rec.closed_on:
                raise ValidationError(_("Closed investigations cannot be escalated."))
            if rec.phase != 'phase_1':
                raise ValidationError(_("Only Phase I investigations can be escalated."))
            if rec.lab_error_found:
                raise ValidationError(_("Cannot escalate to Phase II if a lab error was found. Please invalidate and re-test instead."))
            rec.phase = 'phase_2'

    def action_invalidate_retest(self):
        """Invalidates the initial OOS result due to a confirmed lab error, closes Phase I, and permits re-testing."""
        for rec in self:
            if rec.closed_on:
                raise ValidationError(_("This investigation is already closed."))
            if rec.phase != 'phase_1':
                raise ValidationError(_("Invalidation and re-testing can only be triggered in Phase I."))
            if not rec.lab_error_found:
                raise ValidationError(_("You must select 'Lab Error Found' to invalidate and re-test."))
            
            # Invalidate results: reset actual_value to 0.0 and result_entered to False
            rec.result_line_id.write({
                'actual_value': 0.0,
                'result_entered': False,
            })
            
            # Set test order status to in_progress (if under_investigation)
            test_order = rec.result_line_id.test_order_id
            if test_order.status == 'under_investigation':
                # Check if there are other open investigations for this test order
                other_open = self.env['pharma.oos.investigation'].search([
                    ('result_line_id.test_order_id', '=', test_order.id),
                    ('id', '!=', rec.id),
                    ('closed_on', '=', False)
                ])
                if not other_open:
                    test_order.write({'status': 'in_progress'})

            rec.write({
                'investigated_by': self.env.user.id,
                'closed_on': fields.Datetime.now()
            })

    def action_close_investigation(self):
        """Closes a Phase II investigation after confirming the final disposition,
        updating the QC test order status accordingly."""
        for rec in self:
            if rec.closed_on:
                raise ValidationError(_("This investigation is already closed."))
            if rec.phase != 'phase_2':
                raise ValidationError(_("Only Phase II investigations can be closed directly. "
                                        "If Phase I is sufficient, select lab error found or escalate to Phase II."))
            if not rec.conclusion:
                raise ValidationError(_("You must enter a conclusion before closing Phase II."))
            if not rec.disposition:
                raise ValidationError(_("You must enter a disposition before closing Phase II."))
            
            rec.write({
                'investigated_by': self.env.user.id,
                'closed_on': fields.Datetime.now()
            })
            
            # Create a deviation since the OOS is confirmed
            self.env['pharma.deviation'].create({
                'stage': 'qc',
                'classification': 'critical',
                'description': f"OOS Failure — Parameter: {rec.result_line_id.parameter} | Expected: {rec.result_line_id.expected_min} - {rec.result_line_id.expected_max} | Actual: {rec.result_line_id.actual_value or '—'} | Batch: {rec.result_line_id.test_order_id.lot_id.name}",
                'immediate_action': f"OOS investigation {rec.name} confirmed failure. Conclusion: {rec.conclusion or ''}",
                'oos_investigation_id': rec.id,
                'qc_result_id': rec.result_line_id.id,
                'lot_id': rec.result_line_id.test_order_id.lot_id.id,
            })
            
            # Update parent test order status
            test_order = rec.result_line_id.test_order_id
            if test_order:
                # If disposition is reject, set test order to failed
                if rec.disposition == 'reject':
                    test_order.write({'status': 'failed'})
                elif rec.disposition == 'release':
                    # Check if all other OOS investigations for this test order are closed
                    other_open = self.env['pharma.oos.investigation'].search([
                        ('result_line_id.test_order_id', '=', test_order.id),
                        ('id', '!=', rec.id),
                        ('closed_on', '=', False)
                    ])
                    if not other_open:
                        # Also check if any closed investigations were rejected
                        other_failed = self.env['pharma.oos.investigation'].search([
                            ('result_line_id.test_order_id', '=', test_order.id),
                            ('id', '!=', rec.id),
                            ('disposition', '=', 'reject'),
                            ('lab_error_found', '=', False)
                        ])
                        if other_failed:
                            test_order.write({'status': 'failed'})
                        else:
                            # Test order stays under investigation until the deviation closes
                            test_order.write({'status': 'under_investigation'})

    @api.constrains('closed_on', 'disposition')
    def _check_close(self):
        """Validates that Phase II closures have a disposition set, while allowing Phase I lab-error closures without one."""
        for rec in self:
            if rec.closed_on and not rec.disposition:
                # Phase I lab-error closures (action_invalidate_retest) do not
                # require a disposition — only Phase II closures do.  Allow the
                # Phase I path through so that invalidate_retest can close without
                # forcing the user to pick a disposition.
                if rec.phase == 'phase_2':
                    raise ValidationError(
                        _("A Phase II investigation must have a disposition before it can be closed.")
                    )

    @api.model_create_multi
    def create(self, vals_list):
        """Overrides creation to assign a sequential OOS investigation number."""
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('pharma.oos.investigation') or '/'
        return super().create(vals_list)

    def write(self, vals):
        """Overrides write to prevent modifications to restricted fields once the investigation is closed."""
        for rec in self:
            if rec.closed_on:
                restricted_fields = ('result_line_id', 'lab_error_found', 'phase', 'conclusion', 'disposition')
                if any(f in vals for f in restricted_fields):
                    raise ValidationError(_("Cannot modify details of a closed OOS investigation."))
        return super().write(vals)
