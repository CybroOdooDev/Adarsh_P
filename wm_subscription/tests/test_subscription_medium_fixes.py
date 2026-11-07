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
from datetime import date

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionMediumFixes(TransactionCase):
    """Regression tests: renewal keeps the start date, is only allowed when
    due, invoices use the subscription currency and portal requests use the
    benefits frozen on the subscription."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Medium Fix Sub Customer'})
        sla = cls.env['wm.sla'].create({'name': 'Medium Fix SLA', 'terms_and_conditions': 'Terms'})
        cls.contract = cls.env['wm.partner.contract'].create({
            'name': 'Medium Fix Contract',
            'partner_id': cls.partner.id,
            'sla_id': sla.id,
            'from_date': date(2026, 1, 1),
            'to_date': date(2027, 12, 31),
            'frequency': 'monthly',
            'no_of_frequency': 1,
            'billing_basis': 'per_collection',
            'fixed_price': 100.0,
            'max_weight': 500.0,
            'overweight_price': 10.0,
            'state': 'signed',
        })
        cls.plan = cls.env['wm.subscription.plan'].create({
            'name': 'Medium Fix Monthly',
            'code': 'MED_FIX_M',
            'recurring_price': 100.0,
            'billing_cycle': 'monthly',
            'extra_pickup_discount': 10.0,
            'free_container_swaps_per_year': 2,
            'priority_sla_level': 'priority_24h',
        })

    def _other_contract(self):
        """A second signed contract: a contract can hold only one live subscription."""
        return self.contract.copy({'name': '%s (2)' % self.contract.name, 'state': 'signed'})

    def _active_sub(self, **vals):
        sub = self.env['wm.subscription'].create(dict({
            'partner_id': self.partner.id,
            'contract_id': self.contract.id,
            'plan_id': self.plan.id,
            'date_start': date(2026, 1, 1),
        }, **vals))
        sub.action_activate()
        return sub

    @freeze_time('2026-02-10')
    def test_renew_keeps_start_date(self):
        """S-01: renewing extends the end date without moving the start date."""
        sub = self._active_sub()
        self.assertEqual(sub.next_invoice_date, date(2026, 2, 1))
        sub.action_renew()
        self.assertEqual(sub.date_start, date(2026, 1, 1))
        # Renewal adds one billing cycle (monthly plan), not a full year.
        self.assertEqual(sub.date_end, date(2026, 2, 28))
        self.assertEqual(sub.next_invoice_date, date(2026, 3, 1))

    @freeze_time('2026-02-10')
    def test_renew_only_when_due_and_active(self):
        """S-02: manual renew is refused when not due or not active."""
        sub = self._active_sub()
        sub.action_renew()
        invoice_count = len(sub.invoice_ids)
        with self.assertRaises(UserError):
            sub.action_renew()
        self.assertEqual(len(sub.invoice_ids), invoice_count)

        paused = self._active_sub(contract_id=self._other_contract().id)
        paused.action_pause()
        with self.assertRaises(UserError):
            paused.action_renew()

    @freeze_time('2026-01-15')
    def test_invoices_use_subscription_currency(self):
        """S-03: generated invoices are in the subscription currency."""
        currency = self.env['res.currency'].with_context(active_test=False).search(
            [('id', '!=', self.env.company.currency_id.id)], limit=1)
        currency.active = True
        sub = self._active_sub(currency_id=currency.id)
        self.assertTrue(sub.invoice_ids)
        self.assertEqual(sub.invoice_ids.currency_id, currency)

    @freeze_time('2026-01-15')
    def test_portal_request_uses_frozen_subscription_benefits(self):
        """S-04: portal pricing reads the subscription's frozen benefits."""
        sub = self._active_sub()
        # Plan edits only reach draft subscriptions: the active one stays frozen
        self.plan.write({'extra_pickup_discount': 50.0, 'priority_sla_level': 'vip_same_day'})
        self.assertEqual(sub.extra_pickup_discount, 10.0)
        point = self.env['wm.collection.point'].create({
            'name': 'Medium Fix Site', 'partner_id': self.partner.id,
        })
        request = self.env['wm.portal.service.request'].create({
            'partner_id': self.partner.id,
            'collection_point_id': point.id,
            'request_type': 'extra_pickup',
            'requested_date': date(2026, 1, 15),
        })
        self.assertEqual(request.active_subscription_id, sub)
        self.assertEqual(request.subscriber_discount_pct, 10.0)
        self.assertEqual(request.priority_sla_level, 'priority_24h')
