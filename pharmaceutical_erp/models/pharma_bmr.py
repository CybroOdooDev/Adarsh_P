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
from odoo.exceptions import UserError
from odoo.tools.translate import _


YIELD_THRESHOLD = 95.0  # percent — BMR flags a QA review below this


class PharmaBMR(models.Model):
    """Batch Manufacturing Record (BMR)."""
    _name = 'pharma.bmr'
    _description = 'Batch Manufacturing Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'name desc'

    _sql_constraints = [
        ('production_uniq', 'unique(production_id)', 'A Manufacturing Order can only have one BMR.')
    ]
    name = fields.Char(
        string='BMR Number',
        default='New',
        copy=False,
        readonly=True,
        tracking=True,
            help='Specifies the BMR Number for this record.',
    )

    production_id = fields.Many2one(
        comodel_name='mrp.production',
        string='Manufacturing Order',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
            help='Specifies the Manufacturing Order for this record.',
    )

    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        required=True,
        ondelete='restrict',
        tracking=True,
            help='Specifies the Product for this record.',
    )

    batch_no = fields.Char(
        string='Batch Number',
        required=True,
        copy=False,
        tracking=True,
        help='Unique batch number for this production run.',
    )
    status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('on_hold', 'On Hold'),
            ('completed', 'Completed'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
            help='Specifies the Status for this record.',
    )
    yield_expected = fields.Float(
        string='Expected Yield (kg)',
        digits=(16, 3),
        help='Theoretical yield based on BOM quantities.',
    )

    yield_actual = fields.Float(
        string='Actual Yield (kg)',
        digits=(16, 3),
        tracking=True,
        help='Actual output weight recorded at end of batch.',
    )

    yield_percentage = fields.Float(
        string='Yield %',
        compute='_compute_yield',
        store=True,
        digits=(5, 2),
        tracking=True,
            help='Specifies the Yield % for this record.',
    )

    yield_flag = fields.Boolean(
        string='Yield Flag',
        compute='_compute_yield',
        store=True,
        tracking=True,
        help='True when yield is below the configured threshold. '
             'QA sign-off is required before the BMR can be completed.',
    )

    qa_yield_signoff = fields.Boolean(
        string='QA Yield Sign-Off',
        copy=False,
        tracking=True,
        help='QA Director has reviewed and accepted a below-threshold yield.',
    )

    qa_yield_signed_by = fields.Many2one(
        comodel_name='res.users',
        string='Yield Sign-Off By',
        copy=False,
        readonly=True,
        tracking=True,
            help='Specifies the Yield Sign-Off By for this record.',
    )
    step_ids = fields.One2many(
        comodel_name='pharma.bmr.step',
        inverse_name='bmr_id',
        string='Steps',
            help='Specifies the Steps for this record.',
    )

    ipqc_ids = fields.One2many(
        comodel_name='pharma.ipqc.result',
        inverse_name='bmr_id',
        string='IPQC Results',
            help='Specifies the IPQC Results for this record.',
    )
    step_count = fields.Integer(
        compute='_compute_counts',
            help='Specifies the Step Count for this record.',
    )
    ipqc_count = fields.Integer(
        compute='_compute_counts',
            help='Specifies the Ipqc Count for this record.',
    )
    deviation_count = fields.Integer(
        compute='_compute_deviation_count',
            help='Specifies the Deviation Count for this record.',
    )
    all_steps_done = fields.Boolean(
        string='All Steps Done',
        compute='_compute_all_steps_done',
    )

    @api.depends('step_ids.status')
    def _compute_all_steps_done(self):
        for rec in self:
            if rec.step_ids:
                rec.all_steps_done = all(s.status == 'done' for s in rec.step_ids)
            else:
                rec.all_steps_done = False

    @api.depends('step_ids', 'ipqc_ids')
    def _compute_counts(self):
        """Calculates the total number of execution steps and IPQC results linked to this BMR."""
        for rec in self:
            rec.step_count = len(rec.step_ids)
            rec.ipqc_count = len(rec.ipqc_ids)

    def _compute_deviation_count(self):
        """Calculates the total number of deviations linked to this BMR and its IPQC results."""
        for rec in self:
            if rec.production_id:
                devs = self.env['pharma.deviation'].search([
                    '|',
                    ('batch_id', '=', rec.production_id.id),
                    ('id', 'in', rec.ipqc_ids.mapped('deviation_id').ids)
                ])
                rec.deviation_count = len(devs)
            else:
                rec.deviation_count = 0

    def action_view_deviations(self):
        """Returns a window action to display all deviations associated with this BMR."""
        self.ensure_one()
        devs = self.env['pharma.deviation'].search([
            '|',
            ('batch_id', '=', self.production_id.id),
            ('id', 'in', self.ipqc_ids.mapped('deviation_id').ids)
        ])
        action = self.env["ir.actions.actions"]._for_xml_id("pharmaceutical_erp.pharma_deviation_action")
        if len(devs) == 1:
            action['views'] = [(self.env.ref('pharmaceutical_erp.pharma_deviation_form').id, 'form')]
            action['res_id'] = devs.id
        else:
            action['domain'] = [('id', 'in', devs.ids)]
        return action

    @api.depends('yield_expected', 'yield_actual')
    def _compute_yield(self):
        """Calculates the actual yield percentage and flags the BMR if the yield falls below the configured threshold."""
        for rec in self:
            if rec.yield_expected:
                pct = (rec.yield_actual / rec.yield_expected) * 100.0
            else:
                pct = 0.0
            rec.yield_percentage = pct
            rec.yield_flag = pct < YIELD_THRESHOLD and rec.yield_expected > 0
    @api.model_create_multi
    def create(self, vals_list):
        """Overrides creation to auto-assign a sequential BMR number."""
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('pharma.bmr') or 'New'
        return super().create(vals_list)

    def action_start(self):
        """Move BMR from Draft → In Progress."""
        for rec in self:
            if rec.status != 'draft':
                raise UserError(_('Only Draft BMRs can be started.'))
            if not rec.step_ids:
                raise UserError(_('Add at least one step before starting the BMR.'))
            rec.status = 'in_progress'
            rec.message_post(body=_('BMR started by %s.') % self.env.user.name)
        return True

    def action_hold(self):
        """Put the entire BMR On Hold."""
        for rec in self:
            if rec.status != 'in_progress':
                raise UserError(_('Only In Progress BMRs can be put on hold.'))
            rec.status = 'on_hold'
            rec.message_post(body=_('BMR placed on hold by %s.') % self.env.user.name)
        return True

    def action_resume(self):
        """Resume a BMR from On Hold → In Progress."""
        for rec in self:
            if rec.status != 'on_hold':
                raise UserError(_('Only On Hold BMRs can be resumed.'))
            # Check for open IPQCs on steps that are currently active or on hold
            active_step_ids = rec.step_ids.filtered(lambda s: s.status in ('in_progress', 'hold')).ids
            open_ipqcs = rec.ipqc_ids.filtered(lambda r: r.step_id.id in active_step_ids and not r.signed_on and r.result == 'fail')
            if open_ipqcs:
                raise UserError(_('Cannot resume — there are open IPQC failures that have not been signed/resolved.'))

            # Check for open Deviations
            open_deviations = self.env['pharma.deviation'].search([
                ('batch_id', '=', rec.production_id.id),
                ('status', '!=', 'closed')
            ])
            if open_deviations:
                raise UserError(_('Cannot resume — there are open Deviations:\n%s') % ', '.join(open_deviations.mapped('name')))

            # Check for open CAPAs
            open_capas = self.env['pharma.capa'].search([
                ('deviation_id.batch_id', '=', rec.production_id.id),
                ('status', '!=', 'closed')
            ])
            if open_capas:
                raise UserError(_('Cannot resume — there are open CAPAs:\n%s') % ', '.join(open_capas.mapped('name')))

            # Ensure no step is still on hold
            held = rec.step_ids.filtered(lambda s: s.status == 'hold')
            if held:
                raise UserError(_(
                    'Cannot resume — the following step(s) are still on hold:\n%s'
                ) % '\n'.join(held.mapped('description')))
            rec.status = 'in_progress'
            rec.message_post(body=_('BMR resumed by %s.') % self.env.user.name)
        return True

    def action_complete(self):
        """
        Move BMR from In Progress → Completed.

        Gating conditions:
          1. All steps must be Done.
          2. No IPQC result is Fail with an open (unresolved) deviation.
          3. If yield_flag is True, qa_yield_signoff must be True.
        """
        for rec in self:
            if rec.status != 'in_progress':
                raise UserError(_('Only In Progress BMRs can be completed.'))

            # Gate 1: all steps done
            non_done = rec.step_ids.filtered(lambda s: s.status != 'done')
            if non_done:
                raise UserError(_(
                    'Cannot complete — %d step(s) are not yet Done.'
                ) % len(non_done))

            # Gate 2: no unresolved IPQC failures
            failed_ipqc = rec.ipqc_ids.filtered(lambda r: r.result == 'fail')
            for check in failed_ipqc:
                dev = check.deviation_id
                if not dev:
                    raise UserError(_(
                        'IPQC check "%s" failed but has no linked deviation. '
                        'Please raise a deviation first.'
                    ) % check.parameter)
                if dev.status != 'closed':
                    raise UserError(_(
                        'IPQC failure on "%s" has an open deviation (%s). '
                        'Close the deviation before completing the BMR.'
                    ) % (check.parameter, dev.name))

            # Gate 3: yield flag requires QA sign-off
            if rec.yield_flag and not rec.qa_yield_signoff:
                raise UserError(_(
                    'Yield is below the %.1f%% threshold (actual: %.2f%%). '
                    'A QA Director must sign off on the yield before this BMR '
                    'can be completed.'
                ) % (YIELD_THRESHOLD, rec.yield_percentage))

            rec.status = 'completed'
            rec.message_post(body=_('BMR completed by %s.') % self.env.user.name)

            if rec.production_id and rec.production_id.state not in ('done', 'cancel'):
                rec.production_id.with_context(skip_sanity_check=True).button_mark_done()
                rec.production_id.message_post(body=_("BMR %s completed. Manufacturing Order closed automatically.") % rec.name)

            # Auto-create Finished Goods QC Test Order
            rec._create_fg_qc_test_order()

    def action_qa_yield_signoff(self):
        """QA Director accepts a below-threshold yield."""
        self._check_group(
            'pharmaceutical_erp.group_pharma_qa_director',
            _('Only the Pharma QA Director can sign off on yield deviations.'),
        )
        for rec in self:
            if not rec.yield_flag:
                raise UserError(_('Yield sign-off is only required when the yield flag is set.'))
            rec.write({
                'qa_yield_signoff': True,
                'qa_yield_signed_by': self.env.user.id,
            })
            rec.message_post(
                body=_('Yield sign-off by QA Director %s. Yield: %.2f%%.') % (
                    self.env.user.name, rec.yield_percentage
                )
            )

    def _create_fg_qc_test_order(self):
        """
        Auto-create a Finished Goods QC Test Order when the BMR is completed.
        Links to the finished lot and loads the approved FG QC Spec.
        """
        lot = None
        if self.production_id and self.production_id.lot_producing_ids:
            lot = self.production_id.lot_producing_ids[0]

        if not lot:
            self.message_post(body=_(
                'BMR completed but no finished lot found on the MO. '
                'Please create the Finished Goods QC Test Order manually.'
            ))
            return

        self.env['pharma.qc.test.order'].create({
            'product_id': self.product_id.id,
            'lot_id': lot.id,
            'stage': 'finished',
        })
        self.message_post(body=_(
            'Finished Goods QC Test Order auto-created for lot %s.'
        ) % lot.name)

    def _check_group(self, group_xmlid, message):
        """Utility method to verify if the current user belongs to a specific security group."""
        if not self.env.user.has_group(group_xmlid):
            raise UserError(message)
