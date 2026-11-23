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
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestShipment(TransactionCase):
    # 1x1 transparent PNG
    SIGNATURE = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkY'
                 'AAAAAYAAjCB0C8AAAAASUVORK5CYII=')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref('stock.group_tracking_lot')             + cls.env.ref('stock.group_production_lot')
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.customer = cls.env['res.partner'].create({'name': 'City Hospital'})
        cls.transporter = cls.env['res.partner'].create(
            {'name': 'Cold Chain Logistics'})
        cls.contract = cls._make_contract(cls.transporter)
        cls.driver_1 = cls.env['res.partner'].create(
            {'name': 'Driver One', 'parent_id': cls.transporter.id})
        cls.driver_2 = cls.env['res.partner'].create(
            {'name': 'Escort Two', 'parent_id': cls.transporter.id})
        cls._qualify(cls.driver_1, 'driver')
        cls._qualify(cls.driver_2, 'escort')
        cls.product = cls.env['product.product'].create({
            'name': 'Paracetamol 500 mg', 'is_storable': True, 'tracking': 'lot'})
        cls.product.lst_price = 12.5
        cls.lot = cls.env['stock.lot'].create(
            {'name': 'B-001', 'product_id': cls.product.id})
        cls.lot.lot_status = 'released'
        cls.env['stock.quant']._update_available_quantity(
            cls.product, cls.stock, 100, lot_id=cls.lot)

    @classmethod
    def _qualify(cls, person, role='driver', **vals):
        values = dict({
            'transport_role': role,
            'cold_chain_trained': True,
            'background_check_date': '2026-01-01', 'background_check_valid_until': '2099-12-31',
        }, **vals)
        if role == 'driver':
            values.setdefault('driving_licence_number', 'KL07 20190012345')
            values.setdefault('driving_licence_valid_until', '2099-12-31')
        person.write(values)
        return person

    @classmethod
    def _make_contract(cls, transporter, **vals):
        """An active contract, written straight to Active for test setup."""
        values = dict({
            'transporter_id': transporter.id,
            'date_start': '2020-01-01', 'date_end': '2099-12-31',
            'service_ambient': True, 'service_cold_chain': True,
        }, **vals)
        contract = cls.env['pharma.transport.contract'].create(values)
        contract.state = 'active'
        return contract

    def _validated_delivery(self, qty=40, template=True):
        picking = self.env['stock.picking'].create({
            'checklist_template_id': template and self.env.ref(
                'pharma_dispatch.checklist_template_standard').id,
            'picking_type_id': self.warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'location_id': self.stock.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
                'uom_id': self.product.uom_id.id,
                'location_id': self.stock.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.action_put_in_pack()
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        return picking

    def test_dispatch_creates_shipment_from_delivery(self):
        picking = self._validated_delivery()
        action = picking.action_create_shipment()
        shipment = self.env['pharma.shipment'].browse(action['res_id'])
        self.assertTrue(shipment.name.startswith('SHP/'))
        self.assertEqual(shipment.picking_id, picking)
        self.assertEqual(shipment.partner_id, self.customer)
        self.assertEqual(len(shipment.line_ids), 1)
        line = shipment.line_ids
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.lot_id, self.lot)
        self.assertEqual(line.quantity, 40)
        self.assertTrue(line.package_id)
        self.assertEqual(shipment.package_ids, line.package_id)
        self.assertEqual(picking.active_shipment_count, 1)
        with self.assertRaises(UserError):
            picking.action_create_shipment()

    def test_shipment_needs_checklist_template(self):
        picking = self._validated_delivery(template=False)
        with self.assertRaises(UserError):
            picking.action_create_shipment()
        picking.checklist_template_id = self.env.ref(
            'pharma_dispatch.checklist_template_standard')
        shipment = self.env['pharma.shipment'].browse(
            picking.action_create_shipment()['res_id'])
        self.assertEqual(shipment.checklist_template_id, picking.checklist_template_id)

    def test_cold_chain_template_sets_shipment_range(self):
        template = self.env['pharma.dispatch.checklist.template'].create({
            'name': 'Cold', 'temperature_controlled': True,
            'temp_min': 2.0, 'temp_max': 8.0,
            'line_ids': [(0, 0, {'name': 'Front', 'section': 'temperature',
                                 'check_type': 'numeric', 'severity': 'critical',
                                 'applies_to': 'cold_chain'})],
        })
        picking = self._validated_delivery()
        picking.checklist_template_id = template
        shipment = self.env['pharma.shipment'].browse(
            picking.action_create_shipment()['res_id'])
        self.assertTrue(shipment.temperature_controlled)
        self.assertEqual((shipment.temp_min, shipment.temp_max), (2.0, 8.0))
        shipment.vehicle_number = 'KL-07-AB-1234'
        checklist = self._start(shipment)
        self.assertEqual(checklist.line_ids.max_value, 8.0)

    def test_cannot_dispatch_with_unfinished_checklist(self):
        shipment = self._draft_shipment()
        checklist = self._start(shipment)
        with self.assertRaises(UserError):
            shipment.action_dispatch()  # in progress
        self._answer(checklist)
        with self.assertRaises(UserError):
            shipment.action_dispatch()  # answered but not completed
        checklist.action_complete()
        shipment.action_dispatch()
        self.assertEqual(shipment.state, 'dispatched')

    def test_dispatch_requires_transport_details(self):
        shipment = self.env['pharma.shipment'].browse(
            self._validated_delivery().action_create_shipment()['res_id'])
        with self.assertRaises(UserError):
            shipment.action_dispatch()
        shipment.write({
            'transporter_id': self.transporter.id,
            'driver_ids': [(6, 0, (self.driver_1 | self.driver_2).ids)],
            'expected_delivery_date': '2099-01-01 10:00:00',
            'vehicle_number': 'KL-07-AB-1234',
        })
        with self.assertRaises(UserError):
            shipment.action_dispatch()  # no checklist yet
        self._pass_checklist(shipment)
        shipment.action_dispatch()
        self.assertEqual(shipment.state, 'dispatched')
        self.assertEqual(len(shipment.driver_ids), 2)
        with self.assertRaises(UserError):
            shipment.action_mark_delivered()  # no proof of delivery yet
        shipment.write({'received_by': 'Pharmacist A', 'receiver_signature': self.SIGNATURE})
        shipment.action_mark_delivered()
        self.assertEqual(shipment.state, 'delivered')
        self.assertTrue(shipment.delivered_date)
        self.assertFalse(shipment.has_discrepancy)

    def test_expected_date_not_before_dispatch(self):
        shipment = self.env['pharma.shipment'].browse(
            self._validated_delivery().action_create_shipment()['res_id'])
        with self.assertRaises(ValidationError):
            shipment.write({'dispatch_date': '2030-01-02 00:00:00',
                            'expected_delivery_date': '2030-01-01 00:00:00'})

    def test_undone_delivery_cannot_dispatch(self):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'location_id': self.stock.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        with self.assertRaises(UserError):
            picking.action_create_shipment()

    def test_cancelled_shipment_allows_new_one(self):
        picking = self._validated_delivery()
        first = self.env['pharma.shipment'].browse(picking.action_create_shipment()['res_id'])
        first.action_cancel()
        second = self.env['pharma.shipment'].browse(picking.action_create_shipment()['res_id'])
        self.assertNotEqual(first, second)
        self.assertEqual(picking.shipment_count, 2)

    def _answer(self, checklist, failing=(), readings=None):
        """Answer every check: yes, readings in range, text filled, photo
        added. Checks whose name contains a word in failing get No."""
        for line in checklist.line_ids:
            vals = {}
            if line.check_type == 'yes_no':
                fail = any(word in line.name for word in failing)
                vals['answer'] = 'no' if fail else 'yes'
            elif line.check_type == 'numeric':
                value = (readings or {}).get(line.name)
                vals['value_numeric'] = value if value is not None else \
                    (line.min_value + line.max_value) / 2
            else:
                vals['value_text'] = 'LOG-001'
            if line.photo_required:
                vals['photo'] = self.SIGNATURE
            line.write(vals)

    def _pass_checklist(self, shipment):
        action = shipment.action_start_checklist()
        checklist = self.env['pharma.dispatch.checklist'].browse(action['res_id'])
        self._answer(checklist)
        checklist.action_complete()
        self.assertEqual(checklist.state, 'passed')
        return checklist

    def _draft_shipment(self, **vals):
        shipment = self.env['pharma.shipment'].browse(
            self._validated_delivery().action_create_shipment()['res_id'])
        shipment.write(dict({
            'transporter_id': self.transporter.id,
            'driver_ids': [(6, 0, self.driver_1.ids)],
            'expected_delivery_date': '2099-01-01 10:00:00',
            'vehicle_number': 'KL-07-AB-1234',
        }, **vals))
        return shipment

    def _start(self, shipment):
        return self.env['pharma.dispatch.checklist'].browse(
            shipment.action_start_checklist()['res_id'])

    def test_checklist_ambient_skips_cold_chain_checks(self):
        checklist = self._start(self._draft_shipment())
        names = checklist.line_ids.mapped('name')
        self.assertIn('Cargo-space temperature (ambient vehicle)', names)
        self.assertFalse([n for n in names if 'Reefer' in n])
        with self.assertRaises(UserError):
            checklist.action_complete()  # unanswered

    def test_critical_failure_rejects_vehicle(self):
        shipment = self._draft_shipment()
        checklist = self._start(shipment)
        self._answer(checklist, failing=('No pests',))
        checklist.action_complete()
        self.assertEqual(checklist.state, 'rejected')
        with self.assertRaises(UserError):
            checklist.action_override()
        with self.assertRaises(UserError):
            shipment.action_dispatch()
        # same vehicle can be re-checked after cleaning, or another one used
        shipment.vehicle_number = 'KL-07-CD-5678'
        self._pass_checklist(shipment)
        self.assertEqual(shipment.checklist_count, 2)
        shipment.action_dispatch()
        self.assertEqual(shipment.state, 'dispatched')

    def test_major_failure_needs_override(self):
        shipment = self._draft_shipment()
        checklist = self._start(shipment)
        self._answer(checklist, failing=('GPS tracker',))
        checklist.action_complete()
        self.assertEqual(checklist.state, 'failed')
        with self.assertRaises(UserError):
            checklist.action_override()  # no reason
        checklist.override_reason = 'GPS replaced by phone tracking for this trip'
        checklist.action_override()
        self.assertEqual(checklist.state, 'passed')
        self.assertTrue(checklist.overridden)
        shipment.action_dispatch()

    def test_minor_failure_does_not_block(self):
        checklist = self._start(self._draft_shipment())
        self._answer(checklist, failing=('Fire extinguisher',))
        checklist.action_complete()
        self.assertEqual(checklist.state, 'passed')
        self.assertEqual(checklist.failed_minor_count, 1)

    def test_cold_chain_reading_out_of_range_rejects(self):
        shipment = self._draft_shipment(temperature_controlled=True,
                                        temp_min=2.0, temp_max=8.0)
        checklist = self._start(shipment)
        front = 'Cargo-space temperature at the front (calibrated probe)'
        self.assertEqual(checklist.line_ids.filtered(
            lambda l: l.name == front).max_value, 8.0)
        self._answer(checklist, readings={front: 9.1})
        checklist.action_complete()
        self.assertEqual(checklist.state, 'rejected')
        self.assertFalse(shipment.temperature_ids)

    def test_cold_chain_pass_logs_preloading_temperatures(self):
        shipment = self._draft_shipment(temperature_controlled=True,
                                        temp_min=2.0, temp_max=8.0)
        checklist = self._start(shipment)
        self._answer(checklist)
        checklist.action_complete()
        self.assertEqual(checklist.state, 'passed')
        self.assertEqual(len(shipment.temperature_ids), 3)
        self.assertFalse(shipment.excursion_count)

    def test_zero_reading_counts_as_answer(self):
        checklist = self._start(self._draft_shipment(
            temperature_controlled=True, temp_min=-5.0, temp_max=5.0))
        line = checklist.line_ids.filtered(lambda l: l.check_type == 'numeric')[:1]
        self.assertEqual(line.result, 'pending')
        line.value_numeric = 0.0
        self.assertEqual(line.result, 'pass')

    def test_dispatch_blocked_when_vehicle_changed(self):
        shipment = self._draft_shipment()
        self._pass_checklist(shipment)
        shipment.vehicle_number = 'KL-07-ZZ-0001'
        with self.assertRaises(UserError):
            shipment.action_dispatch()

    def _dispatched_shipment(self, **vals):
        shipment = self.env['pharma.shipment'].browse(
            self._validated_delivery().action_create_shipment()['res_id'])
        shipment.write(dict({
            'transporter_id': self.transporter.id,
            'driver_ids': [(6, 0, self.driver_1.ids)],
            'expected_delivery_date': '2099-01-01 10:00:00',
            'vehicle_number': 'KL-07-AB-1234',
        }, **vals))
        self._pass_checklist(shipment)
        shipment.action_dispatch()
        return shipment

    def test_temperature_excursion_needs_qa_decision(self):
        shipment = self._dispatched_shipment(
            temperature_controlled=True, temp_min=2.0, temp_max=8.0)
        shipment.write({'received_by': 'Pharmacist A',
                        'receiver_signature': self.SIGNATURE})
        self.assertEqual(len(shipment.temperature_ids), 3)  # pre-loading readings
        Temp = self.env['pharma.shipment.temperature']
        Temp.create({'shipment_id': shipment.id, 'temperature': 5.0})
        self.assertFalse(shipment.excursion_decision)
        Temp.create({'shipment_id': shipment.id, 'temperature': 11.5})
        self.assertEqual(shipment.excursion_count, 1)
        self.assertEqual(shipment.excursion_decision, 'pending')
        self.assertEqual(shipment.recorded_max, 11.5)
        shipment.action_reject_excursion()
        self.assertEqual(shipment.excursion_decision, 'rejected')
        self.assertEqual(shipment.excursion_reviewed_by, self.env.user)
        with self.assertRaises(UserError):
            shipment.action_accept_excursion()

    def test_pod_shortage_and_damage(self):
        shipment = self._dispatched_shipment()
        line = shipment.line_ids
        self.assertEqual(line.received_qty, 40)
        with self.assertRaises(ValidationError):
            line.write({'received_qty': 40, 'damaged_qty': 1})
        line.write({'received_qty': 35, 'damaged_qty': 2})
        self.assertEqual(line.shortage_qty, 3)
        shipment.write({'received_by': 'Pharmacist A', 'seal_intact': True,
                        'receiver_signature': self.SIGNATURE})
        shipment.action_mark_delivered()
        self.assertTrue(shipment.has_discrepancy)

    # QA release gate -------------------------------------------------------

    def test_unreleased_batch_cannot_be_delivered(self):
        self.lot.lot_status = 'approved'  # QC approved, not QA released
        with self.assertRaisesRegex(UserError, 'QA-released'):
            self._validated_delivery()

    def test_batch_recalled_after_delivery_blocks_shipment(self):
        picking = self._validated_delivery()
        self.lot.lot_status = 'recalled'
        with self.assertRaisesRegex(UserError, 'QA-released'):
            picking.action_create_shipment()

    def test_batch_put_on_hold_blocks_dispatch(self):
        shipment = self._draft_shipment()
        self._pass_checklist(shipment)
        self.lot.lot_status = 'on_hold'
        with self.assertRaisesRegex(UserError, 'no longer QA-released'):
            shipment.action_dispatch()
        self.lot.lot_status = 'released'
        shipment.action_dispatch()
        self.assertEqual(shipment.state, 'dispatched')

    # Documents ---------------------------------------------------------------

    def test_challan_number_given_on_dispatch(self):
        shipment = self._draft_shipment()
        self.assertFalse(shipment.challan_number)
        self._pass_checklist(shipment)
        shipment.action_dispatch()
        self.assertTrue(shipment.challan_number.startswith('DC/'))

    def test_dispatch_date_set_on_dispatch(self):
        shipment = self._draft_shipment()
        shipment.write({'dispatch_date': '2026-01-01 08:00:00'})
        self._pass_checklist(shipment)
        before = fields.Datetime.now()
        shipment.action_dispatch()
        self.assertGreaterEqual(shipment.dispatch_date, before)

    def test_dispatch_blocked_when_expected_date_past(self):
        shipment = self._draft_shipment()
        self._pass_checklist(shipment)
        shipment.write({'dispatch_date': '2026-01-01 08:00:00',
                        'expected_delivery_date': '2026-01-02 08:00:00'})
        with self.assertRaises(UserError):
            shipment.action_dispatch()

    def test_line_value_and_dates(self):
        self.lot.write({'manufacture_date': '2026-01-01', 'expiry_date': '2028-12-31'})
        shipment = self._draft_shipment()
        line = shipment.line_ids
        self.assertEqual(line.price_unit, 12.5)
        self.assertEqual(line.value, 500.0)
        self.assertEqual(str(line.expiration_date), '2028-12-31')
        self.assertEqual(str(line.manufacture_date), '2026-01-01')

    def test_reports_render(self):
        shipment = self._draft_shipment(seal_number='S-123')
        Report = self.env['ir.actions.report']
        html = Report._render_qweb_html(
            'pharma_dispatch.report_packing_list', shipment.ids)[0].decode()
        self.assertIn('Packing List', html)
        self.assertIn('B-001', html)
        self.assertIn('S-123', html)
        html = Report._render_qweb_html(
            'pharma_dispatch.report_delivery_challan', shipment.ids)[0].decode()
        self.assertIn('DRAFT', html)
        self.assertIn('Triplicate for Consignor', html)
        self._pass_checklist(shipment)
        shipment.action_dispatch()
        html = Report._render_qweb_html(
            'pharma_dispatch.report_delivery_challan', shipment.ids)[0].decode()
        self.assertIn(shipment.challan_number, html)
        self.assertNotIn('not valid for transport', html)

    # Delivery challan data -------------------------------------------------

    def test_challan_number_per_financial_year(self):
        shipment = self._draft_shipment(dispatch_date='2027-02-10 09:00:00',
                                        expected_delivery_date='2027-02-11 09:00:00')
        self.assertRegex(shipment._next_challan_number(), r'^DC/26-27/\d{5}$')
        shipment.write({'dispatch_date': '2027-04-02 09:00:00',
                        'expected_delivery_date': '2027-04-03 09:00:00'})
        first = shipment._next_challan_number()
        self.assertEqual(first, 'DC/27-28/00001')
        self.assertLessEqual(len(first), 16)

    def test_challan_taxes(self):
        tax = self.env['account.tax'].create({
            'name': 'GST 12%', 'amount': 12.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'country_id': self.env.ref('base.in').id,
            'tax_group_id': self.env['account.tax.group'].create(
                {'name': 'GST', 'country_id': self.env.ref('base.in').id}).id})
        self.product.taxes_id = tax
        shipment = self._draft_shipment()
        line = shipment.line_ids
        self.assertEqual(line.tax_ids, tax)
        self.assertEqual(line.value, 500.0)
        self.assertAlmostEqual(line.tax_amount, 60.0)
        self.assertAlmostEqual(shipment.amount_total, 560.0)
        self.assertTrue(shipment._challan_shows_tax())
        summary = shipment._challan_tax_summary()
        self.assertEqual(len(summary), 1)
        self.assertAlmostEqual(summary[0]['amount'], 60.0)
        # The reason is free text and does not change the tax.
        shipment.transport_reason = 'Stock Transfer to Own Branch'
        self.assertTrue(shipment._challan_shows_tax())
        self.assertAlmostEqual(shipment.amount_total, 560.0)

    def test_eway_bill_expected_above_limit(self):
        shipment = self._draft_shipment()
        shipment.currency_id.name == 'INR' or self.skipTest('company currency is not INR')
        self.assertFalse(shipment.eway_bill_expected)
        shipment.line_ids.price_unit = 2000.0
        self.assertTrue(shipment.eway_bill_expected)

    def test_gst_state_code(self):
        partner = self.env['res.partner'].create(
            {'name': 'Kerala Pharma', 'vat': '32AAACH5678K1Z2'})
        self.assertEqual(partner._pharma_gst_state_code(), '32')

    def test_challan_shows_licences_and_transport_docs(self):
        self.customer.write({'pharma_dl_20b': 'KL-EKM-123/20B',
                             'pharma_dl_21b': 'KL-EKM-123/21B'})
        shipment = self._draft_shipment(lr_number='LR-7781', eway_bill_number='3310 2233 4455',
                                        transport_reason='Supply to Customer')
        html = self.env['ir.actions.report']._render_qweb_html(
            'pharma_dispatch.report_delivery_challan', shipment.ids)[0].decode()
        for text in ('KL-EKM-123/20B', 'KL-EKM-123/21B', 'LR-7781', '3310 2233 4455',
                     'Supply to Customer', 'Original for Consignee'):
            self.assertIn(text, html)

    # Transport contracts ---------------------------------------------------

    def _draft_contract(self, transporter, **vals):
        values = dict({
            'transporter_id': transporter.id,
            'date_start': '2026-01-01', 'date_end': '2099-12-31',
            'service_ambient': True,
        }, **vals)
        return self.env['pharma.transport.contract'].create(values)

    def _sign_all(self, contract):
        contract.document_ids = self.env['ir.attachment'].create(
            {'name': 'contract.pdf', 'raw': b'%PDF-1.4'})

    def test_contract_activation_needs_signed_document(self):
        other = self.env['res.partner'].create({'name': 'Road Movers'})
        contract = self._draft_contract(other)
        self.assertTrue(contract.name.startswith('TC/'))
        with self.assertRaisesRegex(UserError, 'signed contract'):
            contract.action_activate()
        self._sign_all(contract)
        contract.action_activate()
        self.assertEqual(contract.state, 'active')
        second = self._draft_contract(other)
        self._sign_all(second)
        with self.assertRaisesRegex(UserError, 'already has an active contract'):
            second.action_activate()

    def test_dispatch_blocked_without_contract(self):
        other = self.env['res.partner'].create({'name': 'No Contract Ltd'})
        driver = self._qualify(self.env['res.partner'].create({'name': 'D', 'parent_id': other.id}))
        shipment = self._draft_shipment(transporter_id=other.id,
                                        driver_ids=[(6, 0, driver.ids)])
        self.assertFalse(shipment.transport_contract_id)
        self._pass_checklist(shipment)
        with self.assertRaisesRegex(UserError, 'no active transport contract'):
            shipment.action_dispatch()
        # a contract activated afterwards is picked up at dispatch
        self._make_contract(other)
        shipment.action_dispatch()
        self.assertEqual(shipment.state, 'dispatched')
        self.assertTrue(shipment.transport_contract_id)

    def test_contract_must_cover_cold_chain(self):
        self.contract.service_cold_chain = False
        shipment = self._draft_shipment(temperature_controlled=True,
                                        temp_min=2.0, temp_max=8.0)
        self.assertEqual(shipment.transport_contract_id, self.contract)
        self._pass_checklist(shipment)
        with self.assertRaisesRegex(UserError, 'does not cover'):
            shipment.action_dispatch()

    def test_contract_must_cover_high_security(self):
        shipment = self._draft_shipment()
        shipment.high_security = True
        self._pass_checklist(shipment)
        with self.assertRaisesRegex(UserError, 'does not cover'):
            shipment.action_dispatch()
        self.contract.service_high_security = True
        shipment.action_dispatch()
        self.assertEqual(shipment.state, 'dispatched')

    def test_dispatched_shipment_keeps_its_contract(self):
        shipment = self._draft_shipment()
        self._pass_checklist(shipment)
        shipment.action_dispatch()
        self.contract.state = 'terminated'
        shipment.invalidate_recordset()
        self.assertEqual(shipment.transport_contract_id, self.contract)
        self.assertEqual(self.contract.shipment_count, 1)

    def test_cron_expires_and_reminds(self):
        other = self.env['res.partner'].create({'name': 'Expiring Co'})
        today = fields.Date.today()
        ended = self._make_contract(other, date_start=today - timedelta(days=400),
                                    date_end=today - timedelta(days=1))
        other2 = self.env['res.partner'].create({'name': 'Soon Co'})
        soon = self._make_contract(other2, date_start=today - timedelta(days=300),
                                   date_end=today + timedelta(days=10))
        Contract = self.env['pharma.transport.contract']
        Contract._cron_contract_validity()
        self.assertEqual(ended.state, 'expired')
        self.assertFalse(ended.active)
        self.assertEqual(Contract.search([('active', '=', False), ('id', '=', ended.id)]), ended)
        self.assertEqual(len(soon.activity_ids), 1)
        Contract._cron_contract_validity()
        self.assertEqual(len(soon.activity_ids), 1)  # no duplicate reminder

    def test_renew_creates_next_term_in_draft(self):
        other = self.env['res.partner'].create({'name': 'Renewing Co'})
        today = fields.Date.today()
        contract = self._make_contract(
            other, date_start=today - timedelta(days=300), date_end=today + timedelta(days=64),
            service_high_security=True, coverage='Kerala', reminder_days=90)
        self._sign_all(contract)
        Contract = self.env['pharma.transport.contract']
        Contract._cron_contract_validity()
        self.assertEqual(len(contract.activity_ids), 1)

        action = contract.action_renew()
        renewal = Contract.browse(action['res_id'])
        self.assertEqual(renewal.state, 'draft')
        self.assertNotEqual(renewal.name, contract.name)
        self.assertEqual(renewal.renewed_from_id, contract)
        self.assertEqual(contract.renewal_id, renewal)
        self.assertEqual(renewal.date_start, contract.date_end + timedelta(days=1))
        self.assertEqual(renewal.date_end - renewal.date_start,
                         contract.date_end - contract.date_start)
        self.assertEqual(renewal.transporter_id, other)
        self.assertTrue(renewal.service_high_security)
        self.assertEqual(renewal.coverage, 'Kerala')
        self.assertFalse(renewal.document_ids)
        with self.assertRaisesRegex(UserError, 'already renewed'):
            contract.action_renew()

        self._sign_all(renewal)
        renewal.action_activate()
        self.assertEqual(renewal.state, 'active')
        self.assertFalse(contract.activity_ids)
        Contract._cron_contract_validity()
        self.assertFalse(contract.activity_ids)  # no reminder once renewed

    def test_renew_expired_contract_starts_today(self):
        other = self.env['res.partner'].create({'name': 'Lapsed Co'})
        today = fields.Date.today()
        contract = self._make_contract(other, date_start=today - timedelta(days=400),
                                       date_end=today - timedelta(days=35))
        self.env['pharma.transport.contract']._cron_contract_validity()
        self.assertFalse(contract.active)
        renewal = self.env['pharma.transport.contract'].browse(contract.action_renew()['res_id'])
        self.assertEqual(renewal.date_start, today)
        self.assertTrue(renewal.active)
        self.assertEqual(contract.renewal_id, renewal)

    def test_draft_contract_cannot_be_renewed(self):
        other = self.env['res.partner'].create({'name': 'Draft Co'})
        with self.assertRaises(UserError):
            self._draft_contract(other).action_renew()

    def test_terminate_wizard(self):
        wizard = self.env['pharma.transport.contract.terminate'].create({
            'contract_ids': [(6, 0, self.contract.ids)], 'reason': 'Repeated excursions'})
        wizard.action_confirm()
        self.assertEqual(self.contract.state, 'terminated')
        self.assertEqual(self.contract.termination_reason, 'Repeated excursions')

    # Crew qualification ------------------------------------------------------

    def _ready_shipment(self, **vals):
        shipment = self._draft_shipment(**vals)
        self._pass_checklist(shipment)
        return shipment

    def test_unqualified_driver_blocks_dispatch(self):
        newcomer = self.env['res.partner'].create(
            {'name': 'New Driver', 'parent_id': self.transporter.id, 'transport_role': 'driver'})
        self.assertEqual(newcomer.transport_qualification_state, 'not_qualified')
        shipment = self._ready_shipment(driver_ids=[(6, 0, newcomer.ids)])
        self.assertIn('New Driver', shipment.crew_issues)
        with self.assertRaisesRegex(UserError, 'not qualified'):
            shipment.action_dispatch()
        self._qualify(newcomer)
        self.assertEqual(newcomer.transport_qualification_state, 'qualified')
        shipment.action_dispatch()
        self.assertEqual(shipment.state, 'dispatched')

    def test_escort_alone_cannot_drive(self):
        shipment = self._ready_shipment(driver_ids=[(6, 0, self.driver_2.ids)])
        with self.assertRaisesRegex(UserError, 'No qualified driver'):
            shipment.action_dispatch()

    def test_licence_must_last_until_delivery(self):
        self.driver_1.driving_licence_valid_until = '2098-06-30'
        shipment = self._ready_shipment(driver_ids=[(6, 0, self.driver_1.ids)],
                                        expected_delivery_date='2099-01-01 10:00:00')
        with self.assertRaisesRegex(UserError, 'driving licence'):
            shipment.action_dispatch()

    def test_cold_chain_needs_trained_crew(self):
        self.driver_1.cold_chain_trained = False
        shipment = self._ready_shipment(driver_ids=[(6, 0, self.driver_1.ids)],
                                        temperature_controlled=True, temp_min=2.0, temp_max=8.0)
        with self.assertRaisesRegex(UserError, 'cold-chain trained'):
            shipment.action_dispatch()

    def test_high_security_needs_background_check(self):
        self.contract.service_high_security = True
        self.driver_1.background_check_valid_until = False
        shipment = self._ready_shipment(driver_ids=[(6, 0, self.driver_1.ids)])
        shipment.high_security = True
        with self.assertRaisesRegex(UserError, 'background check'):
            shipment.action_dispatch()
        shipment.high_security = False
        shipment.action_dispatch()

    def test_driver_of_another_transporter_rejected(self):
        other = self.env['res.partner'].create({'name': 'Other Haulier'})
        outsider = self._qualify(self.env['res.partner'].create(
            {'name': 'Outsider', 'parent_id': other.id}))
        shipment = self._ready_shipment(driver_ids=[(6, 0, outsider.ids)])
        with self.assertRaisesRegex(UserError, 'does not belong'):
            shipment.action_dispatch()

    def test_crew_expiry_reminder(self):
        soon = fields.Date.today() + timedelta(days=10)
        self.driver_1.driving_licence_valid_until = soon
        self.assertEqual(self.driver_1.transport_qualification_state, 'expiring')
        self.env['pharma.transport.contract']._cron_contract_validity()
        reminders = self.driver_1.activity_ids.filtered(
            lambda a: a.summary == 'Driver qualification expiring')
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders.date_deadline, soon)
        self.env['pharma.transport.contract']._cron_contract_validity()
        self.assertEqual(len(self.driver_1.activity_ids.filtered(
            lambda a: a.summary == 'Driver qualification expiring')), 1)
