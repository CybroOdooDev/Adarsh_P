"""Coverage tests: plan constraints and propagation, subscription constraints,
pause/resume/cancel workflow, cron expiry, quota/swap computes and pricing."""
from datetime import date

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionCoverage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Coverage Sub Customer'})
        cls.sla = cls.env['wm.sla'].create({'name': 'Coverage SLA', 'terms_and_conditions': 'Terms'})
        cls.plan = cls.env['wm.subscription.plan'].create({
            'name': 'Coverage Plan', 'code': 'COV_PLAN', 'recurring_price': 100.0,
            'billing_cycle': 'monthly', 'included_monthly_weight_kg': 300.0,
            'extra_pickup_discount': 10.0, 'free_container_swaps_per_year': 1,
        })
        cls.driver = new_test_user(cls.env, login='wm_cov_sub_driver', groups='wm_base.group_wm_driver')

    def _contract(self, name='COV-C', state='signed', partner=None):
        return self.env['wm.partner.contract'].create({
            'name': name, 'partner_id': (partner or self.partner).id, 'sla_id': self.sla.id,
            'from_date': date(2026, 1, 1), 'to_date': date(2028, 12, 31),
            'frequency': 'monthly', 'no_of_frequency': 1,
            'billing_basis': 'per_collection', 'fixed_price': 100.0,
            'max_weight': 500.0, 'overweight_price': 10.0, 'state': state,
        })

    def _sub(self, contract=None, **vals):
        return self.env['wm.subscription'].create(dict({
            'partner_id': self.partner.id,
            'contract_id': (contract or self._contract()).id,
            'plan_id': self.plan.id,
            'date_start': date(2026, 1, 1),
        }, **vals))

    # ── Plan ────────────────────────────────────────────────────────────────
    def test_plan_value_constraints(self):
        for field, value in (('recurring_price', -1.0), ('extra_pickup_discount', 101.0),
                             ('extra_pickup_discount', -1.0), ('included_monthly_weight_kg', -5.0),
                             ('free_container_swaps_per_year', -1)):
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                self.plan.copy({'code': 'COV_BAD_%s_%s' % (field[:5], value)}).write({field: value})

    def test_plan_code_unique(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['wm.subscription.plan'].create({
                'name': 'Dup', 'code': 'COV_PLAN', 'recurring_price': 1.0})

    def test_plan_write_propagates_to_draft_only(self):
        draft = self._sub(self._contract('COV-D'))
        active = self._sub(self._contract('COV-A'))
        active.action_activate()
        self.plan.write({'recurring_price': 250.0, 'priority_sla_level': 'vip_same_day',
                         'free_container_swaps_per_year': 4})
        self.assertEqual(draft.recurring_price, 250.0)
        self.assertEqual(draft.priority_sla_level, 'vip_same_day')
        self.assertEqual(draft.free_container_swaps_per_year, 4)
        self.assertEqual(active.recurring_price, 100.0)
        self.assertEqual(active.priority_sla_level, 'standard')

    def test_create_copies_plan_defaults(self):
        sub = self._sub()
        self.assertEqual(sub.recurring_price, 100.0)
        self.assertEqual(sub.extra_pickup_discount, 10.0)
        self.assertEqual(sub.included_monthly_weight_kg, 300.0)
        self.assertEqual(sub.free_container_swaps_per_year, 1)
        self.assertNotEqual(sub.name, 'New')

    def test_onchange_plan_copies_benefits_in_draft_only(self):
        sub = self.env['wm.subscription'].new({
            'plan_id': self.plan.id, 'date_start': date(2026, 3, 1), 'state': 'draft'})
        sub._onchange_plan_id()
        self.assertEqual(sub.recurring_price, 100.0)
        self.assertEqual(sub.extra_pickup_discount, 10.0)
        self.assertEqual(sub.date_end, date(2026, 3, 31))
        active = self.env['wm.subscription'].new({
            'plan_id': self.plan.id, 'state': 'active', 'recurring_price': 5.0})
        active._onchange_plan_id()
        self.assertEqual(active.recurring_price, 5.0)

    # ── Constraints ─────────────────────────────────────────────────────────
    def test_contract_must_belong_to_customer(self):
        other = self.env['res.partner'].create({'name': 'Other Sub Customer'})
        with self.assertRaises(ValidationError):
            self._sub(self._contract('COV-OWN', partner=other))

    def test_end_date_before_start_rejected(self):
        sub = self._sub()
        with self.assertRaises(ValidationError):
            # the inverse would rewrite date_start: skip it to hit the constraint
            sub.with_context(wm_skip_date_end_inverse=True).write({'date_end': date(2025, 12, 1)})

    def test_pause_end_before_start_rejected(self):
        sub = self._sub()
        with self.assertRaises(ValidationError):
            sub.write({'pause_start_date': date(2026, 5, 1), 'pause_end_date': date(2026, 4, 1)})

    # ── Activation guards ───────────────────────────────────────────────────
    def test_activate_requires_valid_contract_state(self):
        sub = self._sub(self._contract('COV-DRAFT', state='draft'))
        with self.assertRaises(ValidationError):
            sub.action_activate()
        self.assertEqual(sub.state, 'draft')

    def test_activate_generates_invoice_and_dates(self):
        sub = self._sub()
        sub.action_activate()
        self.assertEqual(sub.state, 'active')
        self.assertEqual(sub.date_end, date(2026, 1, 31))
        self.assertEqual(sub.next_invoice_date, date(2026, 2, 1))
        self.assertEqual(len(sub.invoice_ids), 1)
        self.assertEqual(sub.invoice_count, 1)

    def test_activate_non_draft_refused(self):
        sub = self._sub()
        sub.action_activate()
        with self.assertRaises(UserError):
            sub.action_activate()

    # ── Pause / resume ──────────────────────────────────────────────────────
    @freeze_time('2026-01-15')
    def test_pause_and_resume_cycle(self):
        sub = self._sub()
        sub.action_activate()
        sub.action_pause(resume_date=date(2026, 3, 1))
        self.assertEqual(sub.state, 'paused')
        self.assertEqual(sub.pause_start_date, date(2026, 1, 15))
        self.assertEqual(sub.pause_end_date, date(2026, 3, 1))
        with self.assertRaises(UserError):
            sub.action_pause()
        sub.next_invoice_date = date(2026, 1, 20)
        sub.action_resume()
        self.assertEqual(sub.state, 'active')
        self.assertFalse(sub.pause_start_date)
        self.assertFalse(sub.pause_end_date)
        # a billing date still in the future is left untouched
        self.assertEqual(sub.next_invoice_date, date(2026, 1, 20))

    @freeze_time('2026-03-15')
    def test_resume_aligns_stale_next_invoice_date(self):
        sub = self._sub()
        sub.action_activate()
        sub.action_pause()
        sub.action_resume()
        self.assertEqual(sub.next_invoice_date, date(2026, 3, 15))

    def test_pause_and_resume_invalid_states(self):
        sub = self._sub()
        with self.assertRaises(UserError):
            sub.action_pause()
        with self.assertRaises(UserError):
            sub.action_resume()

    def test_single_live_constraint_on_resume_path(self):
        contract = self._contract('COV-LIVE')
        sub = self._sub(contract)
        sub.action_activate()
        sub.action_pause()
        with self.assertRaises(ValidationError):
            self._sub(contract).action_activate()

    # ── Cancel ──────────────────────────────────────────────────────────────
    def test_cancel_keeps_past_draft_invoices(self):
        # Cancelling only drops drafts of current/future cycles; a past cycle's
        # draft (here 2026-01-01) is earned revenue left for accounting review.
        sub = self._sub()
        sub.action_activate()
        invoices = sub.invoice_ids
        self.assertTrue(invoices)
        self.assertTrue(all(inv.invoice_date < fields.Date.today() for inv in invoices))
        sub.action_cancel(reason='Moved away')
        self.assertEqual(sub.state, 'cancelled')
        self.assertEqual(sub.cancel_reason, 'Moved away')
        self.assertEqual(set(invoices.mapped('state')), {'draft'})

    def test_cancel_draft_subscription_and_invalid_states(self):
        sub = self._sub()
        sub.action_cancel()
        self.assertEqual(sub.state, 'cancelled')
        self.assertTrue(sub.cancel_reason)
        with self.assertRaises(UserError):
            sub.action_cancel()

    def test_cancel_and_renew_denied_for_non_managers(self):
        sub = self._sub()
        with self.assertRaises(AccessError):
            sub.with_user(self.driver).action_cancel()
        self.assertEqual(sub.state, 'draft')

    # ── Cron ────────────────────────────────────────────────────────────────
    @freeze_time('2026-06-15')
    def test_cron_expires_non_renewing_subscription(self):
        sub = self._sub(auto_renew=False)
        sub.action_activate()
        self.assertEqual(sub.state, 'active')
        self.assertLess(sub.date_end, date(2026, 6, 15))
        self.env['wm.subscription']._cron_process_subscriptions()
        self.assertEqual(sub.state, 'expired')

    @freeze_time('2026-06-15')
    def test_cron_expires_when_contract_cancelled(self):
        contract = self._contract('COV-EXP')
        sub = self._sub(contract)
        sub.action_activate()
        contract.state = 'cancelled'
        self.env['wm.subscription']._cron_process_subscriptions()
        self.assertEqual(sub.state, 'expired')

    # ── Computes / actions ──────────────────────────────────────────────────
    def test_quota_compute_without_collections(self):
        sub = self._sub()
        self.assertEqual(sub.current_cycle_weight_kg, 0.0)
        self.assertEqual(sub.remaining_quota_kg, 300.0)
        self.assertFalse(sub.is_quota_exceeded)
        no_start = self._sub(self._contract('COV-NS'), date_start=False)
        self.assertEqual(no_start.remaining_quota_kg, 300.0)
        self.assertFalse(no_start.is_quota_exceeded)

    @freeze_time('2026-01-15')
    def test_used_free_swaps_count_and_helper(self):
        sub = self._sub()
        sub.action_activate()
        point = self.env['wm.collection.point'].create({'name': 'Cov Site', 'partner_id': self.partner.id})
        req = self.env['wm.portal.service.request'].create({
            'partner_id': self.partner.id, 'request_type': 'container_swap',
            'collection_point_id': point.id, 'requested_date': date(2026, 1, 15)})
        self.assertTrue(req.is_free_swap)
        self.assertEqual(req.final_estimated_price, 0.0)
        self.assertEqual(req.base_estimated_price, 75.0)
        req.state = 'submitted'
        self.assertEqual(sub._count_free_swaps(), 1)
        self.assertEqual(sub._count_free_swaps(exclude_request=req), 0)
        # pending requests are not "used" until approved
        sub.invalidate_recordset(['used_free_swaps_count'])
        self.assertEqual(sub.used_free_swaps_count, 0)
        req.state = 'approved'
        sub.invalidate_recordset(['used_free_swaps_count'])
        self.assertEqual(sub.used_free_swaps_count, 1)

    @freeze_time('2026-01-15')
    def test_service_request_pricing_with_and_without_subscription(self):
        point = self.env['wm.collection.point'].create({'name': 'Cov Site 2', 'partner_id': self.partner.id})
        vals = {'partner_id': self.partner.id, 'request_type': 'extra_pickup',
                'collection_point_id': point.id, 'requested_date': date(2026, 1, 15)}
        plain = self.env['wm.portal.service.request'].create(vals)
        self.assertFalse(plain.active_subscription_id)
        self.assertEqual(plain.subscriber_discount_pct, 0.0)
        self.assertEqual(plain.base_estimated_price, 50.0)
        self.assertEqual(plain.final_estimated_price, 50.0)
        self.assertEqual(plain.priority_sla_level, 'standard')
        self._sub().action_activate()
        disc = self.env['wm.portal.service.request'].create(vals)
        self.assertEqual(disc.subscriber_discount_pct, 10.0)
        self.assertAlmostEqual(disc.discount_amount, 5.0)
        self.assertAlmostEqual(disc.final_estimated_price, 45.0)

    def test_view_actions(self):
        contract = self._contract('COV-VIEW')
        sub = self._sub(contract)
        sub.action_activate()
        act = sub.action_view_invoices()
        self.assertEqual(act['res_id'], sub.invoice_ids.id)
        self.assertEqual(act['view_mode'], 'form')
        self.assertEqual(contract.subscription_count, 1)
        cact = contract.action_view_subscriptions()
        self.assertEqual(cact['res_id'], sub.id)
        self._sub(contract, state='cancelled')
        self.assertEqual(contract.action_view_subscriptions()['view_mode'], 'list,form')

    def test_generate_term_invoices_idempotent_and_zero_price(self):
        sub = self._sub()
        inv1, nxt = sub._generate_term_invoices(date(2026, 1, 1), date(2026, 3, 31))
        self.assertEqual(len(inv1), 3)
        self.assertEqual(nxt, date(2026, 4, 1))
        inv2, _nxt = sub._generate_term_invoices(date(2026, 1, 1), date(2026, 3, 31))
        self.assertEqual(inv1, inv2)
        free = self._sub(self._contract('COV-FREE'), recurring_price=0.0)
        none, _nxt = free._generate_term_invoices(date(2026, 1, 1), date(2026, 1, 31))
        self.assertFalse(none)
