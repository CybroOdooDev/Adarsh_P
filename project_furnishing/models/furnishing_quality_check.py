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
    installation_ids = fields.Many2many(
        'project.installation',
        'project_installation_quality_check_rel',
        'quality_check_id',
        'installation_id',
        string='Scheduled Installations',
        domain="[('project_id', '=', project_id)]",
        help='Installation batch or site delivery for which this finished piece is dispatched.'
    )
    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Transfer',
        readonly=True,
        copy=False,
        help='Internal transfer moving certified goods from Quality Inspection to Main Stock upon passing QC.'
    )

    # -------------------------------------------------------------------------
    # DYNAMIC CHECKLIST LINES & TEMPLATE
    # -------------------------------------------------------------------------
    template_id = fields.Many2one(
        'furnishing.quality.check.template',
        string='Checklist Template',
        tracking=True,
        domain="['|', ('stage', '=', 'all'), ('stage', '=', stage)]",
        help='Select a QC checklist template to populate standard checkpoints.'
    )
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

            # Populate checklist lines from template if template_id is given and no lines provided
            if vals.get('template_id') and not vals.get('check_line_ids'):
                template = self.env['furnishing.quality.check.template'].browse(vals['template_id'])
                if template:
                    vals['check_line_ids'] = [
                        (0, 0, {
                            'check_type_id': t_line.check_type_id.id,
                            'sequence': t_line.sequence,
                            'result': 'pending',
                        }) for t_line in template.line_ids
                    ]
        return super().create(vals_list)

    def write(self, vals):
        if 'template_id' in vals:
            for check in self:
                if check.state != 'draft' and vals['template_id'] != check.template_id.id:
                    raise UserError(_(
                        "The checklist template cannot be changed once inspection has started for Quality Check '%(name)s'.",
                        name=check.name,
                    ))
        return super().write(vals)

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id:
            if self.template_id.stage and self.template_id.stage != 'all':
                self.stage = self.template_id.stage
            lines = [(5, 0, 0)]
            for t_line in self.template_id.line_ids:
                lines.append((0, 0, {
                    'check_type_id': t_line.check_type_id.id,
                    'sequence': t_line.sequence,
                    'result': 'pending',
                }))
            self.check_line_ids = lines

    @api.onchange('production_id')
    def _onchange_production_id(self):
        if self.production_id:
            self.product_id = self.production_id.product_id
            self.product_qty = self.production_id.product_qty
            if self.production_id.project_id:
                self.project_id = self.production_id.project_id

    @api.constrains('production_id')
    def _check_production_state(self):
        for check in self:
            if check.production_id and check.production_id.state == 'cancel':
                raise ValidationError(_(
                    "A quality check cannot be created for cancelled Manufacturing Order '%(mo_name)s'.",
                    mo_name=check.production_id.name,
                ))

    @api.constrains('state', 'check_line_ids')
    def _check_inspection_checkpoints(self):
        for check in self:
            if check.state != 'draft' and not check.check_line_ids:
                raise ValidationError(_(
                    "Quality Check '%(name)s' requires at least one checkpoint line to start or conduct an inspection.",
                    name=check.name,
                ))

    # -------------------------------------------------------------------------
    # WORKFLOW ACTIONS
    # -------------------------------------------------------------------------
    def action_start(self):
        for record in self:
            if record.state not in ('draft', 'failed'):
                raise UserError(_("Quality Check '%s' can only be moved to Under Inspection from Draft or Failed state.") % record.name)
            if not record.check_line_ids:
                raise UserError(_(
                    "Quality Check '%(name)s' requires at least one checkpoint line to start inspection. "
                    "Please select a checklist template or add checkpoint lines before starting.",
                    name=record.name,
                ))
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
                    "Please mark the rectified checkpoints as 'Pass' before releasing.",
                    name=record.name,
                    count=record.failed_lines_count
                ))
            record._action_transfer_to_stock()
            record.write({
                'state': 'passed',
                'defect_type': 'none',
            })
            record.message_post(body=_("Quality Check <b>PASSED</b>: Certified Site-Ready for Delivery & Installation."))

    def _action_transfer_to_stock(self):
        self.ensure_one()
        if not self.product_id or not getattr(self.product_id, 'is_storable', False):
            return False
        company = self.company_id or self.env.company
        warehouse = False
        if self.production_id and self.production_id.picking_type_id:
            warehouse = self.production_id.picking_type_id.warehouse_id
        if not warehouse:
            warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        if not warehouse:
            return False

        source_loc = False
        if self.production_id and self.production_id.location_dest_id:
            source_loc = self.production_id.location_dest_id
        else:
            source_loc = company.furnishing_qc_location_id or company._get_furnishing_qc_location()

        target_loc = warehouse.lot_stock_id
        if not source_loc or not target_loc or source_loc == target_loc:
            return False

        qty_needed = self.product_qty or 1.0
        qty_available = self.env['stock.quant'].sudo()._get_available_quantity(self.product_id, source_loc)
        if qty_available < qty_needed:
            raise UserError(_(
                "Cannot transfer '%(product)s' to main stock. "
                "Insufficient quantity in %(src)s (Required: %(needed)g, Available: %(avail)g). "
                "Please verify the item has been produced and deposited into Quality Inspection before passing QC."
            ) % {
                'product': self.product_id.display_name,
                'src': source_loc.display_name,
                'needed': qty_needed,
                'avail': qty_available,
            })

        picking_type = warehouse.int_type_id
        if not picking_type:
            raise UserError(_("No Internal Transfer operation type found for warehouse '%s'.") % warehouse.name)

        with self.env.cr.savepoint():
            picking = self.env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': source_loc.id,
                'location_dest_id': target_loc.id,
                'origin': _("QC Release: %s") % self.name,
                'company_id': company.id,
                'project_id': self.project_id.id if self.project_id else False,
            })
            move = self.env['stock.move'].sudo().create({
                'description_picking': _("QC Release: %s") % self.product_id.display_name,
                'product_id': self.product_id.id,
                'product_uom_qty': qty_needed,
                'uom_id': self.product_id.uom_id.id,
                'location_id': source_loc.id,
                'location_dest_id': target_loc.id,
                'picking_id': picking.id,
                'company_id': company.id,
            })
            picking.action_confirm()
            picking.action_assign()
            lot_id = False
            if self.production_id:
                if hasattr(self.production_id, 'lot_producing_ids') and self.production_id.lot_producing_ids:
                    lot_id = self.production_id.lot_producing_ids[0]
                elif hasattr(self.production_id, 'lot_producing_id') and self.production_id.lot_producing_id:
                    lot_id = self.production_id.lot_producing_id
            for ml in picking.move_line_ids:
                ml.quantity = ml.quantity_product_uom or qty_needed
                if lot_id and not ml.lot_id:
                    ml.lot_id = lot_id.id
            if not picking.move_line_ids:
                self.env['stock.move.line'].sudo().create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': self.product_id.id,
                    'product_uom_id': self.product_id.uom_id.id,
                    'quantity': qty_needed,
                    'location_id': source_loc.id,
                    'location_dest_id': target_loc.id,
                    'lot_id': lot_id.id if lot_id else False,
                })
            res = picking.button_validate()
            if picking.state != 'done':
                raise UserError(_(
                    "Automatic stock transfer %(picking)s could not be completed immediately (State: %(state)s). "
                    "Please complete the stock transfer manually.",
                    picking=picking.name,
                    state=picking.state,
                ))

            self.stock_picking_id = picking.id
            self.message_post(body=_(
                "Stock Transfer <b>%(picking)s</b> completed: %(qty)g %(uom)s moved from %(src)s to %(dst)s.",
                picking=picking.name,
                qty=qty_needed,
                uom=self.product_id.uom_id.name,
                src=source_loc.display_name,
                dst=target_loc.display_name,
            ))
            return picking

    def action_view_stock_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Transfer'),
            'res_model': 'stock.picking',
            'res_id': self.stock_picking_id.id,
            'view_mode': 'form',
        }

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            check_id = vals.get('check_id')
            if check_id:
                check = self.env['furnishing.quality.check'].browse(check_id)
                if check.state != 'draft':
                    raise UserError(_(
                        "Checkpoints cannot be added once inspection has started for Quality Check '%(name)s'.",
                        name=check.name,
                    ))
        return super().create(vals_list)

    def write(self, vals):
        if 'check_type_id' in vals:
            for line in self:
                if line.check_id.state != 'draft' and vals['check_type_id'] != line.check_type_id.id:
                    raise UserError(_(
                        "Checkpoints cannot be changed once inspection has started for Quality Check '%(name)s'.",
                        name=line.check_id.name,
                    ))
        return super().write(vals)

    def unlink(self):
        for line in self:
            if line.check_id.state != 'draft':
                raise UserError(_(
                    "Checkpoints cannot be removed once inspection has started for Quality Check '%(name)s'.",
                    name=line.check_id.name,
                ))
        return super().unlink()

    def action_set_pass(self):
        for line in self:
            line.result = 'pass'

    def action_set_fail(self):
        for line in self:
            line.result = 'fail'
