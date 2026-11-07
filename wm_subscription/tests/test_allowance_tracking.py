#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
#    For full details, see https://www.odoo.com/documentation/20.0/legal/licenses/licenses.html
#
#############################################################################
"""The monthly weight allowance is granted once per month, whichever path
(monthly run, consolidated or direct invoice) bills the collections."""
from datetime import date, datetime, time

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAllowanceTracking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.period_start = today.replace(day=1) - relativedelta(months=1)
        cls.period_end = today.replace(day=1) - relativedelta(days=1)
        cls.partner = cls.env['res.partner'].create({
            'name': 'Allowance Partner', 'billing_mode': 'monthly_run',
        })
        cls.point = cls.env['wm.collection.point'].create({
            'name': 'Allowance Point', 'partner_id': cls.partner.id,
        })
        cls.category = cls.env['wm.waste.category'].create({
            'name': 'Allowance Plastic', 'code': 'ALWPL', 'price': 1.0,
        })
        sla = cls.env['wm.sla'].create({'name': 'Allowance SLA', 'terms_and_conditions': 'Terms'})
        cls.contract = cls.env['wm.partner.contract'].create({
            'name': 'WM-ALLOWANCE',
            'partner_id': cls.partner.id,
            'sla_id': sla.id,
            'collection_point_ids': [(6, 0, cls.point.ids)],
            'from_date': cls.period_start - relativedelta(months=1),
            'to_date': cls.period_end + relativedelta(years=1),
            'frequency': 'weekly',
            'no_of_frequency': 1,
            'billing_basis': 'category_rate',
            'contract_line_ids': [(0, 0, {'category_id': cls.category.id, 'price': 2.0})],
            'state': 'ongoing',
        })
        plan = cls.env['wm.subscription.plan'].create({
            'name': 'Allowance Plan', 'code': 'ALW_PLAN',
            'recurring_price': 50.0, 'billing_cycle': 'monthly',
        })
        cls.sub = cls.env['wm.subscription'].create({
            'partner_id': cls.partner.id,
            'contract_id': cls.contract.id,
            'plan_id': plan.id,
            'date_start': cls.period_start,
            'included_monthly_weight_kg': 100.0,
        })
        cls.sub.write({'state': 'active'})

    def _order(self, weight, day=5):
        start = datetime.combine(self.period_start + relativedelta(days=day), time(10, 0))
        order = self.env['wm.collection.order'].create({
            'partner_id': self.partner.id,
            'collection_point_id': self.point.id,
            'contract_id': self.contract.id,
            'scheduled_start': start,
            'scheduled_end': start + relativedelta(hours=1),
            'actual_start': start,
            'actual_end': start + relativedelta(hours=1),
            'order_line_ids': [(0, 0, {'category_id': self.category.id, 'weight': weight})],
        })
        order.sudo().with_context(programmatic_state_change=True).write({'state': 'completed'})
        return order

    def _run(self):
        run = self.env['wm.monthly.billing.run'].create({
            'period_start': self.period_start,
            'period_end': self.period_end,
            'partner_ids': [(6, 0, self.partner.ids)],
        })
        run.action_run_billing()
        return run

    def _consolidated(self, orders):
        consolidated = self.env['wm.consolidated.invoice'].create({
            'partner_id': self.partner.id,
            'date_from': self.period_start,
            'date_to': self.period_end,
            'order_ids': [(6, 0, orders.ids)],
        })
        consolidated.action_generate_invoice()
        return consolidated

    def test_second_run_in_the_month_does_not_regrant(self):
        """80 kg then 50 kg in two runs: only 20 kg of the 100 kg is left for the second."""
        first = self._order(80.0)
        self.assertFalse(self._run().invoice_ids)
        self.assertEqual(first.allowance_used_kg, 80.0)
        self.assertEqual(first.allowance_subscription_id, self.sub)

        second = self._order(50.0, day=6)
        run = self._run()
        self.assertEqual(second.allowance_used_kg, 20.0)
        self.assertAlmostEqual(run.invoice_ids.amount_untaxed, 60.0)  # 30 kg x 2.0

    def test_direct_invoice_uses_allowance(self):
        """A direct invoice takes the allowance off, and leaves none for the next one."""
        first = self._order(130.0)
        first.action_create_invoice()
        invoice = first.direct_invoice_id
        self.assertAlmostEqual(invoice.amount_untaxed, 60.0)  # 30 kg x 2.0
        credit = invoice.invoice_line_ids.filtered(lambda ln: ln.name.startswith('Subscription allowance'))
        self.assertAlmostEqual(credit.price_subtotal, -200.0)  # 100 kg x 2.0
        self.assertEqual(first.allowance_used_kg, 100.0)

        second = self._order(40.0, day=6)
        second.action_create_invoice()
        self.assertAlmostEqual(second.direct_invoice_id.amount_untaxed, 80.0)
        self.assertEqual(second.allowance_used_kg, 0.0)

    def test_consolidated_invoice_shares_allowance_with_run(self):
        """What a run already granted is not granted again by a consolidated invoice."""
        self._order(80.0)
        self._run()
        second = self._order(50.0, day=6)
        consolidated = self._consolidated(second)
        self.assertAlmostEqual(consolidated.invoice_id.amount_untaxed, 60.0)  # 30 kg x 2.0
        self.assertEqual(second.allowance_used_kg, 20.0)

    def test_reset_consolidated_invoice_releases_allowance(self):
        """Orders taken off a reset invoice give their allowance back."""
        first = self._order(50.0)
        consolidated = self._consolidated(first)
        self.assertAlmostEqual(consolidated.invoice_id.amount_untaxed, 0.0)
        consolidated.invoice_id.button_cancel()
        consolidated.action_reset_to_draft()
        self.assertFalse(first.is_billed)

        second = self._order(100.0, day=6)
        second.action_create_invoice()
        self.assertAlmostEqual(second.direct_invoice_id.amount_untaxed, 0.0)
        self.assertEqual(second.allowance_used_kg, 100.0)

    def test_next_month_has_a_fresh_allowance(self):
        first = self._order(100.0)
        first.action_create_invoice()
        next_month = self._order(60.0, day=(self.period_end - self.period_start).days + 6)
        next_month.action_create_invoice()
        self.assertAlmostEqual(next_month.direct_invoice_id.amount_untaxed, 0.0)
        self.assertEqual(next_month.allowance_period_start, self.period_end + relativedelta(days=1))

    def test_allowance_credited_despite_minimum_weight(self):
        """The free kg are credited even when a minimum weight raises the line."""
        hazardous = self.env['wm.waste.category'].create({
            'name': 'Allowance Hazardous', 'code': 'ALWHZ', 'price': 1.0,
        })
        self.env['wm.category.billing.rule'].create({
            'category_id': hazardous.id,
            'partner_id': self.partner.id,
            'price': 3.9,
            'billing_basis': 'per_kg',
            'min_weight': 50.0,
        })
        self.sub.included_monthly_weight_kg = 10.0
        order = self._order(10.0)
        order.order_line_ids = [(0, 0, {'category_id': hazardous.id, 'weight': 20.0})]
        order.action_create_invoice()
        lines = order.direct_invoice_id.invoice_line_ids
        # The allowance goes to the dearest waste: 50 kg minimum x 3.9 = 195,
        # minus 10 free kg x 3.9 = 39, plus 10 kg x 2.0 = 20 of plastic
        credit = lines.filtered(lambda ln: ln.name.startswith('Subscription allowance'))
        self.assertIn('Allowance Hazardous', credit.name)
        self.assertAlmostEqual(credit.price_subtotal, -39.0)
        self.assertAlmostEqual(order.direct_invoice_id.amount_untaxed, 176.0)

    def test_allowance_windows_leave_no_gap(self):
        """A start on the 31st: each window starts the day after the previous one ends."""
        sub = self.env['wm.subscription'].new({'date_start': date(2026, 1, 31)})
        self.assertIsNone(sub._get_allowance_period(date(2026, 1, 30)))
        self.assertEqual(sub._get_allowance_period(date(2026, 2, 27)), (date(2026, 1, 31), date(2026, 2, 27)))
        self.assertEqual(sub._get_allowance_period(date(2026, 3, 30)), (date(2026, 2, 28), date(2026, 3, 30)))
        self.assertEqual(sub._get_allowance_period(date(2026, 3, 31)), (date(2026, 3, 31), date(2026, 4, 29)))
