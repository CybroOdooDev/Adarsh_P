# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FurnishingQualityCheck(models.Model):
    _name = 'furnishing.quality.check'
    _description = 'Furnishing Manufacturing Quality Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'check_date desc, id desc'

    name = fields.Char(
        string='QC Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True
    )
    project_id = fields.Many2one(
        'project.project',
        string='Furnishing Project',
        tracking=True,
        domain="[('is_template', '=', False)]",
        help='Linked furnishing project for this fabrication/manufacturing order.'
    )
    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        tracking=True,
        ondelete='set null',
        domain="[('state', '!=', 'cancel')]",
        help='The Manufacturing Order being inspected.'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product / Furniture Piece',
        required=True,
        tracking=True,
        help='The manufactured product, furniture unit, or joinery element being checked.'
    )
    product_qty = fields.Float(
        string='Inspected Quantity',
        default=1.0,
        digits='Product Unit of Measure',
        tracking=True
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_id.uom_id',
        readonly=True
    )
    stage = fields.Selection([
        ('raw_material', 'Raw Material (Timber, Veneer, Boards, Hardware)'),
        ('in_process', 'In-Process (Joinery, Carcass, Framework)'),
        ('finishing', 'Finishing & Coating (Polish, Lacquer, Veneer Lamination)'),
        ('assembly', 'Fitting & Hardware Assembly (Hinges, Runners, Glass)'),
        ('pre_dispatch', 'Pre-Dispatch / Factory Sign-Off'),
    ], string='Inspection Stage', default='pre_dispatch', required=True, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'Under Inspection'),
        ('passed', 'Passed'),
        ('conditional', 'Conditional Pass (Minor Rectification)'),
        ('failed', 'Failed (Rejected)'),
    ], string='Inspection Status', default='draft', required=True, tracking=True, copy=False)

    check_date = fields.Date(
        string='Inspection Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    inspector_id = fields.Many2one(
        'res.users',
        string='Quality Inspector',
        default=lambda self: self.env.user,
        required=True,
        tracking=True
    )
    supervisor_id = fields.Many2one(
        'res.users',
        string='QC Supervisor / Sign-Off',
        tracking=True,
        help='Senior QC Manager or Factory Supervisor who signed off the inspection.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # -------------------------------------------------------------------------
    # DYNAMIC CHECKLIST LINES & TEST TYPES
    # -------------------------------------------------------------------------
    check_line_ids = fields.One2many(
        'furnishing.quality.check.line',
        'check_id',
        string='Inspection Checklist',
        copy=True
    )
    total_lines_count = fields.Integer(
        string='Total Checkpoints',
        compute='_compute_line_counts',
        store=True
    )
    passed_lines_count = fields.Integer(
        string='Passed',
        compute='_compute_line_counts',
        store=True
    )
    failed_lines_count = fields.Integer(
        string='Failed',
        compute='_compute_line_counts',
        store=True
    )
    pending_lines_count = fields.Integer(
        string='Pending Evaluation',
        compute='_compute_line_counts',
        store=True
    )

    @api.depends('check_line_ids.result')
    def _compute_line_counts(self):
        for check in self:
            total = len(check.check_line_ids)
            passed = sum(1 for line in check.check_line_ids if line.result == 'pass')
            failed = sum(1 for line in check.check_line_ids if line.result == 'fail')
            pending = sum(1 for line in check.check_line_ids if line.result == 'pending')
            check.total_lines_count = total
            check.passed_lines_count = passed
            check.failed_lines_count = failed
            check.pending_lines_count = pending

    # -------------------------------------------------------------------------
    # DISPATCH CLEARANCE & READINESS
    # -------------------------------------------------------------------------
    dispatch_ready = fields.Boolean(
        string='Certified Site-Ready',
        compute='_compute_dispatch_ready',
        store=True,
        tracking=True,
        help='Indicates whether this finished piece has passed all quality checks and is approved for site delivery.'
    )

    @api.depends('state', 'failed_lines_count')
    def _compute_dispatch_ready(self):
        for check in self:
            check.dispatch_ready = (check.state == 'passed' and check.failed_lines_count == 0)

    # -------------------------------------------------------------------------
    # VISUAL EVIDENCE / QC PHOTOS
    # -------------------------------------------------------------------------
    inspection_image = fields.Image(
        string='Finished Piece Photo',
        max_width=1920,
        max_height=1920,
        help='Photo of the finished piece after assembly/polish.'
    )
    defect_image = fields.Image(
        string='Defect Close-up Photo',
        max_width=1920,
        max_height=1920,
        help='Close-up photo of any scratch, gap, or non-conformance.'
    )


    # -------------------------------------------------------------------------
    # DEFECT LOGGING & CORRECTIVE ACTION
    # -------------------------------------------------------------------------
    defect_type = fields.Selection([
        ('none', 'No Defect'),
        ('dimensional', 'Dimensional Deviation'),
        ('surface_blemish', 'Scratch, Dent, or Surface Blemish'),
        ('color_mismatch', 'Color, Stain, or Polish Mismatch'),
        ('edge_gap', 'Edge Banding Peeling or Joint Gap'),
        ('hardware_issue', 'Hardware Misaligned or Defective Movement'),
        ('warping', 'Timber Warping or Core Board Delamination'),
        ('wobble', 'Uneven Legs / Wobble on Flat Floor'),
        ('glass_stone', 'Glass / Mirror / Stone Defect'),
        ('packaging', 'Packaging / Labeling Defect'),
        ('other', 'Other Non-Conformance'),
    ], string='Defect Classification', default='none', tracking=True)

    defect_severity = fields.Selection([
        ('minor', 'Minor (Quick touch-up on site)'),
        ('major', 'Major (Factory rework required)'),
        ('critical', 'Critical (Complete rejection & re-fabrication)'),
    ], string='Defect Severity', tracking=True)

    corrective_action = fields.Text(
        string='Corrective Action Required',
        help='Instructions for carpenters, painters, or assemblers to rectify the non-conformance.'
    )
    rectification_deadline = fields.Date(
        string='Target Rectification Date',
        tracking=True
    )
    recheck_required = fields.Boolean(
        string='Re-Inspection Required',
        default=False,
        tracking=True
    )
    notes = fields.Html(
        string='Inspector Notes & Technical Observations'
    )

    # -------------------------------------------------------------------------
    # CRUD & BUSINESS LOGIC
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furnishing.quality.check') or _('New')

            # Auto-populate active test types for this stage if no lines were manually given
            if 'check_line_ids' not in vals or not vals.get('check_line_ids'):
                stage = vals.get('stage', 'pre_dispatch')
                types = self.env['furnishing.quality.check.type'].search([
                    '|', ('stage', '=', 'all'), ('stage', '=', stage)
                ], order='sequence, id')
                if not types:
                    types = self.env['furnishing.quality.check.type'].search([], order='sequence, id')
                if types:
                    vals['check_line_ids'] = [
                        (0, 0, {
                            'check_type_id': t.id,
                            'sequence': t.sequence,
                            'result': 'pending',
                        }) for t in types
                    ]
        return super().create(vals_list)

    @api.onchange('production_id')
    def _onchange_production_id(self):
        if self.production_id:
            self.product_id = self.production_id.product_id
            self.product_qty = self.production_id.product_qty
            if hasattr(self.production_id, 'project_id') and self.production_id.project_id:
                self.project_id = self.production_id.project_id

    @api.constrains('production_id')
    def _check_production_state(self):
        for check in self:
            if check.production_id and check.production_id.state == 'cancel':
                raise ValidationError(_(
                    "A quality check cannot be created for cancelled Manufacturing Order '%(mo_name)s'.",
                    mo_name=check.production_id.name,
                ))

    def action_load_default_checks(self):
        """Populate active check types into checklist lines without removing existing lines."""
        self.ensure_one()
        types = self.env['furnishing.quality.check.type'].search([
            '|', ('stage', '=', 'all'), ('stage', '=', self.stage)
        ], order='sequence, id')
        if not types:
            types = self.env['furnishing.quality.check.type'].search([], order='sequence, id')
        existing_type_ids = set(self.check_line_ids.mapped('check_type_id.id'))
        new_lines = []
        for t in types:
            if t.id not in existing_type_ids:
                new_lines.append((0, 0, {
                    'check_type_id': t.id,
                    'sequence': t.sequence,
                    'result': 'pending',
                }))
        if new_lines:
            self.write({'check_line_ids': new_lines})

    # -------------------------------------------------------------------------
    # WORKFLOW ACTIONS
    # -------------------------------------------------------------------------
    def action_start(self):
        for record in self:
            if record.state not in ('draft', 'failed'):
                raise UserError(_("Quality Check '%s' can only be moved to Under Inspection from Draft or Failed state.") % record.name)
        self.write({'state': 'in_progress'})

    def action_pass(self):
        for record in self:
            if record.state != 'in_progress':
                raise UserError(_("Quality Check '%s' must be Under Inspection before it can be passed.") % record.name)
            if record.pending_lines_count > 0:
                raise UserError(_(
                    "Cannot pass Quality Check '%(name)s' because %(count)d checkpoint(s) are still pending evaluation. "
                    "Please evaluate all checkpoints before passing.",
                    name=record.name,
                    count=record.pending_lines_count
                ))
            if record.failed_lines_count > 0:
                raise UserError(_(
                    "Cannot pass Quality Check '%(name)s' because %(count)d checkpoint(s) are marked as 'Fail'. "
                    "Please rectify the failed items or use 'Conditional Pass' / 'Fail / Reject'.",
                    name=record.name,
                    count=record.failed_lines_count
                ))
            record.write({
                'state': 'passed',
                'defect_type': 'none',
            })
            record.message_post(body=_("Quality Check <b>PASSED</b>: Certified Site-Ready for Delivery & Installation."))

    def action_conditional(self):
        for record in self:
            if record.state != 'in_progress':
                raise UserError(_("Quality Check '%s' must be Under Inspection before it can be conditionally passed.") % record.name)
            if record.pending_lines_count > 0:
                raise UserError(_(
                    "Cannot conditionally pass Quality Check '%(name)s' because %(count)d checkpoint(s) are still pending evaluation.",
                    name=record.name,
                    count=record.pending_lines_count
                ))
            record.write({'state': 'conditional'})
            record.message_post(body=_("Quality Check <b>CONDITIONALLY APPROVED</b>: Minor rectification required: %s") % (record.corrective_action or ''))

    def action_fail(self):
        for record in self:
            if record.state != 'in_progress':
                raise UserError(_("Quality Check '%s' must be Under Inspection before it can be failed.") % record.name)
            record.write({'state': 'failed'})
            record.message_post(body=_("Quality Check <b>FAILED / REJECTED</b>. Severity: %s. Action: %s") % (
                record.defect_severity or 'Not specified',
                record.corrective_action or 'Rework required'
            ))

    def action_reset_draft(self):
        for record in self:
            if record.state in ('draft', 'in_progress'):
                raise UserError(_("Quality Check '%s' is already in Draft or Under Inspection.") % record.name)
        self.write({'state': 'draft'})


class FurnishingQualityCheckLine(models.Model):
    _name = 'furnishing.quality.check.line'
    _description = 'Furnishing Quality Check Line'
    _order = 'sequence, id'

    check_id = fields.Many2one(
        'furnishing.quality.check',
        string='Quality Check',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    check_type_id = fields.Many2one(
        'furnishing.quality.check.type',
        string='Checkpoint / Test',
        required=True
    )
    category = fields.Selection(
        related='check_type_id.category',
        string='Category',
        readonly=True,
        store=True
    )
    instructions = fields.Text(
        string='Standard Norms & Instructions',
        related='check_type_id.standard_instructions',
        readonly=True
    )
    result = fields.Selection([
        ('pending', 'Pending Evaluation'),
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('na', 'N/A'),
    ], string='Result', default='pending', required=True)
    notes = fields.Char(
        string='Remarks / Measured Value',
        help='e.g., Measured: +0.5mm, or Satin gloss level 30% verified'
    )
