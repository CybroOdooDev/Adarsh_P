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
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'wm_contracts_billing')
class TestAuditBillingRegressions(TransactionCase):
    """Regression tests for billing defects confirmed by the 2026-10 ERP audit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Audit Billing Customer'})
        cls.point = cls.env['wm.collection.point'].create({'name': 'Audit Billing Site', 'partner_id': cls.partner.id})
        cls.category = cls.env['wm.waste.category'].create({'name': 'Audit Billing Cat', 'code': 'AUD-BIL'})

    def _contract(self, name, price):
        today = fields.Date.today()
        return self.env['wm.partner.contract'].create({
            'name': name,
            'partner_id': self.partner.id,
            'sla_id': self.env['wm.sla'].create({'name': name + ' SLA', 'terms_and_conditions': 'Terms'}).id,
            'from_date': today, 'to_date': today + timedelta(days=365),
            'frequency': 'weekly', 'no_of_frequency': 1,
            'billing_basis': 'category_rate', 'state': 'confirmed',
            'contract_line_ids': [(0, 0, {'category_id': self.category.id, 'price': price})],
        })

    def _foreign_currency(self, rate):
        currency = self.env['res.currency'].with_context(active_test=False).search(
            [('id', '!=', self.company.currency_id.id), ('decimal_places', '=', 2)], limit=1)
        currency.active = True
        self.env['res.currency.rate'].search([('currency_id', '=', currency.id)]).unlink()
        self.env['res.currency.rate'].create({
            'currency_id': currency.id, 'company_id': self.company.id,
            'name': fields.Date.today(), 'rate': rate,
        })
        return currency

    # AUD-010: the conversion factor was rounded to the invoice currency (0.01198 -> 0.01)
    def test_invoice_currency_factor_is_not_rounded(self):
        currency = self._foreign_currency(0.01198)
        factor = self.env['wm.collection.order']._get_invoice_currency_factor(
            currency, self.company, fields.Date.today())
        self.assertAlmostEqual(factor, 0.01198, places=6)
        # 7,600 kg at 10/kg in company currency = 76,000 -> 910.48 in the invoice currency
        self.assertAlmostEqual(currency.round(76000.0 * factor), 910.48, places=2)

    # AUD-011: a released (cancelled) invoice could be reset to draft and reposted
    def _invoice(self):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {'name': 'Collection', 'quantity': 1.0, 'price_unit': 912.0})],
        })

    def test_cancelled_invoice_that_released_orders_cannot_be_reset(self):
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 7600.0})],
        })
        invoice = self._invoice()
        order.sudo().direct_invoice_id = invoice
        invoice.button_cancel()
        self.assertEqual(invoice.state, 'cancel')
        self.assertFalse(order.direct_invoice_id, "Cancelling releases the order for re-billing")
        with self.assertRaises(UserError):
            invoice.button_draft()
        self.assertEqual(invoice.state, 'cancel')

    def test_unrelated_cancelled_invoice_can_still_be_reset(self):
        invoice = self._invoice()
        invoice.button_cancel()
        invoice.button_draft()
        self.assertEqual(invoice.state, 'draft')

    # AUD-012: service requests had no company restriction
    def test_service_request_is_company_scoped(self):
        company_b = self.env['res.company'].create({'name': 'Audit Billing Company B'})
        manager = new_test_user(self.env, login='wm_audit_contract_mgr',
                                groups='wm_contracts_billing.group_wm_contract_manager',
                                company_id=self.company.id, company_ids=[(6, 0, self.company.ids)])
        request_b = self.env['wm.portal.service.request'].with_company(company_b).create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'request_type': 'container_swap',
            'requested_date': fields.Date.today(),
            'company_id': company_b.id,
        })
        self.assertEqual(request_b.company_id, company_b)
        visible = self.env['wm.portal.service.request'].with_user(manager).search([('id', '=', request_b.id)])
        self.assertFalse(visible, "A user of company A must not see company B's service requests")

    # Phase 3: Per-kg rate precision preserves 4+ decimal places
    def test_per_kg_rate_precision_preserves_decimals(self):
        rule = self.env['wm.pricing.rule'].create({
            'name': 'Audit Fine Pricing Rule',
            'waste_category_id': self.category.id,
            'price_per_kg': 0.0875,
        })
        self.assertAlmostEqual(rule.price_per_kg, 0.0875, places=4)

        contract = self._contract('Fine Rate Contract', 0.0875)
        line = contract.contract_line_ids[0]
        self.assertAlmostEqual(line.price, 0.0875, places=4, msg="Per-kg rate must not round to 2 decimals")
        billing_rule = self.env['wm.category.billing.rule'].create({
            'category_id': self.category.id, 'billing_basis': 'per_kg', 'price': 0.0875})
        self.assertAlmostEqual(billing_rule.price, 0.0875, places=4)
        self.assertEqual(self.env['decimal.precision'].precision_get('WM Rate'), 4)

    # Phase 3: Contract lines cannot be modified once contract is confirmed
    def test_contract_line_price_cannot_be_changed_after_confirmation(self):
        contract = self._contract('Lock Contract', 1.50)
        manager = new_test_user(self.env, login='wm_audit_lock_mgr',
                                groups='wm_contracts_billing.group_wm_contract_manager')
        as_manager = contract.with_user(manager)
        other_category = self.env['wm.waste.category'].create({'name': 'Audit Lock Cat 2', 'code': 'AUD-LK2'})
        with self.assertRaises(UserError):
            as_manager.contract_line_ids[0].write({'price': 2.50})
        with self.assertRaises(UserError):
            self.env['wm.partner.contract.line'].with_user(manager).create({
                'contract_id': contract.id, 'category_id': other_category.id, 'price': 0.01})
        with self.assertRaises(UserError):
            as_manager.contract_line_ids[0].unlink()
        # The override context is honoured only under sudo(), never from an RPC client
        with self.assertRaises(UserError):
            as_manager.contract_line_ids[0].with_context(wm_contract_price_override=True).write({'price': 2.50})
        self.assertAlmostEqual(contract.contract_line_ids.price, 1.50)

    # Phase 3: Cancelling collection order cancels linked billable events
    def test_cancelled_collection_order_cancels_billable_event(self):
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 50.0})],
        })
        event = self.env['wm.billable.event'].create({
            'partner_id': self.partner.id,
            'event_type': 'extra_pickup',
            'collection_order_id': order.id,
            'price_unit': 45.0,
            'state': 'confirmed',
        })
        self.assertEqual(event.state, 'confirmed')
        order.action_cancel()
        self.assertEqual(event.state, 'cancelled', "Cancelling collection order must cancel linked billable event")

    # Phase 3: Billable event invoice carries service product and taxes
    def test_billable_event_invoice_carries_product_and_taxes(self):
        tax = self.env['account.tax'].create({
            'name': 'Audit Waste Tax 10%',
            'amount_type': 'percent',
            'amount': 10.0,
            'company_id': self.company.id,
        })
        # Named after the event type, so it is the product the event is invoiced on
        service_prod = self.env['product.product'].create({
            'name': 'Extra Pickup Surcharge Service',
            'type': 'service',
            'taxes_id': [(6, 0, tax.ids)],
        })
        event = self.env['wm.billable.event'].create({
            'partner_id': self.partner.id,
            'event_type': 'extra_pickup',
            'price_unit': 100.0,
            'quantity': 1.0,
            'state': 'confirmed',
        })
        action = event.action_create_invoice()
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        line = invoice.invoice_line_ids[0]
        self.assertEqual(line.product_id, service_prod, "The event is invoiced on its service product")
        self.assertIn(tax, line.tax_ids, "Invoice line must have taxes from the service product")
        self.assertAlmostEqual(invoice.amount_untaxed, 100.0)
        self.assertAlmostEqual(invoice.amount_tax, 10.0)


@tagged('post_install', '-at_install', 'wm_contracts_billing')
class TestAuditWeightBillingCalculation(TransactionCase):
    """Independent check of weight-based billing: 7.6 t at 120 per tonne = 912."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.category = cls.env['wm.waste.category'].create({'name': 'Audit Weight Cat', 'code': 'AUD-WGT'})
        cls.sla = cls.env['wm.sla'].create({'name': 'Audit Weight SLA', 'terms_and_conditions': 'Terms'})
        cls.today = today

    def _setup(self, name, billing_mode):
        from datetime import datetime, time, timedelta
        from dateutil.relativedelta import relativedelta
        partner = self.env['res.partner'].create({'name': name, 'billing_mode': billing_mode})
        point = self.env['wm.collection.point'].create({'name': name + ' Site', 'partner_id': partner.id})
        contract = self.env['wm.partner.contract'].create({
            'name': name + ' Contract', 'partner_id': partner.id, 'sla_id': self.sla.id,
            'from_date': self.today - relativedelta(months=1), 'to_date': self.today + relativedelta(years=1),
            'frequency': 'weekly', 'no_of_frequency': 1, 'billing_basis': 'category_rate', 'state': 'ongoing',
            # 120 per tonne = 0.12 per kg
            'contract_line_ids': [(0, 0, {'category_id': self.category.id, 'price': 0.12})],
        })
        start = datetime.combine(self.today, time(0, 30))
        order = self.env['wm.collection.order'].create({
            'partner_id': partner.id, 'collection_point_id': point.id, 'contract_id': contract.id,
            'scheduled_start': start, 'scheduled_end': start + timedelta(hours=1),
            'actual_start': start, 'actual_end': start + timedelta(hours=1), 'state': 'completed',
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': 7600.0})],
        })
        return partner, order

    def test_direct_invoice_is_912(self):
        _partner, order = self._setup('Audit Direct 912', 'consolidated')
        self.assertAlmostEqual(order.total_amount, 912.0)
        order.action_create_invoice()
        self.assertAlmostEqual(order.direct_invoice_id.amount_untaxed, 912.0)

    def test_monthly_run_invoice_is_912_and_not_duplicated(self):
        partner, _order = self._setup('Audit Run 912', 'monthly_run')
        run = self.env['wm.monthly.billing.run'].create({
            'period_start': self.today.replace(day=1), 'period_end': self.today})
        run.action_run_billing(partner_ids=partner.ids)
        invoice = run.invoice_ids.filtered(lambda inv: inv.partner_id == partner)
        self.assertEqual(len(invoice), 1)
        self.assertAlmostEqual(invoice.amount_untaxed, 912.0)
        rerun = self.env['wm.monthly.billing.run'].create({
            'period_start': self.today.replace(day=1), 'period_end': self.today})
        rerun.action_run_billing(partner_ids=partner.ids)
        self.assertFalse(rerun.invoice_ids.filtered(lambda inv: inv.partner_id == partner),
                         "A second run must not bill the same order again")
