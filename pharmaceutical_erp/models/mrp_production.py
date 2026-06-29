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


class MrpRoutingWorkcenter(models.Model):
    """Extension of MRP Routing Workcenter to link operations with approved standard operating procedures (SOPs)."""
    _inherit = 'mrp.routing.workcenter'

    sop_id = fields.Many2one(
        comodel_name='pharma.sop',
        string='Linked SOP',
        required=True,
        domain="[('status', '=', 'effective')]",
        help='Approved SOP detailing how this routing operation must be executed.',
    )


class MrpProduction(models.Model):
    """Extension of MRP Production to support Pharmaceutical Batch Manufacturing Records (BMR) and QA Release workflows."""
    _inherit = 'mrp.production'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._merge_identical_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'move_raw_ids' in vals:
            self._merge_identical_lines()
        return res

    def _merge_identical_lines(self):
        """Merges identical product lines into a single line with summed quantities."""
        for mo in self:
            if mo.state not in ['draft', 'confirmed']:
                continue
            seen = {}
            moves_to_unlink = self.env['stock.move']
            for move in mo.move_raw_ids:
                if not move.product_id:
                    continue
                key = (move.product_id.id, move.product_uom.id)
                if key in seen:
                    seen[key].product_uom_qty += move.product_uom_qty
                    moves_to_unlink |= move
                else:
                    seen[key] = move
            if moves_to_unlink:
                if mo.state == 'confirmed':
                    moves_to_unlink._action_cancel()
                moves_to_unlink.unlink()

    bmr_ids = fields.One2many(
        comodel_name='pharma.bmr',
        inverse_name='production_id',
        string='Batch Manufacturing Records',
            help='Specifies the Batch Manufacturing Records for this record.',
    )

    bmr_count = fields.Integer(
        string='BMR Count',
        compute='_compute_bmr_count',
            help='Specifies the BMR Count for this record.',
    )

    @api.depends('bmr_ids')
    def _compute_bmr_count(self):
        """Calculates the total number of Batch Manufacturing Records linked to this manufacturing order."""
        for rec in self:
            rec.bmr_count = len(rec.bmr_ids)

    pharma_bmr_completed = fields.Boolean(
        string='BMR Completed',
        compute='_compute_pharma_bmr_completed',
            help='Specifies the BMR Completed for this record.',
    )

    @api.depends('bmr_ids.status')
    def _compute_pharma_bmr_completed(self):
        for rec in self:
            if rec.bmr_ids:
                rec.pharma_bmr_completed = all(b.status == 'completed' for b in rec.bmr_ids)
            else:
                rec.pharma_bmr_completed = False

    pharma_allowed_component_ids = fields.Many2many(
        comodel_name='product.product',
        compute='_compute_pharma_allowed_component_ids',
        string='Allowed Components'
    )

    @api.depends('bom_id', 'bom_id.bom_line_ids.product_id')
    def _compute_pharma_allowed_component_ids(self):
        for rec in self:
            if rec.bom_id:
                rec.pharma_allowed_component_ids = rec.bom_id.bom_line_ids.mapped('product_id')
            else:
                rec.pharma_allowed_component_ids = self.env['product.product']


    def button_mark_done(self):
        for rec in self:
            if not rec.pharma_bmr_completed:
                raise UserError(_("Cannot produce: The linked Batch Manufacturing Record (BMR) must be completed first."))
        return super(MrpProduction, self).button_mark_done()

    def action_confirm(self):
        # Enforce that only approved formulas (BoMs) can be used to confirm a production order
        """Overrides confirmation to enforce approved BoM usage and auto-generates the corresponding Batch Manufacturing Record."""
        for rec in self:
            if rec.bom_id and rec.bom_id.formula_status != 'approved':
                raise UserError(_(
                    'Cannot confirm Manufacturing Order %s because BoM/Formula "%s" is not Approved.'
                ) % (rec.name, rec.bom_id.display_name))

        res = super(MrpProduction, self).action_confirm()

        # Auto-create BMR
        for rec in self:
            if not rec.bmr_ids:
                rec.action_create_bmr()
        return res

    def action_create_bmr(self):
        """Generates a new Draft BMR and populates its execution steps and IPQC parameters from
        the BoM and approved specifications."""
        self.ensure_one()
        if self.bmr_ids:
            raise UserError(_('A BMR already exists for this Manufacturing Order.'))

        # Expected yield calculation
        expected_yield = self.product_qty
        if self.bom_id and self.bom_id.theoretical_yield:
            expected_yield = self.product_qty * (self.bom_id.theoretical_yield / 100.0)

        # Batch number: use lot_producing_ids if set, otherwise default to MO name
        batch_no = self.lot_producing_ids[0].name if self.lot_producing_ids else self.name

        # Create BMR
        bmr = self.env['pharma.bmr'].create({
            'production_id': self.id,
            'product_id': self.product_id.product_tmpl_id.id,
            'batch_no': batch_no,
            'yield_expected': expected_yield,
            'status': 'draft',
        })

        # Pull steps from BOM operations
        if self.bom_id and self.bom_id.operation_ids:
            for op in self.bom_id.operation_ids:
                self.env['pharma.bmr.step'].create({
                    'bmr_id': bmr.id,
                    'sequence': op.sequence,
                    'description': op.name,
                    'sop_id': op.sop_id.id,
                    'status': 'pending',
                })
        else:
            # Create a default step if BOM has no operations
            self.env['pharma.bmr.step'].create({
                'bmr_id': bmr.id,
                'sequence': 10,
                'description': _('Standard Manufacturing Execution Step'),
                'status': 'pending',
            })

        # Pull IPQC parameters from approved inprocess QC Spec
        qc_spec = self.env['pharma.qc.spec'].search([
            ('product_id', '=', self.product_id.product_tmpl_id.id),
            ('stage', '=', 'inprocess'),
            ('state', '=', 'approved'),
        ], limit=1)
        if qc_spec:
            for line in qc_spec.parameter_ids:
                self.env['pharma.ipqc.result'].create({
                    'bmr_id': bmr.id,
                    'parameter': line.parameter_name,
                    'expected_min': line.min_value,
                    'expected_max': line.max_value,
                })

        return bmr

    def action_view_bmr(self):
        """Open the BMR form/list for this MO.

        BMRs are always auto-generated when the MO is confirmed; they must
        never be created manually from this button.
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('pharmaceutical_erp.pharma_bmr_action')
        # Prevent manual BMR creation from the Production Order
        context_str = action.get('context', '{}')
        from ast import literal_eval
        try:
            ctx = literal_eval(context_str) if isinstance(context_str, str) else (context_str or {})
        except Exception:
            ctx = {}
        ctx['create'] = False
        action['context'] = ctx
        if len(self.bmr_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.bmr_ids[0].id,
            })
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('production_id', '=', self.id)],
            })
        return action

    qa_release_eligible = fields.Boolean(
        string='QA Release Eligible',
        compute='_compute_qa_release_eligible',
        search='_search_qa_release_eligible',
        help='Specifies the QA Release Eligible for this record.'
    )

    def _compute_qa_release_eligible(self):
        """Evaluates if the manufacturing order is eligible for QA Release based on completion status and
        whether it's already released."""
        for bmr in self:
            has_coa = self.env['pharma.coa'].search_count([('batch_id', '=', bmr.id)]) > 0
            has_qa_queue = self.env['pharma.qa.release'].search_count([('production_id', '=', bmr.id)]) > 0
            bmr.qa_release_eligible = (bmr.state == 'done' and not has_coa and not has_qa_queue)

    def _search_qa_release_eligible(self, operator, value):
        """Custom search method to filter manufacturing orders that are eligible for QA Release."""
        if operator == '=' and value is True:
            return [('state', '=', 'done')]
        elif operator == '!=' and value is True:
            return [('state', '!=', 'done')]
        elif operator == '=' and value is False:
            return [('state', '!=', 'done')]
        elif operator == '!=' and value is False:
            return [('state', '=', 'done')]
        return [('id', 'in', [])]

    def action_qa_release(self):
        """Executes the final QA release process, generating a Certificate of Analysis (CoA) and
        updating the lot status to 'Released'."""
        from odoo.exceptions import ValidationError
        for bmr in self:
            if not bmr.qa_release_eligible:
                raise ValidationError("This BMR is not eligible for QA Release. Please ensure it"
                                      " is completed and in 'done' state.")
            
            # Prevent multiple QA release records
            existing_qa_release = self.env['pharma.qa.release'].search([('production_id', '=', bmr.id)], limit=1)
            if existing_qa_release:
                raise ValidationError("A QA Release Queue record already exists for this batch.")

            existing_coa = self.env['pharma.coa'].search([('batch_id', '=', bmr.id)], limit=1)
            if existing_coa:
                raise ValidationError("A Certificate of Analysis already exists for this batch.")

            # Strict compliance validation
            qc_tests = self.env['pharma.qc.test.order'].search([
                ('lot_id', 'in', bmr.lot_producing_ids.ids)
            ])
            if not qc_tests or not all(t.status == 'passed' for t in qc_tests):
                raise ValidationError("All QC Test Orders for the produced lots must be passed before QA Release.")

            open_oos = self.env['pharma.oos.investigation'].search_count([
                ('result_line_id.test_order_id', 'in', qc_tests.ids),
                ('closed_on', '=', False)
            ])
            if open_oos > 0:
                raise ValidationError("There are open OOS investigations for this batch. They must be "
                                      "closed before QA Release.")

            open_deviations = self.env['pharma.deviation'].search_count([
                ('batch_id', '=', bmr.id),
                ('status', 'in', ('open', 'under_investigation'))
            ])
            if open_deviations > 0:
                raise ValidationError("There are open or under investigation deviations for this batch."
                                      " They must be resolved before QA Release.")
            
            qa_release = self.env['pharma.qa.release'].create({
                'production_id': bmr.id,
                'lot_id': bmr.lot_producing_ids[0].id if bmr.lot_producing_ids else False,
            })
            
            # Post a message to BMR
            bmr.message_post(body=f"Sent to QA Release Queue: {qa_release.name}.")
