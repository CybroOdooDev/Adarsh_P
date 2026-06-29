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


class PharmaQcTestOrder(models.Model):
    """QC Test Order — records quality control testing orders, stage, spec, lot information, and results."""
    _name = 'pharma.qc.test.order'
    _description = 'QC Test Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(
        string='Test Order Number',
        required=True,
        copy=False,
        readonly=True,
        default='/',
            help='Specifies the Test Order Number for this record.',
    )

    lot_id = fields.Many2one(
        comodel_name='stock.lot',
        string='Lot',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
        help='Which material or product lot is being tested.'
    )

    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
        help='Product linked to this test order.'
    )

    spec_id = fields.Many2one(
        comodel_name='pharma.qc.spec',
        string='Specification',
        required=True,
        domain="[('state', '=', 'approved')]",
        ondelete='restrict',
        index=True,
        tracking=True,
        help='QC specification auto-loaded based on product and stage.'
    )

    stage = fields.Selection(
        selection=[
            ('incoming', 'Incoming'),
            ('inprocess', 'In-Process'),
            ('finished', 'Finished Goods'),
        ],
        string='Testing Stage',
        required=True,
        default='incoming',
        tracking=True,
        help='QC checkpoint stage.'
    )

    status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('under_investigation', 'Under Investigation'),
            ('passed', 'Passed'),
            ('failed', 'Failed'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        help='Overall status of the test order.'
    )

    entered_by = fields.Many2one(
        comodel_name='res.users',
        string='Analyst',
        tracking=True,
        help='Analyst who entered the results.'
    )

    reviewed_by = fields.Many2one(
        comodel_name='res.users',
        string='Reviewed By',
        tracking=True,
        help='Second person who reviewed and signed, must differ from analyst.'
    )

    result_line_ids = fields.One2many(
        comodel_name='pharma.qc.result.line',
        inverse_name='test_order_id',
        string='Test Results',
        copy=True,
            help='Specifies the Test Results for this record.',
    )

    oos_investigation_ids = fields.One2many(
        comodel_name='pharma.oos.investigation',
        inverse_name='test_order_id',
        string='OOS Investigations',
    )

    deviation_ids = fields.Many2many(
        comodel_name='pharma.deviation',
        compute='_compute_deviations_capas',
        string='Deviations',
    )

    capa_ids = fields.Many2many(
        comodel_name='pharma.capa',
        compute='_compute_deviations_capas',
        string='CAPAs',
    )

    def _compute_deviations_capas(self):
        for order in self:
            deviations = self.env['pharma.deviation'].search([
                ('oos_investigation_id.result_line_id.test_order_id', '=', order.id)
            ])
            order.deviation_ids = deviations
            order.capa_ids = deviations.mapped('capa_ids')

    oos_investigation_count = fields.Integer(
        string='OOS Investigations',
        compute='_compute_oos_investigation_count',
            help='Specifies the OOS Investigations for this record.',
    )

    deviation_count = fields.Integer(
        string='Deviations',
        compute='_compute_deviation_count',
        help='Specifies the Deviations for this record related to OOS.'
    )

    def _compute_oos_investigation_count(self):
        """Calculates the total number of Out of Specification (OOS) investigations associated with this test order's results."""
        for order in self:
            order.oos_investigation_count = self.env['pharma.oos.investigation'].search_count([
                ('result_line_id.test_order_id', '=', order.id)
            ])

    def action_view_oos_investigations(self):
        """Returns a window action to open all OOS investigations related to this test order."""
        self.ensure_one()
        return {
            'name': 'OOS Investigations',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'pharma.oos.investigation',
            'domain': [('result_line_id.test_order_id', '=', self.id)],
            'context': {},
        }

    def _compute_deviation_count(self):
        """Calculates the total number of Deviations associated with this test order's OOS investigations."""
        for order in self:
            order.deviation_count = self.env['pharma.deviation'].search_count([
                ('oos_investigation_id.result_line_id.test_order_id', '=', order.id)
            ])

    def action_view_deviations(self):
        """Returns a window action to open all Deviations related to this test order."""
        self.ensure_one()
        return {
            'name': 'Deviations',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'pharma.deviation',
            'domain': [('oos_investigation_id.result_line_id.test_order_id', '=', self.id)],
            'context': {},
        }

    def action_start_test(self):
        """Transitions the test order from Draft to In Progress, assigning the current user as the analyst."""
        for rec in self:
            if rec.status != 'draft':
                raise ValidationError(_("Only draft test orders can be started."))
            
            for line in rec.result_line_ids:
                if not line.result_entered:
                    raise ValidationError(_("You must enter a valid result for parameter '%s' before starting.") % line.parameter)
                if line.is_oos:
                    raise ValidationError(_("Actual value for '%s' is not within the expected values. Please enter valid results before starting.") % line.parameter)

            vals = {'status': 'in_progress'}
            if not rec.entered_by:
                vals['entered_by'] = self.env.user.id
            rec.write(vals)

    def action_approve(self):
        """Approves the test order, verifying that all results meet specifications and any OOS investigations are resolved."""
        for rec in self:
            if rec.status not in ('in_progress', 'under_investigation'):
                raise ValidationError(_("Only test orders in 'In Progress' or 'Under Investigation' status can be approved."))
            # if rec.entered_by and rec.entered_by == self.env.user:
            #     raise ValidationError(_("The reviewer must be a different person than the analyst who entered the results."))

            # Check OOS investigations — all must be closed before approving
            investigations = self.env['pharma.oos.investigation'].search([
                ('result_line_id', 'in', rec.result_line_ids.ids)
            ])
            if any(not inv.closed_on for inv in investigations):
                raise ValidationError(_("Cannot approve a test order with open OOS investigations."))

            # Check open deviations resulting from those OOS investigations
            if investigations:
                open_devs = self.env['pharma.deviation'].search([
                    ('oos_investigation_id', 'in', investigations.ids),
                    ('status', '!=', 'closed')
                ])
                if open_devs:
                    raise ValidationError(_("Cannot approve a test order with open related deviations. "
                                            "Close the deviations and CAPAs first."))

            for line in rec.result_line_ids:
                if not line.result_entered:
                    raise ValidationError(_("You must enter a result for parameter '%s' before approving.") % line.parameter)
                if line.is_oos:
                    line_invs = sorted(
                        investigations.filtered(lambda i, l=line: i.result_line_id == l),
                        key=lambda i: i.id,
                    )
                    if not line_invs:
                        raise ValidationError(_("OOS result has no investigation record. Cannot approve."))
                    latest = line_invs[-1]
                    if not latest.lab_error_found and latest.disposition != 'release':
                        raise ValidationError(_("Cannot approve: OOS result has no 'Release' "
                                                "disposition and was not resolved as a lab error."))

            rec.write({
                'reviewed_by': self.env.user.id,
                'status': 'passed',
            })



    def action_reject(self):
        """Rejects the test order, marking it as Failed when results do not meet quality standards."""
        for rec in self:
            if rec.status not in ('in_progress', 'under_investigation'):
                raise ValidationError(_("Only test orders in 'In Progress' or 'Under Investigation' "
                                        "status can be rejected."))
            # if rec.entered_by and rec.entered_by == self.env.user:
            #     raise ValidationError(_("The reviewer must be a different person than the analyst who entered the results."))
            # rec.write({
            #     'reviewed_by': self.env.user.id,
            #     'status': 'failed',
            # })

    @api.constrains('entered_by', 'reviewed_by')
    def _check_reviewer(self):
        """Validates that the reviewer approving or rejecting the test order is different from the
        analyst who entered the results."""
        for rec in self:
            if rec.entered_by and rec.reviewed_by and rec.entered_by == rec.reviewed_by:
                pass
                # raise ValidationError(_("The reviewer must be a different person than the analyst who entered the results."))

    @api.onchange('product_id', 'stage')
    def _onchange_product_stage(self):
        """Automatically fetches and assigns the latest approved QC specification when the
         product or testing stage changes."""
        if self.product_id and self.stage:
            spec = self.env['pharma.qc.spec'].search([
                ('product_id', '=', self.product_id.id),
                ('stage', '=', self.stage),
                ('state', '=', 'approved'),
                '|', ('effective_date', '=', False), ('effective_date', '>=', fields.Date.today())
            ], order='version desc', limit=1)
            if spec:
                self.spec_id = spec.id
            else:
                self.spec_id = False
        else:
            self.spec_id = False

    @api.onchange('spec_id')
    def _onchange_spec_id(self):
        """Generates new test result lines based on the parameters defined in the selected QC specification."""
        if self.spec_id:
            # Clear old lines
            self.result_line_ids = [(5, 0, 0)]
            # Create new lines from spec parameter lines
            lines = []
            for line in self.spec_id.parameter_ids:
                lines.append((0, 0, {
                    'parameter': line.parameter_name,
                    'expected_min': line.min_value,
                    'has_min': line.min_value != 0.0 or getattr(line, 'has_min', True),
                    'expected_max': line.max_value,
                    'has_max': line.max_value != 0.0 or getattr(line, 'has_max', True),
                    'uom': line.uom_id.name or '',
                    'actual_value': 0.0,
                }))
            self.result_line_ids = lines

    @api.model_create_multi
    def create(self, vals_list):
        """Overrides creation to auto-assign a sequential test order number and automatically
        load parameters from the active QC specification."""
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('pharma.qc.test.order') or '/'

            # Auto load spec_id if product and stage are provided but spec_id is not
            if not vals.get('spec_id') and vals.get('product_id') and vals.get('stage'):
                spec = self.env['pharma.qc.spec'].search([
                    ('product_id', '=', vals['product_id']),
                    ('stage', '=', vals['stage']),
                    ('state', '=', 'approved'),
                    '|', ('effective_date', '=', False), ('effective_date', '>=', fields.Date.today())
                ], order='version desc', limit=1)
                if spec:
                    vals['spec_id'] = spec.id
                else:
                    product = self.env['product.template'].browse(vals['product_id'])
                    raise ValidationError(_(
                        "Cannot generate QC Test Order: No approved '%s' QC Specification found for product '%s'. "
                        "An approved specification is required before this product can be processed."
                    ) % (vals['stage'], product.display_name))

            # If spec_id is set/found, auto-load parameters if lines not provided
            if vals.get('spec_id') and not vals.get('result_line_ids'):
                spec = self.env['pharma.qc.spec'].browse(vals['spec_id'])
                lines = []
                for line in spec.parameter_ids:
                    lines.append((0, 0, {
                        'parameter': line.parameter_name,
                        'expected_min': line.min_value,
                        'has_min': line.min_value != 0.0 or getattr(line, 'has_min', True),
                        'expected_max': line.max_value,
                        'has_max': line.max_value != 0.0 or getattr(line, 'has_max', True),
                        'uom': line.uom_id.name or '',
                        'actual_value': 0.0,
                    }))
                vals['result_line_ids'] = lines
        return super().create(vals_list)

    def write(self, vals):
        """Overrides write to lock material and specification details once testing begins,
         and auto-updates result lines if the specification changes in draft mode."""
        _many2one = {'product_id', 'lot_id', 'spec_id'}
        _selection = {'stage'}
        locked = _many2one | _selection
        for rec in self:
            if rec.status != 'draft':
                for field in locked:
                    if field not in vals:
                        continue
                    current = rec[field].id if field in _many2one else rec[field]
                    if vals[field] != current:
                        raise ValidationError(
                            _("Cannot modify material or parameter details once the test has started.")
                        )
        # If spec_id is updated on draft test orders and result_line_ids is not passed,
        # regenerate the result lines.
        if 'spec_id' in vals and not vals.get('result_line_ids'):
            spec = self.env['pharma.qc.spec'].browse(vals['spec_id']) if vals['spec_id'] else False
            lines = [(5, 0, 0)]
            if spec:
                for line in spec.parameter_ids:
                    lines.append((0, 0, {
                        'parameter': line.parameter_name,
                        'expected_min': line.min_value,
                        'has_min': line.min_value != 0.0 or getattr(line, 'has_min', True),
                        'expected_max': line.max_value,
                        'has_max': line.max_value != 0.0 or getattr(line, 'has_max', True),
                        'uom': line.uom_id.name or '',
                        'actual_value': 0.0,
                    }))
            vals['result_line_ids'] = lines

        res = super().write(vals)
        if 'status' in vals and vals['status'] == 'passed':
            for rec in self:
                if rec.lot_id:
                    rec.lot_id.action_approve_lot()
        return res





