# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class PharmaQaRelease(models.Model):
    _name = 'pharma.qa.release'
    _description = 'QA Release Queue Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New', tracking=True)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True, readonly=True, tracking=True)
    product_id = fields.Many2one('product.template', related='production_id.product_id.product_tmpl_id', store=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/Batch', readonly=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('released', 'Released'),
    ], string='Status', default='draft', tracking=True)
    coa_id = fields.Many2one('pharma.coa', string='Certificate of Analysis', readonly=True, tracking=True)

    # Smart button counts
    bmr_count = fields.Integer(compute="_compute_counts", string="BMR")
    qc_test_count = fields.Integer(compute="_compute_counts", string="QC Test Orders")
    deviation_count = fields.Integer(compute="_compute_counts", string="Deviations")
    capa_count = fields.Integer(compute="_compute_counts", string="CAPAs")
    coa_count = fields.Integer(compute="_compute_counts", string="CoAs")

    # Main details
    company_id = fields.Many2one('res.company', related='production_id.company_id', string='Company')
    manufacturing_date = fields.Date(related='lot_id.manufacture_date', string='Manufacturing Date')
    expiry_date = fields.Date(related='lot_id.expiry_date', string='Expiry Date')
    formula_version = fields.Char(related='production_id.bom_id.display_name', string='Formula Version')
    manufactured_by = fields.Many2one('res.users', related='production_id.user_id', string='Manufactured By')

    # Release Checklist
    bmr_completed = fields.Boolean("BMR Completed", compute="_compute_checklist")
    fg_qc_passed = fields.Boolean("Finished Goods QC Passed", compute="_compute_checklist")
    no_open_deviations = fields.Boolean("No Open Deviations", compute="_compute_checklist")
    no_open_capas = fields.Boolean("No Open CAPAs", compute="_compute_checklist")
    yield_within_threshold = fields.Boolean("Yield Within Threshold", compute="_compute_checklist")
    all_bmr_steps_completed = fields.Boolean("All Mandatory BMR Steps Completed", compute="_compute_checklist")
    all_ipqc_passed = fields.Boolean("All Required IPQC Checks Passed", compute="_compute_checklist")
    stability_sampling_completed = fields.Boolean("Stability Sampling Completed (if applicable)")
    regulatory_docs_verified = fields.Boolean("Regulatory Documents Verified")
    overall_status = fields.Selection([('pending', 'Pending'), ('all_clear', 'All Clear')], compute="_compute_overall_status")

    # Finished Goods QC
    fg_qc_test_id = fields.Many2one('pharma.qc.test.order', compute="_compute_fg_qc", string="QC Test Order")
    fg_qc_status = fields.Selection([
        ('draft', 'Draft'), ('in_progress', 'In Progress'), ('under_investigation', 'Under Investigation'),
        ('passed', 'Passed'), ('failed', 'Failed')
    ], compute="_compute_fg_qc", string="QC Status")
    fg_qc_stage = fields.Selection([
        ('incoming', 'Incoming'), ('inprocess', 'In-Process'), ('finished', 'Finished Goods')
    ], compute="_compute_fg_qc", string="Stage")
    fg_qc_reviewed_by = fields.Many2one('res.users', compute="_compute_fg_qc", string="Reviewed By")

    # Yield Information
    expected_yield = fields.Float(string="Expected Yield", compute="_compute_yield")
    actual_yield = fields.Float(string="Actual Yield", compute="_compute_yield")
    yield_percentage = fields.Float(string="Yield %", compute="_compute_yield")
    yield_flag = fields.Char(string="Yield Flag", compute="_compute_yield")

    @api.depends('production_id', 'lot_id')
    def _compute_counts(self):
        for rec in self:
            rec.bmr_count = self.env['pharma.bmr'].search_count([('production_id', '=', rec.production_id.id)]) if rec.production_id else 0
            rec.qc_test_count = self.env['pharma.qc.test.order'].search_count([('lot_id', '=', rec.lot_id.id)]) if rec.lot_id else 0
            rec.deviation_count = self.env['pharma.deviation'].search_count([('batch_id', '=', rec.production_id.id)]) if rec.production_id else 0
            rec.capa_count = self.env['pharma.capa'].search_count([('deviation_id.batch_id', '=', rec.production_id.id)]) if rec.production_id else 0
            rec.coa_count = self.env['pharma.coa'].search_count([('lot_id', '=', rec.lot_id.id)]) if rec.lot_id else 0

    @api.depends('production_id', 'lot_id')
    def _compute_checklist(self):
        for rec in self:
            bmr = self.env['pharma.bmr'].search([('production_id', '=', rec.production_id.id)], limit=1)
            rec.bmr_completed = bool(bmr and bmr.status == 'completed')
            rec.all_bmr_steps_completed = bool(bmr and bmr.status == 'completed') # simplified
            
            fg_qc = self.env['pharma.qc.test.order'].search([
                ('lot_id', '=', rec.lot_id.id), 
                ('stage', 'in', ('finished', 'finished_product'))
            ])
            rec.fg_qc_passed = bool(fg_qc and all(q.status == 'passed' for q in fg_qc))
            
            ipqc = self.env['pharma.qc.test.order'].search([
                ('lot_id', '=', rec.lot_id.id), 
                ('stage', '=', 'in_process')
            ])
            rec.all_ipqc_passed = bool(not ipqc or all(q.status == 'passed' for q in ipqc))
            
            open_devs = self.env['pharma.deviation'].search_count([
                ('batch_id', '=', rec.production_id.id),
                ('status', 'in', ('open', 'under_investigation'))
            ])
            rec.no_open_deviations = (open_devs == 0)
            
            open_capas = self.env['pharma.capa'].search_count([
                ('deviation_id.batch_id', '=', rec.production_id.id),
                ('status', 'in', ('draft', 'in_progress', 'under_review'))
            ])
            rec.no_open_capas = (open_capas == 0)
            
            # Simple yield threshold check (e.g. >= 90%)
            expected = rec.production_id.product_qty or 1
            actual = rec.production_id.qty_producing or 0
            yield_pct = (actual / expected) * 100
            rec.yield_within_threshold = (yield_pct >= 90.0)

    @api.depends('bmr_completed', 'fg_qc_passed', 'no_open_deviations', 'no_open_capas', 'yield_within_threshold', 'all_bmr_steps_completed', 'all_ipqc_passed')
    def _compute_overall_status(self):
        for rec in self:
            if all([
                rec.bmr_completed, rec.fg_qc_passed, rec.no_open_deviations,
                rec.no_open_capas, rec.yield_within_threshold, rec.all_bmr_steps_completed,
                rec.all_ipqc_passed
            ]):
                rec.overall_status = 'all_clear'
            else:
                rec.overall_status = 'pending'

    @api.depends('lot_id')
    def _compute_fg_qc(self):
        for rec in self:
            qc = self.env['pharma.qc.test.order'].search([
                ('lot_id', '=', rec.lot_id.id),
                ('stage', 'in', ('finished', 'finished_product'))
            ], limit=1, order="id desc")
            rec.fg_qc_test_id = qc.id
            rec.fg_qc_status = qc.status if qc else False
            rec.fg_qc_stage = qc.stage if qc else False
            rec.fg_qc_reviewed_by = qc.reviewed_by.id if qc else False

    @api.depends('production_id')
    def _compute_yield(self):
        for rec in self:
            expected = rec.production_id.product_qty or 0.0
            actual = rec.production_id.qty_producing or 0.0
            # If we want them to display as % directly or units:
            rec.expected_yield = expected
            rec.actual_yield = actual
            if expected > 0:
                pct = (actual / expected)
            else:
                pct = 0.0
            rec.yield_percentage = pct
            rec.yield_flag = 'Within Limit' if pct >= 0.90 else 'Out of Limit'

    def action_view_bmr(self):
        self.ensure_one()
        return {
            'name': 'BMR',
            'type': 'ir.actions.act_window',
            'res_model': 'pharma.bmr',
            'view_mode': 'list,form',
            'domain': [('production_id', '=', self.production_id.id)],
        }

    def action_view_qc_tests(self):
        self.ensure_one()
        return {
            'name': 'QC Test Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'pharma.qc.test.order',
            'view_mode': 'list,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
        }

    def action_view_deviations(self):
        self.ensure_one()
        return {
            'name': 'Deviations',
            'type': 'ir.actions.act_window',
            'res_model': 'pharma.deviation',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.production_id.id)],
        }

    def action_view_capas(self):
        self.ensure_one()
        return {
            'name': 'CAPAs',
            'type': 'ir.actions.act_window',
            'res_model': 'pharma.capa',
            'view_mode': 'list,form',
            'domain': [('deviation_id.batch_id', '=', self.production_id.id)],
        }

    def action_view_coa(self):
        self.ensure_one()
        return {
            'name': 'CoAs',
            'type': 'ir.actions.act_window',
            'res_model': 'pharma.coa',
            'view_mode': 'list,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
        }

    def action_view_genealogy(self):
        self.ensure_one()
        return {
            'name': 'Genealogy',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot',
            'view_mode': 'form',
            'res_id': self.lot_id.id,
        }


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('pharma.qa.release') or 'New'
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            bmr = rec.production_id
            qc_tests = self.env['pharma.qc.test.order'].search([
                ('lot_id', '=', rec.lot_id.id)
            ])
            if not qc_tests or not all(t.status == 'passed' for t in qc_tests):
                raise ValidationError("All QC Test Orders for the produced lots must be passed before QA Release.")

            open_oos = self.env['pharma.oos.investigation'].search_count([
                ('result_line_id.test_order_id', 'in', qc_tests.ids),
                ('closed_on', '=', False)
            ])
            if open_oos > 0:
                raise ValidationError("There are open OOS investigations for this batch. They must be closed before QA Release.")

            open_deviations = self.env['pharma.deviation'].search_count([
                ('batch_id', '=', bmr.id),
                ('status', 'in', ('open', 'under_investigation'))
            ])
            if open_deviations > 0:
                raise ValidationError("There are open or under investigation deviations for this batch. They must be resolved before QA Release.")

            passed_tests = qc_tests.filtered(lambda t: t.status == 'passed')
            primary_test_order = passed_tests[0] if passed_tests else False

            coa_vals = {
                'batch_id': bmr.id,
                'product_id': rec.product_id.id,
                'lot_id': rec.lot_id.id,
                'released_by': self.env.user.id,
                'release_date': fields.Datetime.now(),
                'qc_test_order_id': primary_test_order.id if primary_test_order else False,
                'is_locked': True,
            }
            
            lines = []
            for order in passed_tests:
                for res_line in order.result_line_ids:
                    mapped_status = 'pass' if res_line.status == 'pass' else 'oos'
                    lines.append((0, 0, {
                        'parameter': res_line.parameter,
                        'expected_min': res_line.expected_min,
                        'expected_max': res_line.expected_max,
                        'actual_value': res_line.actual_value,
                        'uom': res_line.uom,
                        'status': mapped_status,
                    }))
            coa_vals['coa_line_ids'] = lines

            coa = self.env['pharma.coa'].create(coa_vals)
            rec.coa_id = coa.id
            rec.state = 'released'
            
            if rec.lot_id:
                rec.lot_id.write({'lot_status': 'released'})

            bmr.message_post(body=f"Batch released by QA. Certificate of Analysis {coa.name} has been generated.")
