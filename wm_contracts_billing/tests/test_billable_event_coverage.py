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
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'wm_billing')
class TestBillableEventCoverage(TransactionCase):
    """Constraints, pricing, state transitions and invoicing access of ad-hoc billable events."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Event Coverage Customer'})
        cls.today = fields.Date.today()
        cls.rule = cls.env['wm.event.pricing.rule'].create({
            'event_type': 'overweight',
            'price_unit': 2.0,
            'min_charge': 100.0,
            'effective_date': cls.today - timedelta(days=10),
        })

    def _event(self, **kw):
        vals = {
            'partner_id': self.partner.id,
            'event_type': 'overweight',
            'quantity': 10.0,
        }
        vals.update(kw)
        return self.env['wm.billable.event'].create(vals)

    def test_quantity_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._event(quantity=0.0)
        event = self._event()
        with self.assertRaises(ValidationError):
            event.quantity = -3.0

    def test_min_charge_raises_unit_price(self):
        event = self._event(quantity=10.0)  # 10 * 2 = 20 < 100 minimum
        self.assertAlmostEqual(event.price_unit, 10.0)
        self.assertAlmostEqual(event.amount, 100.0)
        self.assertEqual(event.rate_source, self.rule.name)
        big = self._event(quantity=100.0)  # 200 > minimum
        self.assertAlmostEqual(big.price_unit, 2.0)
        self.assertAlmostEqual(big.amount, 200.0)

    def test_no_matching_rule_and_expired_rule(self):
        event = self._event(event_type='emergency_callout')
        self.assertEqual(event.price_unit, 0.0)
        self.assertIn('manual price', event.rate_source)
        self.rule.expiry_date = self.today - timedelta(days=1)
        expired = self._event(event_date=self.today)
        self.assertEqual(expired.price_unit, 0.0)

    def test_discount_is_clamped(self):
        event = self._event(quantity=100.0, discount_pct=25.0)
        self.assertAlmostEqual(event.amount, 150.0)
        event.discount_pct = 250.0
        self.assertAlmostEqual(event.amount, 0.0)
        event.discount_pct = -50.0
        self.assertAlmostEqual(event.amount, 200.0)
        vals = event._prepare_invoice_line_vals()
        self.assertEqual(vals['discount'], 0.0)
        self.assertEqual(vals['quantity'], 100.0)
        self.assertIn(event.name, vals['name'])

    def test_confirm_only_from_draft(self):
        event = self._event()
        self.assertTrue(event.name.startswith('WM') or event.name != 'New')
        event.action_confirm()
        self.assertEqual(event.state, 'confirmed')
        with self.assertRaises(UserError):
            event.action_confirm()

    def test_cancel_and_reset_transitions(self):
        event = self._event()
        event.action_cancel()
        self.assertEqual(event.state, 'cancelled')
        event.action_reset_draft()
        self.assertEqual(event.state, 'draft')
        event.state = 'invoiced'
        with self.assertRaises(ValidationError):
            event.action_reset_draft()
        with self.assertRaises(UserError):
            event.action_cancel()

    def test_invoice_requires_confirmed_state(self):
        event = self._event()
        with self.assertRaises(UserError):
            event.action_create_invoice()

    def test_invoice_requires_billing_group(self):
        event = self._event()
        event.action_confirm()
        user = new_test_user(self.env, login='evt_cov_plain', groups='base.group_user')
        self.assertFalse(self.env['wm.billable.event'].with_user(user)._can_create_invoices())
        with self.assertRaises(AccessError):
            event.with_user(user).action_create_invoice()
        finance = new_test_user(self.env, login='evt_cov_fin', groups='base.group_user,wm_base.group_wm_finance')
        self.assertTrue(self.env['wm.billable.event'].with_user(finance)._can_create_invoices())

    def test_invoice_and_cancel_releases_event(self):
        event = self._event(quantity=100.0)
        event.action_confirm()
        action = event.action_create_invoice()
        self.assertEqual(event.state, 'invoiced')
        invoice = event.invoice_id
        self.assertTrue(invoice)
        self.assertEqual(action['res_id'], invoice.id)
        self.assertEqual(event.invoice_count, 1)
        self.assertEqual(event.action_view_invoice()['res_id'], invoice.id)
        with self.assertRaises(UserError):
            event.action_create_invoice()
        # Cancelling the invoice releases the event so it can be billed again
        invoice.button_cancel()
        self.assertEqual(event.state, 'confirmed')
        self.assertFalse(event.invoice_id)
        self.assertFalse(event.invoice_line_id)

    def test_view_invoice_without_invoice(self):
        self.assertIsNone(self._event().action_view_invoice())

    def test_emergency_callout_from_collection_point(self):
        point = self.env['wm.collection.point'].create({
            'name': 'Callout Point', 'partner_id': self.partner.id,
        })
        action = point.action_log_emergency_callout()
        self.assertEqual(action['res_model'], 'wm.billable.event')
        ctx = action['context']
        self.assertEqual(ctx['default_collection_point_id'], point.id)
        self.assertEqual(ctx['default_partner_id'], self.partner.id)
        self.assertEqual(ctx['default_event_type'], 'emergency_callout')
        # The defaults must produce a valid event.
        event = self.env['wm.billable.event'].with_context(**ctx).create({})
        self.assertEqual(event.collection_point_id, point)
        self.assertEqual(event.event_type, 'emergency_callout')
        # The button is added to the collection point form by this module.
        arch = point.get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('action_log_emergency_callout', arch)

    def test_dispatcher_can_log_emergency_callout(self):
        """Dispatchers see the Log Emergency Callout button, so they must be able to save the event."""
        dispatcher = new_test_user(
            self.env, login='evt_cov_dispatch', groups='base.group_user,wm_base.group_wm_dispatcher')
        point = self.env['wm.collection.point'].create({
            'name': 'Dispatcher Callout Point', 'partner_id': self.partner.id,
        })
        action = point.with_user(dispatcher).action_log_emergency_callout()
        event = self.env['wm.billable.event'].with_user(dispatcher).with_context(
            **action['context']).create({})
        self.assertEqual(event.event_type, 'emergency_callout')
        event.action_confirm()
        self.assertEqual(event.state, 'confirmed')
        # Invoicing stays with billing staff.
        with self.assertRaises(AccessError):
            event.action_create_invoice()

    def test_dispatcher_cannot_change_pricing(self):
        """Dispatchers log events at the rule price; prices and events past draft stay with billing."""
        dispatcher = new_test_user(
            self.env, login='evt_cov_dispatch2', groups='base.group_user,wm_base.group_wm_dispatcher')
        Event = self.env['wm.billable.event'].with_user(dispatcher)
        vals = {'partner_id': self.partner.id, 'event_type': 'extra_pickup'}
        with self.assertRaises(AccessError):
            Event.create(dict(vals, price_unit=1.0))
        with self.assertRaises(AccessError):
            Event.create(dict(vals, state='confirmed'))
        event = Event.create(vals)
        self.assertFalse(event.can_edit_pricing)
        with self.assertRaises(AccessError):
            event.write({'discount_pct': 50.0})
        event.write({'notes': 'Draft events stay editable'})
        event.action_confirm()
        with self.assertRaises(AccessError):
            event.write({'quantity': 5.0})
        event.action_reset_draft()
        event.write({'quantity': 2.0})
        event.sudo().write({'state': 'invoiced'})
        with self.assertRaises(AccessError):
            event.write({'state': 'draft'})
        # Billing staff keep full control
        finance = new_test_user(
            self.env, login='evt_cov_fin2', groups='base.group_user,wm_base.group_wm_finance')
        fin_event = event.with_user(finance)
        self.assertTrue(fin_event.can_edit_pricing)
        fin_event.write({'price_unit': 75.0})
        self.assertEqual(event.price_unit, 75.0)
