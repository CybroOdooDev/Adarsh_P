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
from datetime import datetime, time, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'wm_collection')
class TestAuditRegressions(TransactionCase):
    """Regression tests for defects confirmed by the 2026-10 ERP audit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_bool('wm_collection.use_batch_approval', False)
        cls.env['ir.config_parameter'].sudo().set_bool('wm_collection.use_batch_inspection', False)
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.src_location = cls.warehouse.lot_stock_id
        cls.dest_location = cls.env['stock.location'].create({
            'name': 'Audit Sorted Yard', 'usage': 'internal',
            'location_id': cls.src_location.location_id.id,
        })
        cls.category = cls.env['wm.waste.category'].create({'name': 'Audit Mixed', 'code': 'AUD-MIX'})
        cls.partner = cls.env['res.partner'].create({'name': 'Audit Customer'})
        cls.point = cls.env['wm.collection.point'].create({'name': 'Audit Site', 'partner_id': cls.partner.id})
        cls.dispatcher = new_test_user(cls.env, login='wm_audit_dispatcher', groups='wm_base.group_wm_dispatcher')

    def _sla(self):
        count = self.env['wm.sla'].search_count([('name', '=like', 'Audit SLA%')])
        return self.env['wm.sla'].create({'name': 'Audit SLA %d' % count, 'terms_and_conditions': 'Terms'})

    def _qty_at(self, product, location):
        return sum(self.env['stock.quant'].search([
            ('product_id', '=', product.id), ('location_id', '=', location.id)]).mapped('quantity'))

    # AUD-001: sorting a batch whose line has no UoM moved 1000x the stock
    def test_sort_line_without_uom_moves_quantity_in_product_uom(self):
        """A batch line without its own UoM is received in the product UoM, so
        sorting it must move the same quantity in the same UoM (it used to
        fall back to the batch's kg UoM and move 100 kg of a Units product,
        i.e. 100,000 Units)."""
        product = self.env['product.template'].create({
            'name': 'Audit Material', 'is_waste_material': True,
            'wm_waste_category_id': self.category.id,
        }).product_variant_id
        product.is_storable = True
        self.assertEqual(product.uom_id, self.env.ref('uom.product_uom_unit'))
        batch = self.env['waste.batch'].create({
            'warehouse_id': self.warehouse.id,
            'location_id': self.src_location.id,
            'category_id': self.category.id,
            'line_ids': [(0, 0, {'product_id': product.id, 'quantity': 100.0})],
        })
        batch.with_context(skip_inspection_check=True).action_receive_batch()
        batch.with_context(skip_inspection_check=True).action_move_to_stock()
        self.assertAlmostEqual(self._qty_at(product, self.src_location), 100.0)

        self.env['waste.batch.sort.wizard'].create({
            'batch_id': batch.id,
            'output_batch_mode': 'per_material',
            'line_ids': [(0, 0, {
                'batch_line_id': batch.line_ids.id,
                'sort_qty': 100.0,
                'dest_product_id': product.id,
                'dest_location_id': self.dest_location.id,
            })],
        }).action_confirm_sort()

        self.assertAlmostEqual(self._qty_at(product, self.src_location), 0.0,
                               msg="Sorting must not leave a negative quant at the source")
        self.assertAlmostEqual(self._qty_at(product, self.dest_location), 100.0,
                               msg="Sorted stock must equal the sorted quantity")
        child = batch.sorted_batch_ids
        self.assertEqual(child.line_ids.uom_id, product.uom_id)
        self.assertAlmostEqual(child.draft_quantity, 100.0,
                               msg="The child batch shows the same quantity as its parent line")

    # AUD-002: a client-supplied context key unlocked completed orders
    def test_rpc_context_flag_does_not_unlock_completed_order(self):
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 50.0})],
        })
        order.sudo().with_context(programmatic_state_change=True).write({'state': 'completed'})
        self.assertEqual(order.state, 'completed')

        as_dispatcher = order.with_user(self.dispatcher).with_context(programmatic_state_change=True)
        with self.assertRaises(UserError):
            as_dispatcher.write({'estimated_weight': 1.0})
        with self.assertRaises(UserError):
            as_dispatcher.order_line_ids.write({'weight': 5000.0})
        as_dispatcher.write({'state': 'draft'})
        self.assertEqual(order.state, 'completed', "A user cannot change the state with the context key")
        self.assertAlmostEqual(order.order_line_ids.weight, 50.0)

    def test_internal_transition_still_checks_record_access(self):
        """Internal transitions write as superuser, but only after checking
        that the caller may write the order."""
        driver = new_test_user(self.env, login='wm_audit_driver', groups='wm_base.group_wm_driver')
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 10.0})],
        })
        with self.assertRaises(AccessError):
            order.with_user(driver).action_cancel()
        self.assertNotEqual(order.state, 'cancelled')

    # AUD-003: schedule cron created orders in the cron user's company
    def test_schedule_orders_belong_to_route_company(self):
        company_b = self.env['res.company'].create({'name': 'Audit Company B'})
        point_b = self.env['wm.collection.point'].create({
            'name': 'Audit Site B', 'partner_id': self.partner.id, 'company_id': company_b.id,
        }) if 'company_id' in self.env['wm.collection.point']._fields else self.point
        today = fields.Date.context_today(self.env.user)
        template = self.env['wm.route'].with_company(company_b).create({
            'date': today - timedelta(days=7),
            'company_id': company_b.id,
            'line_ids': [(0, 0, {'collection_point_id': point_b.id, 'sequence': 10})],
        })
        self.env['wm.schedule'].create({
            'name': 'Audit B Weekly', 'route_id': template.id, 'recurrence': 'weekly',
            'next_run_date': fields.Datetime.now() - timedelta(minutes=5),
        })
        self.assertNotEqual(self.env.company, company_b)
        self.env['wm.schedule']._process_schedules()
        orders = self.env['wm.collection.order'].search([('collection_point_id', '=', point_b.id)])
        self.assertTrue(orders)
        self.assertEqual(orders.mapped('company_id'), company_b)
        self.assertEqual(orders.route_id.company_id, company_b)

    # AUD-004: negative gross weight accepted on batch
    def test_negative_gross_weight_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['waste.batch'].create({
                'warehouse_id': self.warehouse.id,
                'location_id': self.src_location.id,
                'category_id': self.category.id,
                'gross_weight': -10.0,
                'tare_weight': 0.0,
            })

    # Phase 2: Historical driver preserved on completed orders
    def test_historical_driver_preserved_on_completed_order(self):
        driver_a = new_test_user(self.env, login='audit_driver_a', groups='wm_base.group_wm_driver')
        driver_b = new_test_user(self.env, login='audit_driver_b', groups='wm_base.group_wm_driver')
        route = self.env['wm.route'].create({
            'name': 'Audit Route Driver History',
            'driver_id': driver_a.partner_id.id,
            'line_ids': [(0, 0, {'collection_point_id': self.point.id})],
        })
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'route_id': route.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 10.0})],
        })
        self.assertEqual(order.driver_id, driver_a.partner_id)
        order.sudo().with_context(programmatic_state_change=True).write({'state': 'completed'})
        self.assertEqual(order.state, 'completed')
        # Route driver reassigned to driver_b
        route.driver_id = driver_b.partner_id
        order._compute_driver_id()
        self.assertEqual(order.driver_id, driver_a.partner_id, "Completed order must retain historical driver")

    # Phase 2: Removing route stop detaches orders instead of deleting them
    def test_remove_stop_from_route_preserves_customer_orders(self):
        route = self.env['wm.route'].create({
            'name': 'Audit Route Stop Remove',
            'line_ids': [(0, 0, {'collection_point_id': self.point.id})],
        })
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'route_id': route.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 20.0})],
        })
        route.action_remove_collection_point(self.point.id)
        self.assertTrue(order.exists(), "Customer order must not be deleted when stop is removed")
        self.assertFalse(order.route_id, "Order should be unassigned from route")

    # Phase 2: Adding a stop does not steal orders already assigned to another route
    def test_add_stop_does_not_steal_orders_assigned_to_other_route(self):
        route_1 = self.env['wm.route'].create({'name': 'Route 1'})
        route_2 = self.env['wm.route'].create({'name': 'Route 2'})
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'route_id': route_1.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 15.0})],
        })
        route_2.action_add_collection_point(self.point.id, optimize=False)
        self.assertEqual(order.route_id, route_1, "Order already on Route 1 must not be stolen by Route 2")

    # Phase 2: Route completion does not duplicate batches for orders already batched
    def test_route_completion_skips_orders_already_batched(self):
        route = self.env['wm.route'].create({
            'name': 'Audit Route Batch Dedup',
            'line_ids': [(0, 0, {'collection_point_id': self.point.id})],
        })
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'route_id': route.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 30.0})],
        })
        # Simulate an intake batch already created (e.g. from weighbridge gate entry)
        gate_batch = self.env['waste.batch'].create({
            'name': 'INTAKE/GE-AUDIT',
            'category_id': self.category.id,
            'collection_order_id': order.id,
            'gross_weight': 30.0,
            'draft_quantity': 30.0,
            'warehouse_id': self.warehouse.id,
            'location_id': self.src_location.id,
        })
        order.sudo().with_context(programmatic_state_change=True).write({'state': 'completed'})
        self.assertEqual(order.state, 'completed')
        batches_before = self.env['waste.batch'].search_count([])
        created = route.action_create_route_category_batches()
        # Since the only order on the route was already batched, no additional route batch should be created
        self.assertFalse(created, "Orders already batched must not create duplicate intake batches on route completion")
        self.assertEqual(self.env['waste.batch'].search_count([]), batches_before)
        self.assertTrue(gate_batch.exists())

    # Phase 4 (H2): Volume (per_m3) billing calculation uses container capacity
    def test_per_m3_volume_pricing_calculation(self):
        ctype = self.env['wm.container.type'].create({
            'name': 'Audit 2000L Bin', 'capacity_volume': 2000.0,
        })
        self.env['wm.category.billing.rule'].create({
            'category_id': self.category.id,
            'billing_basis': 'per_m3',
            'price': 45.0,
        })
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'container_id': ctype.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 500.0})],
        })
        line = order.order_line_ids[0]
        self.assertEqual(line.price_basis, 'per_m3')
        # 2000 L = 2.0 m³ * 45.0/m³ = 90.0 (the 500 kg plays no part)
        self.assertAlmostEqual(line.total_amount, 90.0)
        self.assertAlmostEqual(self.env['wm.collection.order']._get_billable_volume_m3(order), 2.0)

    def test_per_m3_without_container_volume_is_refused(self):
        """Without a container volume the order cannot be billed per m3: its kg
        must never be billed as m3."""
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 500.0})],
        })
        with self.assertRaises(UserError):
            self.env['wm.collection.order']._get_billable_volume_m3(order)

    # Phase 4 (H3): Overweight double billing prevented when contract already bills overweight
    def test_overweight_double_billing_prevented(self):
        if 'wm.billable.event' not in self.env or 'wm.partner.contract' not in self.env:
            return
        ctype = self.env['wm.container.type'].create({
            'name': 'Audit 200kg Bin', 'capacity_weight': 200.0,
        })

        def overweight_events(basis, **vals):
            # One active contract per customer: each case gets its own customer.
            partner = self.env['res.partner'].create({'name': 'Audit Overweight %s' % basis})
            point = self.env['wm.collection.point'].create({'name': 'Audit OW %s' % basis, 'partner_id': partner.id})
            contract = self.env['wm.partner.contract'].create(dict({
                'name': 'Contract %s' % basis,
                'partner_id': partner.id,
                'sla_id': self._sla().id,
                'from_date': fields.Date.today() - timedelta(days=30),
                'to_date': fields.Date.today() + timedelta(days=30),
                'frequency': 'weekly', 'no_of_frequency': 1,
                'billing_basis': basis,
                'overweight_price': 15.0,
                'state': 'ongoing',
            }, **vals))
            order = self.env['wm.collection.order'].create({
                'partner_id': partner.id,
                'collection_point_id': point.id,
                'contract_id': contract.id,
                'container_id': ctype.id,
                'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 350.0})],
            })
            self.assertAlmostEqual(order.confirmed_weight, 350.0)
            order._log_overweight_event()
            return self.env['wm.billable.event'].search_count([
                ('collection_order_id', '=', order.id), ('event_type', '=', 'overweight')])

        # The per-collection fee already charges the overweight surcharge
        self.assertEqual(overweight_events('per_collection', fixed_price=100.0, max_weight=200.0), 0)
        # A category-rate contract never applies overweight_price: the event is still raised
        self.assertEqual(overweight_events('category_rate', contract_line_ids=[
            (0, 0, {'category_id': self.category.id, 'price': 0.12})]), 1)

    # Phase 4 (H4): Contract cancellation retains pricing for orders performed before cancellation
    def test_contract_cancellation_retains_historical_pricing(self):
        if 'wm.partner.contract' not in self.env:
            return
        past_date = fields.Date.today() - timedelta(days=10)
        partner = self.env['res.partner'].create({'name': 'Audit Historic Customer'})
        point = self.env['wm.collection.point'].create({'name': 'Audit Historic Site', 'partner_id': partner.id})
        contract = self.env['wm.partner.contract'].create({
            'name': 'Historic Contract',
            'partner_id': partner.id,
            'sla_id': self._sla().id,
            'from_date': past_date - timedelta(days=30),
            'to_date': past_date + timedelta(days=60),
            'frequency': 'weekly', 'no_of_frequency': 1,
            'billing_basis': 'per_collection',
            'fixed_price': 75.0,
            'max_weight': 500.0,
            'overweight_price': 5.0,
            'state': 'ongoing',
        })

        def order_on(day):
            start = datetime.combine(day, time(10, 0))
            return self.env['wm.collection.order'].create({
                'partner_id': partner.id,
                'collection_point_id': point.id,
                'contract_id': contract.id,
                'scheduled_start': start,
                'scheduled_end': start + timedelta(hours=1),
                'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 50.0})],
            })
        order = order_on(past_date)
        later = order_on(fields.Date.today() + timedelta(days=5))
        # Now cancel the contract
        contract.action_cancel()
        self.assertEqual(contract.state, 'cancelled')
        self.assertTrue(contract.cancel_date)
        # Service date was past_date <= cancel_date; pricing rule should still come from contract
        rule = order.order_line_ids[0]._get_billing_rule()
        self.assertTrue(rule and getattr(rule, 'from_contract', False), "Order performed before contract cancellation must retain contract terms")
        self.assertEqual(rule.price, 75.0)
        later_rule = later.order_line_ids[0]._get_billing_rule()
        self.assertFalse(later_rule and getattr(later_rule, 'from_contract', False),
                         "An order after the cancellation date is not priced by the cancelled contract")

    # Route start gate: a dispatched route whose vehicle is not (or no longer)
    # inspected cannot start; a passed inspection recorded on the route counts.
    def _vehicle(self, plate):
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Audit Brand %s' % plate})
        model = self.env['fleet.vehicle.model'].create({'name': 'Audit Model', 'brand_id': brand.id})
        return self.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': plate})

    def test_uninspected_route_cannot_start(self):
        route = self.env['wm.route'].create({'date': fields.Date.today(), 'vehicle_id': self._vehicle('AUD-ST1').id})
        route.sudo().with_context(programmatic_state_change=True).write({'state': 'dispatched'})
        route.invalidate_recordset(['is_inspected'])
        self.assertFalse(route.is_inspected)
        with self.assertRaises(ValidationError):
            route.action_start_route()
        self.assertEqual(route.state, 'dispatched')

    def test_passed_route_inspection_without_vehicle_counts(self):
        route = self.env['wm.route'].create({'date': fields.Date.today(), 'vehicle_id': self._vehicle('AUD-ST2').id})
        survey = self.env['survey.survey'].create({
            'title': 'Audit Pre-Trip', 'scoring_type': 'no_scoring', 'scoring_success_min': 0.0})
        self.env['survey.user_input'].create({
            'survey_id': survey.id, 'route_id': route.id, 'checklist_type': 'pre_trip', 'state': 'done'})
        route.invalidate_recordset(['is_inspected', 'inspection_ids'])
        self.assertTrue(route.is_inspected)
        route.sudo().with_context(programmatic_state_change=True).write({'state': 'dispatched'})
        route.action_start_route()
        self.assertEqual(route.state, 'running')
