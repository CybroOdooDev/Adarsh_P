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
from datetime import date, datetime, time

from freezegun import freeze_time

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionDecisions(TransactionCase):
    """Decision 4: a renewal adds exactly ONE billing cycle (same step as
    activation), the manual Renew works regardless of auto_renew, and the
    cron only renews auto_renew subscriptions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Decision Sub Customer'})
        sla = cls.env['wm.sla'].create({'name': 'Decision SLA', 'terms_and_conditions': 'Terms'})
        cls.contract = cls.env['wm.partner.contract'].create({
            'name': 'Decision Contract',
            'partner_id': cls.partner.id,
            'sla_id': sla.id,
            'from_date': date(2026, 1, 1),
            'to_date': date(2028, 12, 31),
            'frequency': 'monthly',
            'no_of_frequency': 1,
            'billing_basis': 'per_collection',
            'fixed_price': 100.0,
            'max_weight': 500.0,
            'overweight_price': 10.0,
            'state': 'signed',
        })
        Plan = cls.env['wm.subscription.plan']
        cls.plans = {
            cycle: Plan.create({
                'name': 'Decision %s' % cycle,
                'code': 'DEC_%s' % cycle.upper(),
                'recurring_price': 100.0,
                'billing_cycle': cycle,
                'included_monthly_weight_kg': 300.0,
            })
            for cycle in ('monthly', 'quarterly', 'annually')
        }

    def _other_contract(self):
        """A second signed contract: a contract can hold only one live subscription."""
        return self.contract.copy({'name': '%s (2)' % self.contract.name, 'state': 'signed'})

    def _active_sub(self, cycle='monthly', **vals):
        sub = self.env['wm.subscription'].create(dict({
            'partner_id': self.partner.id,
            'contract_id': self.contract.id,
            'plan_id': self.plans[cycle].id,
            'date_start': date(2026, 1, 1),
        }, **vals))
        sub.action_activate()
        return sub

    def _assert_one_cycle_renewal(self, cycle, first_end, renewed_end):
        sub = self._active_sub(cycle)
        self.assertEqual(sub.date_end, first_end)
        invoices_before = len(sub.invoice_ids)
        sub.action_renew()
        self.assertEqual(sub.date_start, date(2026, 1, 1), 'Renewal keeps the start date.')
        self.assertEqual(sub.date_end, renewed_end, '%s renewal adds one cycle.' % cycle)
        self.assertEqual(sub.next_invoice_date, date.fromordinal(renewed_end.toordinal() + 1))
        self.assertEqual(len(sub.invoice_ids) - invoices_before, 1,
                         'Exactly one cycle invoice is generated on renewal.')
        return sub

    @freeze_time('2026-02-10')
    def test_monthly_renewal_adds_one_month(self):
        self._assert_one_cycle_renewal('monthly', date(2026, 1, 31), date(2026, 2, 28))

    @freeze_time('2026-04-10')
    def test_quarterly_renewal_adds_three_months(self):
        self._assert_one_cycle_renewal('quarterly', date(2026, 3, 31), date(2026, 6, 30))

    @freeze_time('2027-01-05')
    def test_annual_renewal_adds_one_year(self):
        self._assert_one_cycle_renewal('annually', date(2026, 12, 31), date(2027, 12, 31))

    @freeze_time('2026-02-10')
    def test_manual_renew_works_without_auto_renew(self):
        sub = self._active_sub(auto_renew=False)
        sub.action_renew()
        self.assertEqual(sub.date_end, date(2026, 2, 28))
        self.assertEqual(sub.next_invoice_date, date(2026, 3, 1))
        self.assertEqual(len(sub.invoice_ids), 2)

    @freeze_time('2026-02-10')
    def test_cron_only_renews_auto_renew(self):
        auto = self._active_sub()
        manual = self._active_sub(auto_renew=False, contract_id=self._other_contract().id)
        self.env['wm.subscription']._cron_process_subscriptions()
        self.assertEqual(auto.date_end, date(2026, 2, 28))
        self.assertEqual(auto.next_invoice_date, date(2026, 3, 1))
        self.assertEqual(auto.state, 'active')
        # Not auto-renewed by the cron: its term (Jan) is over, so it expires.
        self.assertEqual(manual.date_end, date(2026, 1, 31))
        self.assertEqual(manual.next_invoice_date, date(2026, 2, 1))
        self.assertEqual(len(manual.invoice_ids), 1)
        self.assertEqual(manual.state, 'expired')

    def test_quota_window_after_quarterly_renewal(self):
        """The monthly quota window stays the calendar month (anchored on the
        start date) containing today, inside the renewed cycle."""
        if 'wm.collection.order' not in self.env:
            self.skipTest('wm_collection not installed')
        with freeze_time('2026-04-10'):
            sub = self._active_sub('quarterly')
            sub.action_renew()
            self.assertEqual(sub.date_end, date(2026, 6, 30))

        Order = self.env['wm.collection.order']
        captured = []
        original_search = type(Order).search

        def _search(model, domain, *args, **kwargs):
            if model._name == 'wm.collection.order':
                captured.append(list(domain))
            return original_search(model, domain, *args, **kwargs)

        from unittest.mock import patch
        with freeze_time('2026-05-20'), patch.object(type(Order), 'search', _search):
            sub.invalidate_recordset(['current_cycle_weight_kg', 'remaining_quota_kg', 'is_quota_exceeded'])
            self.assertEqual(sub.remaining_quota_kg, 300.0)
        self.assertTrue(captured)
        domain = captured[-1]
        self.assertIn(('scheduled_start', '>=', datetime.combine(date(2026, 5, 1), time.min)), domain)
        self.assertIn(('scheduled_start', '<=', datetime.combine(date(2026, 5, 31), time.max)), domain)
