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
from odoo.exceptions import UserError, ValidationError

from .stock_picking import _unreleased_lots_message


class PharmaShipment(models.Model):
    """Shipment of one delivery order.

    Created from a validated delivery order with the Dispatch button. The
    product lines and packages are copied from the delivery order at that
    moment, so the shipment keeps what actually left the warehouse.
    """
    _name = 'pharma.shipment'
    _description = 'Shipment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'dispatch_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                       readonly=True, default='New', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, readonly=True,
        copy=False, tracking=True)
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company)

    # Delivery order
    picking_id = fields.Many2one(
        'stock.picking', string='Delivery Order', required=True, readonly=True,
        index=True, ondelete='restrict', copy=False,
        domain="[('picking_type_code', '=', 'outgoing')]")
    partner_id = fields.Many2one(related='picking_id.partner_id', store=True,
                                 string='Customer')
    origin = fields.Char(related='picking_id.origin', string='Source Document')

    # Dates
    dispatch_date = fields.Datetime(
        string='Dispatch Date', required=True, tracking=True,
        default=fields.Datetime.now,
        help='Date and time the vehicle leaves the warehouse.')
    expected_delivery_date = fields.Datetime(
        string='Expected Delivery Date', tracking=True,
        help='Date and time the consignment is expected at the customer.')
    delivered_date = fields.Datetime(string='Delivered On', readonly=True,
                                     copy=False, tracking=True)

    # Transport
    high_security = fields.Boolean(
        string='High Security', readonly=True,
        help='Set from the checklist template. The transporter contract must '
             'cover high-security consignments.')
    transport_contract_id = fields.Many2one(
        'pharma.transport.contract', string='Transport Contract',
        compute='_compute_transport_contract', store=True, tracking=True,
        help="The transporter's active contract on the dispatch date. Fixed "
             'once the shipment is dispatched.')
    transporter_id = fields.Many2one(
        'res.partner', string='Transporter', tracking=True,
        domain="[('is_company', '=', True)]",
        help='Transport contractor carrying the consignment.')
    driver_ids = fields.Many2many(
        'res.partner', 'pharma_shipment_driver_rel', 'shipment_id',
        'partner_id', string='Drivers / Personnel',
        domain="[('is_company', '=', False), ('parent_id', '=', transporter_id)]",
        help='Drivers and escorts in the vehicle. High-security consignments '
             'may carry more than one person. Pick from the contacts of the '
             'transporter; new ones are created under the transporter.')

    # Contents
    line_ids = fields.One2many('pharma.shipment.line', 'shipment_id',
                               string='Products', copy=False)
    package_ids = fields.Many2many(
        'stock.package', 'pharma_shipment_package_rel', 'shipment_id',
        'package_id', string='Packages', readonly=True, copy=False)
    package_count = fields.Integer(compute='_compute_package_count',
                                   string='Number of Packages')
    total_weight = fields.Float(compute='_compute_package_count',
                                string='Shipping Weight',
                                help='Sum of the shipping weight of the packages.')
    note = fields.Html(string='Notes')
    transport_reason = fields.Selection([
        ('supply', 'Supply to Customer'),
        ('branch_transfer', 'Stock Transfer to Own Branch'),
        ('job_work', 'Job Work'),
        ('approval', 'Supply on Approval / Sample'),
        ('return', 'Return'),
        ('other', 'Other (not a supply)'),
    ], string='Reason for Transport', required=True, default='supply',
        tracking=True,
        help='Printed on the delivery challan. Tax is shown only for a supply.')
    transport_mode = fields.Selection([
        ('road', 'Road'), ('rail', 'Rail'), ('air', 'Air'), ('ship', 'Ship'),
    ], string='Mode of Transport', required=True, default='road')
    lr_number = fields.Char(
        string='LR / GR No.', tracking=True,
        help="Transporter's consignment note: lorry receipt / goods receipt for "
             "road, RR for rail, AWB for air, bill of lading for ship.")
    lr_date = fields.Date(string='LR / GR Date')
    eway_bill_number = fields.Char(string='E-way Bill No.', tracking=True)
    eway_bill_date = fields.Date(string='E-way Bill Date')
    eway_bill_valid_until = fields.Datetime(string='E-way Bill Valid Until')
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount_untaxed = fields.Monetary(compute='_compute_amounts',
                                     string='Taxable Value')
    amount_tax = fields.Monetary(compute='_compute_amounts', string='Tax')
    amount_total = fields.Monetary(compute='_compute_amounts',
                                   string='Consignment Value')
    eway_bill_expected = fields.Boolean(
        compute='_compute_amounts',
        help='Consignment value above the general e-way bill limit (Rs 50,000).')
    challan_number = fields.Char(
        string='Delivery Challan No.', readonly=True, copy=False, tracking=True,
        help='Serial number of the delivery challan, given when the shipment is dispatched.')
    vehicle_number = fields.Char(string='Vehicle Number', tracking=True,
                                 help='Registration number of the vehicle.')
    seal_number = fields.Char(string='Seal Number', tracking=True,
                              help='Number of the tamper-evident seal on the vehicle or container.')

    # Pre-loading checklist
    checklist_template_id = fields.Many2one(
        'pharma.dispatch.checklist.template', string='Checklist Template',
        tracking=True, ondelete='restrict',
        domain="[('company_id', 'in', (False, company_id))]",
        help='Taken from the delivery order.')
    checklist_ids = fields.One2many('pharma.dispatch.checklist', 'shipment_id',
                                    string='Checklists', copy=False)
    checklist_id = fields.Many2one('pharma.dispatch.checklist',
                                   compute='_compute_checklist',
                                   string='Current Checklist')
    checklist_state = fields.Selection(
        [('in_progress', 'In Progress'), ('passed', 'Passed'),
         ('failed', 'Failed'), ('rejected', 'Vehicle Rejected')],
        compute='_compute_checklist', string='Checklist')
    checklist_count = fields.Integer(compute='_compute_checklist')

    # Temperature
    temperature_controlled = fields.Boolean(
        string='Temperature Controlled', tracking=True,
        help='The consignment must stay within the storage range during transit.')
    temp_min = fields.Float(string='Min (°C)', digits=(4, 1), default=2.0,
                            tracking=True)
    temp_max = fields.Float(string='Max (°C)', digits=(4, 1), default=8.0,
                            tracking=True)
    temperature_ids = fields.One2many('pharma.shipment.temperature',
                                      'shipment_id', string='Temperature Log',
                                      copy=False)
    excursion_count = fields.Integer(compute='_compute_excursion_count',
                                     store=True, string='Excursions')
    recorded_min = fields.Float(compute='_compute_temperature_summary',
                                digits=(4, 1), string='Lowest (°C)')
    recorded_max = fields.Float(compute='_compute_temperature_summary',
                                digits=(4, 1), string='Highest (°C)')
    excursion_decision = fields.Selection([
        ('pending', 'Pending QA Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ], string='Excursion Decision', compute='_compute_excursion_decision',
        store=True, readonly=False, tracking=True, copy=False,
        help='QA decision on goods exposed to a temperature excursion.')
    excursion_reviewed_by = fields.Many2one('res.users', readonly=True,
                                            copy=False, string='Reviewed By')
    excursion_review_note = fields.Text(string='Review Remarks', copy=False)

    # Proof of delivery
    received_by = fields.Char(string='Received By', copy=False, tracking=True,
                              help='Name and designation of the person who received the goods.')
    received_date = fields.Datetime(string='Received On', copy=False)
    receiver_signature = fields.Binary(string='Receiver Signature', copy=False,
                                       attachment=True)
    pod_attachment_ids = fields.Many2many(
        'ir.attachment', 'pharma_shipment_pod_attachment_rel', 'shipment_id',
        'attachment_id', string='Signed Documents', copy=False,
        help='Scan of the signed delivery challan or customer receipt.')
    seal_intact = fields.Boolean(string='Seal Intact on Arrival', default=True,
                                 copy=False)
    receipt_note = fields.Text(string='Condition on Arrival', copy=False)
    has_discrepancy = fields.Boolean(
        compute='_compute_has_discrepancy', store=True,
        string='Delivery Discrepancy',
        help='Shortage, damage or a broken seal was recorded at delivery.')

    _picking_uniq = models.UniqueIndex(
        '(picking_id) WHERE state != \'cancel\'',
        'A delivery order can only have one active shipment.')

    @api.depends('package_ids', 'package_ids.shipping_weight')
    def _compute_package_count(self):
        for shipment in self:
            shipment.package_count = len(shipment.package_ids)
            shipment.total_weight = sum(shipment.package_ids.mapped('shipping_weight'))

    @api.depends('checklist_ids.state')
    def _compute_checklist(self):
        for shipment in self:
            shipment.checklist_id = shipment.checklist_ids.sorted('id', reverse=True)[:1]
            shipment.checklist_state = shipment.checklist_id.state
            shipment.checklist_count = len(shipment.checklist_ids)

    @api.depends('temperature_ids.is_excursion')
    def _compute_excursion_count(self):
        for shipment in self:
            shipment.excursion_count = len(
                shipment.temperature_ids.filtered('is_excursion'))

    @api.depends('temperature_ids.temperature')
    def _compute_temperature_summary(self):
        for shipment in self:
            temps = shipment.temperature_ids.mapped('temperature')
            shipment.recorded_min = min(temps) if temps else 0.0
            shipment.recorded_max = max(temps) if temps else 0.0

    EWAY_BILL_LIMIT = 50000.0

    @api.depends('line_ids.value', 'line_ids.tax_amount', 'transport_reason')
    def _compute_amounts(self):
        for shipment in self:
            untaxed = sum(shipment.line_ids.mapped('value'))
            tax = sum(shipment.line_ids.mapped('tax_amount')) \
                if shipment.transport_reason == 'supply' else 0.0
            shipment.amount_untaxed = untaxed
            shipment.amount_tax = tax
            shipment.amount_total = untaxed + tax
            shipment.eway_bill_expected = (
                shipment.currency_id.name == 'INR'
                and shipment.amount_total > self.EWAY_BILL_LIMIT)

    def _challan_shows_tax(self):
        self.ensure_one()
        return self.transport_reason == 'supply' and bool(self.line_ids.tax_ids)

    def _challan_tax_summary(self):
        """Tax by component for the challan (e.g. CGST 6 %, SGST 6 %):
        a list of dicts with name, base and amount."""
        self.ensure_one()
        summary = {}
        for line in self.line_ids.filtered('tax_ids'):
            for tax in line._tax_result()['taxes']:
                row = summary.setdefault(tax['id'], {
                    'name': tax['name'], 'base': 0.0, 'amount': 0.0})
                row['base'] += tax['base']
                row['amount'] += tax['amount']
        return list(summary.values())

    def _challan_amount_in_words(self):
        self.ensure_one()
        words = self.currency_id.amount_to_text(self.amount_total) or ''
        return (words[:1].upper() + words[1:] + ' only') if words else ''

    @api.model
    def _financial_year_start(self, day):
        """Start of the Indian financial year (1 April) holding day."""
        year = day.year if day.month >= 4 else day.year - 1
        return fields.Date.to_date('%s-04-01' % year)

    def _next_challan_number(self):
        """Serial number per financial year, e.g. DC/26-27/00001 (14 of the
        16 characters Rule 55 allows)."""
        self.ensure_one()
        day = fields.Date.context_today(self, self.dispatch_date)
        fy_start = self._financial_year_start(day)
        fy_end = fy_start.replace(year=fy_start.year + 1, day=31, month=3)
        sequence = self.env.ref('pharma_dispatch.seq_pharma_delivery_challan_fy').sudo()
        DateRange = self.env['ir.sequence.date_range'].sudo()
        if not DateRange.search_count([('sequence_id', '=', sequence.id),
                                       ('date_from', '=', fy_start)]):
            DateRange.create({'sequence_id': sequence.id, 'date_from': fy_start,
                              'date_to': fy_end, 'number_next': 1})
        number = sequence.next_by_id(sequence_date=day)
        return 'DC/%02d-%02d/%s' % (fy_start.year % 100, fy_end.year % 100, number)

    @api.depends('excursion_count')
    def _compute_excursion_decision(self):
        for shipment in self:
            if not shipment.excursion_count:
                shipment.excursion_decision = False
            elif not shipment.excursion_decision:
                shipment.excursion_decision = 'pending'

    @api.depends('seal_intact', 'state', 'line_ids.shortage_qty',
                 'line_ids.damaged_qty')
    def _compute_has_discrepancy(self):
        for shipment in self:
            shipment.has_discrepancy = shipment.state == 'delivered' and (
                not shipment.seal_intact
                or any(line.shortage_qty or line.damaged_qty
                       for line in shipment.line_ids))

    @api.constrains('temperature_controlled', 'temp_min', 'temp_max')
    def _check_temp_range(self):
        for shipment in self:
            if shipment.temperature_controlled and shipment.temp_min >= shipment.temp_max:
                raise ValidationError(self.env._(
                    'The minimum temperature of %s must be below the maximum.',
                    shipment.name))

    @api.constrains('dispatch_date', 'expected_delivery_date')
    def _check_dates(self):
        for shipment in self:
            if (shipment.expected_delivery_date and shipment.dispatch_date
                    and shipment.expected_delivery_date < shipment.dispatch_date):
                raise ValidationError(self.env._(
                    'The expected delivery date of %s is before its dispatch date.',
                    shipment.name))

    @api.onchange('transporter_id')
    def _onchange_transporter_id(self):
        """Drop drivers who do not belong to the new transporter."""
        self.driver_ids = self.driver_ids.filtered(
            lambda d: d.parent_id == self.transporter_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('pharma.shipment') or 'New'
        return super().create(vals_list)

    @api.model
    def _temperature_from_template(self, template):
        vals = {'high_security': template.high_security}
        if template.temperature_controlled:
            vals.update({'temperature_controlled': True,
                         'temp_min': template.temp_min, 'temp_max': template.temp_max})
        return vals

    @api.depends('transporter_id', 'dispatch_date', 'company_id', 'state')
    def _compute_transport_contract(self):
        Contract = self.env['pharma.transport.contract']
        for shipment in self:
            if shipment.state != 'draft' and shipment.transport_contract_id:
                continue  # keep the contract the shipment travelled under
            if not shipment.transporter_id or not shipment.dispatch_date:
                shipment.transport_contract_id = False
                continue
            shipment.transport_contract_id = Contract._find_active(
                shipment.transporter_id, shipment.company_id,
                fields.Date.context_today(shipment, shipment.dispatch_date))

    @api.onchange('checklist_template_id')
    def _onchange_checklist_template_id(self):
        self.update(self._temperature_from_template(self.checklist_template_id))

    @api.model
    def _line_expiry(self, move_line):
        lot = move_line.lot_id
        expiry = lot.expiry_date or lot.expiration_date or move_line.expiration_date
        return fields.Date.to_date(expiry) if expiry else False

    @api.model
    def _line_sale_line(self, move_line):
        move = move_line.move_id
        return 'sale_line_id' in move._fields and move.sale_line_id

    @api.model
    def _line_price_unit(self, move_line):
        """Unit value in the move-line unit, before tax: the sales order price
        net of discount when Sales is installed, otherwise the product's
        sales price."""
        sale_line = self._line_sale_line(move_line)
        if sale_line:
            price = sale_line.price_unit * (1 - (sale_line.discount or 0.0) / 100.0)
            return sale_line.product_uom_id._compute_price(price, move_line.uom_id)
        return move_line.product_id.uom_id._compute_price(
            move_line.product_id.lst_price, move_line.uom_id)

    @api.model
    def _line_taxes(self, move_line, picking):
        sale_line = self._line_sale_line(move_line)
        if sale_line:
            return sale_line.tax_ids
        return move_line.product_id.taxes_id.filtered(
            lambda t: t.company_id in picking.company_id.parent_ids)

    @api.model
    def _prepare_from_picking(self, picking):
        """Values of a new shipment for a delivery order, with its products
        (one line per move line) and its packages."""
        lines = [fields.Command.create({
            'product_id': ml.product_id.id,
            'lot_id': ml.lot_id.id,
            'move_id': ml.move_id.id,
            'expiration_date': self._line_expiry(ml),
            'price_unit': self._line_price_unit(ml),
            'tax_ids': [fields.Command.set(self._line_taxes(ml, picking).ids)],
            'quantity': ml.quantity,
            'uom_id': ml.uom_id.id,
            'package_id': ml.result_package_id.id,
        }) for ml in picking.move_line_ids.filtered('quantity')]
        return {
            'picking_id': picking.id,
            'company_id': picking.company_id.id,
            'checklist_template_id': picking.checklist_template_id.id,
            **self._temperature_from_template(picking.checklist_template_id),
            'line_ids': lines,
            'package_ids': [fields.Command.set(picking._get_packages_for_print().ids)],
        }

    def action_dispatch(self):
        # Look the contract up again: it may have been activated or ended
        # since the shipment was created.
        self.filtered(lambda s: s.state == 'draft')._compute_transport_contract()
        for shipment in self:
            if shipment.state != 'draft':
                raise UserError(self.env._('Only draft shipments can be dispatched.'))
            if not shipment.transporter_id:
                raise UserError(self.env._('Set the transporter of %s before dispatching.',
                                           shipment.name))
            contract = shipment.transport_contract_id
            if not contract:
                raise UserError(self.env._(
                    '%(transporter)s has no active transport contract on the dispatch '
                    'date of %(name)s.',
                    transporter=shipment.transporter_id.name, name=shipment.name))
            if not contract._covers(shipment):
                raise UserError(self.env._(
                    'Contract %(contract)s of %(transporter)s does not cover this '
                    'consignment (%(kind)s).',
                    contract=contract.name, transporter=shipment.transporter_id.name,
                    kind=shipment._consignment_kind()))
            if not shipment.driver_ids:
                raise UserError(self.env._('Assign at least one driver to %s before dispatching.',
                                           shipment.name))
            crew_issues = shipment._pharma_crew_check()
            if crew_issues:
                raise UserError(self.env._(
                    'The crew of %(name)s is not qualified for this consignment:\n%(issues)s',
                    name=shipment.name, issues='\n'.join('- ' + i for i in crew_issues)))
            if not shipment.expected_delivery_date:
                raise UserError(self.env._('Set the expected delivery date of %s before dispatching.',
                                           shipment.name))
            unreleased = shipment.line_ids.lot_id.filtered(
                lambda lot: lot.lot_status != 'released')
            if unreleased:
                raise UserError(self.env._(
                    'GMP: %(name)s carries batches that are no longer QA-released '
                    '(recalled, on hold or rejected after the delivery was '
                    'validated). Do not dispatch:\n%(lots)s',
                    name=shipment.name,
                    lots=_unreleased_lots_message(self.env, unreleased)))
            checklist = shipment.checklist_id
            if not checklist or checklist.state != 'passed':
                raise UserError(self.env._(
                    'The pre-loading checklist of %s has not passed.', shipment.name))
            if checklist.vehicle_number != shipment.vehicle_number:
                raise UserError(self.env._(
                    'The checklist of %(name)s was done on vehicle %(checked)s, '
                    'but the shipment is on %(vehicle)s. Check this vehicle.',
                    name=shipment.name, checked=checklist.vehicle_number,
                    vehicle=shipment.vehicle_number))
        self.write({'state': 'dispatched'})
        for shipment in self:
            if not shipment.challan_number:
                shipment.challan_number = shipment._next_challan_number()

    crew_issues = fields.Text(compute='_compute_crew_issues', string='Crew Issues')

    @api.depends('driver_ids', 'transporter_id', 'expected_delivery_date', 'dispatch_date',
                 'temperature_controlled', 'high_security')
    def _compute_crew_issues(self):
        for shipment in self:
            issues = shipment._pharma_crew_check()
            shipment.crew_issues = '\n'.join(issues) or False

    def _pharma_crew_check(self):
        """Problems with the people assigned to the shipment, as lines of text."""
        self.ensure_one()
        _ = self.env._
        if not self.driver_ids:
            return []
        until = fields.Date.context_today(
            self, self.expected_delivery_date or self.dispatch_date or fields.Datetime.now())
        issues = []
        if not self.driver_ids.filtered(lambda p: p.transport_role == 'driver'):
            issues.append(_('No qualified driver: everyone assigned is registered as an escort or not at all.'))
        transporter = self.transporter_id.commercial_partner_id
        for person in self.driver_ids:
            problems = person._pharma_crew_issues(
                until, cold_chain=self.temperature_controlled,
                high_security=self.high_security)
            if transporter and person.commercial_partner_id != transporter:
                problems.append(_('does not belong to %s', transporter.name))
            if problems:
                issues.append('%s: %s' % (person.name, '; '.join(problems)))
        return issues

    def _consignment_kind(self):
        self.ensure_one()
        kinds = [self.env._('cold chain') if self.temperature_controlled
                 else self.env._('ambient')]
        if self.high_security:
            kinds.append(self.env._('high security'))
        return ', '.join(kinds)

    def action_start_checklist(self):
        """Start the pre-loading checklist of the vehicle at the dock."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(self.env._('The checklist is done before dispatch.'))
        if not self.vehicle_number:
            raise UserError(self.env._('Enter the vehicle number first.'))
        if not self.checklist_template_id:
            raise UserError(self.env._('Choose a checklist template first.'))
        if self.checklist_id.state in ('in_progress', 'passed') \
                and self.checklist_id.vehicle_number == self.vehicle_number:
            raise UserError(self.env._('This vehicle already has a checklist.'))
        Checklist = self.env['pharma.dispatch.checklist']
        checklist = Checklist.create({
            'shipment_id': self.id,
            'template_id': self.checklist_template_id.id,
            'vehicle_number': self.vehicle_number,
            'temperature_controlled': self.temperature_controlled,
            'temp_min': self.temp_min,
            'temp_max': self.temp_max,
            'line_ids': Checklist._prepare_lines(self.checklist_template_id, self),
        })
        return self._open_checklists(checklist)

    def action_view_checklists(self):
        self.ensure_one()
        return self._open_checklists(self.checklist_ids)

    def _open_checklists(self, checklists):
        action = {
            'type': 'ir.actions.act_window',
            'name': self.env._('Checklists'),
            'res_model': 'pharma.dispatch.checklist',
            'domain': [('id', 'in', checklists.ids)],
            'context': {'create': False},
        }
        if len(checklists) == 1:
            action.update(view_mode='form', res_id=checklists.id)
        else:
            action.update(view_mode='list,form')
        return action

    def action_print_packing_list(self):
        return self.env.ref('pharma_dispatch.action_report_packing_list').report_action(self)

    def action_print_delivery_challan(self):
        return self.env.ref('pharma_dispatch.action_report_delivery_challan').report_action(self)

    def _packing_groups(self):
        """Shipment lines grouped by package for the packing list: a list of
        (package or empty recordset, lines), packages first, loose items last."""
        self.ensure_one()
        groups = []
        for package in self.line_ids.package_id.sorted('complete_name'):
            groups.append((package, self.line_ids.filtered(lambda l: l.package_id == package)))
        loose = self.line_ids.filtered(lambda l: not l.package_id)
        if loose:
            groups.append((self.env['stock.package'], loose))
        return groups

    def action_mark_delivered(self):
        """Close the journey with the proof of delivery entered on the
        Proof of Delivery tab."""
        for shipment in self:
            if shipment.state != 'dispatched':
                raise UserError(self.env._('Only dispatched shipments can be marked as delivered.'))
            if not shipment.received_by:
                raise UserError(self.env._('Enter who received %s.', shipment.name))
            if not (shipment.receiver_signature or shipment.pod_attachment_ids):
                raise UserError(self.env._(
                    'Add the receiver signature or the signed delivery document of %s.',
                    shipment.name))
            if shipment.temperature_controlled and not shipment.temperature_ids:
                raise UserError(self.env._(
                    '%s is temperature controlled: record the transit temperatures before closing it.',
                    shipment.name))
        now = fields.Datetime.now()
        for shipment in self:
            received = shipment.received_date or now
            shipment.write({'state': 'delivered', 'delivered_date': received,
                            'received_date': received})
            if shipment.has_discrepancy:
                shipment.message_post(body=self.env._(
                    'Delivered with a discrepancy (shortage, damage or broken seal). '
                    'See the Proof of Delivery tab.'))

    def _check_excursion_review(self):
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(self.env._('Only inventory managers can decide on temperature excursions.'))
        if self.filtered(lambda s: s.excursion_decision != 'pending'):
            raise UserError(self.env._('There is no pending excursion to review.'))

    def action_accept_excursion(self):
        self._check_excursion_review()
        self.write({'excursion_decision': 'accepted',
                    'excursion_reviewed_by': self.env.user.id})

    def action_reject_excursion(self):
        self._check_excursion_review()
        self.write({'excursion_decision': 'rejected',
                    'excursion_reviewed_by': self.env.user.id})

    def action_cancel(self):
        if self.filtered(lambda s: s.state == 'delivered'):
            raise UserError(self.env._('A delivered shipment cannot be cancelled.'))
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        self.filtered(lambda s: s.state == 'cancel').write({'state': 'draft'})

    def action_open_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
        }

    @api.ondelete(at_uninstall=False)
    def _unlink_except_dispatched(self):
        if self.filtered(lambda s: s.state in ('dispatched', 'delivered')):
            raise UserError(self.env._('Dispatched or delivered shipments cannot be deleted; cancel them instead.'))
