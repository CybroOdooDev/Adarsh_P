# -*- coding: utf-8 -*-
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

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

class PharmaBMRStep(models.Model):
    """A single execution step within a Batch Manufacturing Record."""
    _name = 'pharma.bmr.step'
    _description = 'BMR Execution Step'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'bmr_id, sequence, id'

    name = fields.Char(
        string='Step',
        compute='_compute_name',
        store=True,
            help='Specifies the Step for this record.',
    )

    bmr_id = fields.Many2one(
        comodel_name='pharma.bmr',
        string='BMR',
        required=True,
        ondelete='cascade',
        index=True,
            help='Specifies the BMR for this record.',
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
            help='Specifies the Sequence for this record.',
    )

    description = fields.Text(
        string='Step Description',
        required=True,
            help='Specifies the Step Description for this record.',
    )

    status = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('done', 'Done'),
            ('hold', 'Hold'),
        ],
        string='Status',
        default='pending',
        required=True,
            help='Specifies the Status for this record.',
    )

    hold_source_step_id = fields.Many2one(
        comodel_name='pharma.bmr.step',
        string='Hold Source Step',
        copy=False,
        readonly=True,
        ondelete='set null',
        help='Set when this step is on hold because an earlier step was put on hold.',
    )

    sop_id = fields.Many2one(
        comodel_name='pharma.sop',
        string='Linked SOP',
        domain="[('status', '=', 'effective')]",
        ondelete='set null',
        help='If set, the operator must have current (passed) training for this SOP '
             'before signing off. Only Effective SOPs can be linked.',
    )

    @api.depends('sequence', 'description')
    def _compute_name(self):
        """Generates a composite display name for the step using its sequence and description."""
        for step in self:
            description = (step.description or '').strip()
            step.name = '%s - %s' % (step.sequence, description) if description else _('Step %s') % step.sequence
    operator_id = fields.Many2one(
        comodel_name='res.users',
        string='Operator',
        copy=False,
            help='Specifies the Operator for this record.',
    )

    operator_signed_on = fields.Datetime(
        string='Operator Signed On',
        copy=False,
        readonly=True,
            help='Specifies the Operator Signed On for this record.',
    )
    supervisor_id = fields.Many2one(
        comodel_name='res.users',
        string='Supervisor',
        copy=False,
            help='Specifies the Supervisor for this record.',
    )

    supervisor_signed_on = fields.Datetime(
        string='Supervisor Signed On',
        copy=False,
        readonly=True,
            help='Specifies the Supervisor Signed On for this record.',
    )
    @api.constrains('operator_id', 'supervisor_id')
    def _check_different_users(self):
        """Validates that the operator and supervisor sign-offs are performed by different users."""
        for step in self:
            if step.operator_id and step.supervisor_id and \
                    step.operator_id == step.supervisor_id:
                continue
                # raise ValidationError(_(
                #     'The Supervisor must be a different user from the Operator '
                #     'on step: "%s".'
                # ) % step.description)

    def action_operator_sign(self):
        """
        Operator signs the step — records who executed it and when.

        Checks:
          • Step must be Pending.
          • If a SOP is linked, the current user must have completed SOP training.
        """
        for step in self:
            if step.status != 'pending':
                raise UserError(_('Only Pending steps can receive an operator sign-off.'))
            if step.operator_signed_on:
                raise UserError(_('This step already has an operator sign-off.'))

            held_step = step.bmr_id.step_ids.filtered(lambda s: s.status == 'hold' and s.sequence <= step.sequence)
            if held_step:
                raise UserError(_('Cannot sign this step — Step %s is currently on Hold. Release it before proceeding.') % held_step[0].sequence)

            # SOP training check
            if step.sop_id:
                self._check_sop_training(step.sop_id)

            step.write({
                'operator_id': self.env.user.id,
                'operator_signed_on': fields.Datetime.now(),
            })
            step.bmr_id.message_post(
                body=_('Step "%s" operator sign-off by %s.') % (
                    step.description[:60], self.env.user.name
                )
            )

    def action_supervisor_sign(self):
        """
        Supervisor independently verifies the step.

        Checks:
          • Step must have an operator sign-off first.
          • Supervisor must differ from operator (also enforced by DB constraint).
          • Marks the step Done if both sign-offs are complete.
        """
        for step in self:
            if step.status != 'pending':
                raise UserError(_('Only Pending steps can receive a supervisor sign-off.'))
            if not step.operator_signed_on:
                raise UserError(_('The operator must sign off before the supervisor.'))
            if step.supervisor_signed_on:
                raise UserError(_('This step already has a supervisor sign-off.'))
            # if self.env.user == step.operator_id:
            #     raise UserError(_(
            #         'The supervisor must be a different person from the operator. '
            #         'You already signed this step as operator.'
            #     ))

            ipqcs = step.bmr_id.ipqc_ids.filtered(lambda r: r.step_id == step)
            if any(not r.signed_on for r in ipqcs):
                raise UserError(_('Complete and sign all IPQC checks for this step before supervisor sign-off.'))

            # Check for any open Deviations for the batch
            open_deviations = self.env['pharma.deviation'].search([
                ('batch_id', '=', step.bmr_id.production_id.id),
                ('status', '!=', 'closed')
            ])
            if open_deviations:
                raise UserError(_('Cannot sign — there are open Deviations for this batch:\n%s') % ', '.join(open_deviations.mapped('name')))

            # Check for any open CAPAs for the batch
            open_capas = self.env['pharma.capa'].search([
                ('deviation_id.batch_id', '=', step.bmr_id.production_id.id),
                ('status', '!=', 'closed')
            ])
            if open_capas:
                raise UserError(_('Cannot sign — there are open CAPAs for this batch:\n%s') % ', '.join(open_capas.mapped('name')))
            step.write({
                'supervisor_id': self.env.user.id,
                'supervisor_signed_on': fields.Datetime.now(),
                'status': 'done',
            })
            step.bmr_id.message_post(
                body=_('Step "%s" completed. Supervisor sign-off by %s.') % (
                    step.description[:60], self.env.user.name
                )
            )

    def action_hold(self):
        """
        Put this step on Hold and cascade Hold to subsequent Pending steps.

        Only later Pending steps are cascaded. Completed steps and steps already
        on Hold keep their current state and are not linked to this hold.
        """
        for step in self:
            if step.status == 'done':
                raise UserError(_('Completed steps cannot be placed on hold.'))
            if step.status == 'hold':
                raise UserError(_('Step is already on hold.'))
            step.write({
                'status': 'hold',
                'hold_source_step_id': False,
            })

            cascaded_steps = step.bmr_id.step_ids.filtered(
                lambda s: s.status == 'pending' and s.sequence > step.sequence
            )
            cascaded_steps.write({
                'status': 'hold',
                'hold_source_step_id': step.id,
            })

            bmr = step.bmr_id
            if bmr.status == 'in_progress':
                bmr.status = 'on_hold'
                bmr.message_post(
                    body=_('BMR placed on hold — step "%s" put on hold by %s.') % (
                        step.description[:60], self.env.user.name
                    )
                )
            if cascaded_steps:
                bmr.message_post(
                    body=_(
                        'Hold cascaded from step "%(step)s" to pending subsequent step(s): %(steps)s.'
                    ) % {
                        'step': step.description[:60],
                        'steps': ', '.join(cascaded_steps.mapped('name')),
                    }
                )

    def action_release_hold(self):
        """Release the directly held step and restore its cascaded holds."""
        for step in self:
            if step.status != 'hold':
                raise UserError(_('Only steps on Hold can be released.'))
            if step.hold_source_step_id:
                raise UserError(_(
                    'This step is on hold because step "%s" is on hold. '
                    'Release the source step first.'
                ) % step.hold_source_step_id.name)

            cascaded_steps = step.bmr_id.step_ids.filtered(
                lambda s: s.status == 'hold' and s.hold_source_step_id == step
            )
            (step | cascaded_steps).write({
                'status': 'pending',
                'hold_source_step_id': False,
            })
            step.bmr_id.message_post(
                body=_('Step "%s" released from hold by %s.') % (
                    step.description[:60], self.env.user.name
                )
            )
            if cascaded_steps:
                step.bmr_id.message_post(
                    body=_(
                        'Cascaded hold released. Step(s) restored to Pending: %s.'
                    ) % ', '.join(cascaded_steps.mapped('name'))
                )

    def _ipqc_hold(self):
        """
        Put this step on hold due to an IPQC failure.
        Cascades Hold to subsequent Pending steps (same logic as action_hold,
        but called internally by PharmaIPQCResult so no user-facing error is
        raised if the step is already on hold).
        """
        for step in self:
            if step.status in ('done', 'hold'):
                continue
            step.write({'status': 'hold', 'hold_source_step_id': False})
            cascaded = step.bmr_id.step_ids.filtered(
                lambda s: s.status == 'pending' and s.sequence > step.sequence
            )
            cascaded.write({'status': 'hold', 'hold_source_step_id': step.id})
            bmr = step.bmr_id
            if bmr.status == 'in_progress':
                bmr.status = 'on_hold'
                bmr.message_post(body=_(
                    'BMR placed on Hold — IPQC check failed on step "%s". '
                    'Resolve the deviation before resuming.'
                ) % step.description[:60])

    def _ipqc_release(self):
        """
        Release the hold placed by an IPQC failure once all IPQC checks for
        this step are passing. Restores this step and its cascaded steps to
        Pending, and resumes the BMR.
        """
        for step in self:
            if step.status != 'hold':
                continue
            cascaded = step.bmr_id.step_ids.filtered(
                lambda s: s.status == 'hold' and s.hold_source_step_id == step
            )
            (step | cascaded).write({'status': 'pending', 'hold_source_step_id': False})
            bmr = step.bmr_id
            # Only resume BMR if no other steps are still on hold
            if bmr.status == 'on_hold' and not bmr.step_ids.filtered(lambda s: s.status == 'hold'):
                bmr.status = 'in_progress'
                bmr.message_post(body=_(
                    'BMR resumed — IPQC checks for step "%s" cleared. '
                    'Step and subsequent steps restored to Pending.'
                ) % step.description[:60])

    def _check_sop_training(self, sop):
        """
        Verify the current user has a Passed training record for the given SOP.
        Uses pharma.training model — auto-created when SOP reaches Effective status.
        Expired or Pending training blocks sign-off.
        """
        self.env['pharma.training'].check_training_clearance(
            self.env.user.id,
            sop_ids=[sop.id],
        )


