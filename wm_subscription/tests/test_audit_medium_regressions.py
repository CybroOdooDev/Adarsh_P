"""Regression tests for the subscription audit findings: a contract holds one
live subscription, plan edits do not rewrite running terms, and the free-swap
allowance is not over-granted."""
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionAuditMediumRegressions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Audit Sub Customer'})
        cls.sla = cls.env['wm.sla'].create({'name': 'Audit Sub SLA', 'terms_and_conditions': 'Terms'})
        cls.plan = cls.env['wm.subscription.plan'].create({
            'name': 'Audit Plan', 'code': 'AUD_PLAN', 'recurring_price': 100.0,
            'billing_cycle': 'monthly', 'included_monthly_weight_kg': 300.0,
            'free_container_swaps_per_year': 1,
        })

    def _contract(self, name):
        return self.env['wm.partner.contract'].create({
            'name': name, 'partner_id': self.partner.id, 'sla_id': self.sla.id,
            'from_date': date(2026, 1, 1), 'to_date': date(2028, 12, 31),
            'frequency': 'monthly', 'no_of_frequency': 1,
            'billing_basis': 'per_collection', 'fixed_price': 100.0,
            'max_weight': 500.0, 'overweight_price': 10.0, 'state': 'signed',
        })

    def _sub(self, contract):
        sub = self.env['wm.subscription'].create({
            'partner_id': self.partner.id, 'contract_id': contract.id,
            'plan_id': self.plan.id, 'date_start': date(2026, 1, 1)})
        sub.action_activate()
        return sub

    def test_one_live_subscription_per_contract(self):
        contract = self._contract('AUD-C1')
        self._sub(contract)
        with self.assertRaises(ValidationError):
            self._sub(contract)

    def test_plan_cycle_edit_keeps_running_subscription_term(self):
        sub = self._sub(self._contract('AUD-C2'))
        end_before = sub.date_end
        self.plan.write({'billing_cycle': 'annually'})
        sub.invalidate_recordset()
        self.assertEqual(sub.date_end, end_before)
        self.assertEqual(sub.state, 'active')

    def test_pending_free_swap_counts_against_allowance(self):
        sub = self._sub(self._contract('AUD-C3'))
        Request = self.env['wm.portal.service.request']
        point = self.env['wm.collection.point'].create({'name': 'Swap Site', 'partner_id': self.partner.id})
        first = Request.create({'partner_id': self.partner.id, 'request_type': 'container_swap',
                                'collection_point_id': point.id, 'requested_date': date.today()})
        self.assertTrue(first.is_free_swap, "first swap is covered by the plan")
        first.state = 'submitted'
        second = Request.create({'partner_id': self.partner.id, 'request_type': 'container_swap',
                                 'collection_point_id': point.id, 'requested_date': date.today()})
        self.assertFalse(second.is_free_swap, "the single free swap is already taken")
        self.assertEqual(sub.free_container_swaps_per_year, 1)

    def test_cancel_preserves_past_cycle_draft_invoices(self):
        """H1: action_cancel() cancels future cycle draft invoices but preserves past ones for accounting review."""
        contract = self._contract('AUD-C4')
        sub = self._sub(contract)
        past_inv = self.env['account.move'].create({
            'partner_id': self.partner.id,
            'move_type': 'out_invoice',
            'subscription_id': sub.id,
            'invoice_date': date(2020, 1, 1),
            'state': 'draft',
        })
        future_inv = self.env['account.move'].create({
            'partner_id': self.partner.id,
            'move_type': 'out_invoice',
            'subscription_id': sub.id,
            'invoice_date': date(2099, 1, 1),
            'state': 'draft',
        })
        sub.action_cancel(reason="Customer requested cancellation")
        self.assertEqual(sub.state, 'cancelled')
        self.assertEqual(future_inv.state, 'cancel', "Future draft invoice must be auto-cancelled")
        self.assertEqual(past_inv.state, 'draft', "Past cycle draft invoice must be preserved for review")
