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

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionCriticalFixes(TransactionCase):
    """Regression tests: only contract managers manage subscriptions, and only drafts activate."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Fix Sub Customer'})
        sla = cls.env['wm.sla'].create({'name': 'Fix Sub SLA', 'terms_and_conditions': 'Terms'})
        cls.contract = cls.env['wm.partner.contract'].create({
            'name': 'Fix Sub Contract',
            'partner_id': cls.partner.id,
            'sla_id': sla.id,
            'from_date': date(2026, 1, 1),
            'to_date': date(2026, 12, 31),
            'frequency': 'monthly',
            'no_of_frequency': 1,
            'billing_basis': 'per_collection',
            'fixed_price': 100.0,
            'max_weight': 500.0,
            'overweight_price': 10.0,
            'state': 'signed',
        })
        cls.plan = cls.env['wm.subscription.plan'].create({
            'name': 'Fix Monthly', 'code': 'FIX_SUB_M', 'recurring_price': 100.0, 'billing_cycle': 'monthly',
        })
        cls.driver = new_test_user(cls.env, login='wm_fix_sub_driver', groups='wm_base.group_wm_driver')
        cls.manager = new_test_user(cls.env, login='wm_fix_sub_mgr',
                                    groups='wm_contracts_billing.group_wm_contract_manager')

    def _sub(self):
        return self.env['wm.subscription'].create({
            'partner_id': self.partner.id,
            'contract_id': self.contract.id,
            'plan_id': self.plan.id,
            'date_start': date(2026, 1, 1),
        })

    def test_internal_user_cannot_create_or_activate(self):
        """Ordinary internal users (e.g. drivers) can read but not create, activate or renew."""
        with self.assertRaises(AccessError):
            self.env['wm.subscription'].with_user(self.driver).create({
                'partner_id': self.partner.id, 'contract_id': self.contract.id, 'plan_id': self.plan.id,
            })
        sub = self._sub()
        with self.assertRaises(AccessError):
            sub.with_user(self.driver).action_activate()
        with self.assertRaises(AccessError):
            sub.with_user(self.driver).action_renew()
        self.assertEqual(sub.state, 'draft')

    def test_only_draft_subscriptions_activate(self):
        """A cancelled subscription cannot be re-activated with a back-dated term."""
        sub = self._sub()
        sub.with_user(self.manager).action_activate()
        self.assertEqual(sub.state, 'active')
        sub.with_user(self.manager).action_cancel()
        invoice_count = len(sub.invoice_ids) if 'invoice_ids' in sub._fields else None
        with self.assertRaises(UserError):
            sub.with_user(self.manager).action_activate()
        self.assertEqual(sub.state, 'cancelled')
        if invoice_count is not None:
            self.assertEqual(len(sub.invoice_ids), invoice_count)

    def test_activation_does_not_overwrite_contract_included_weight(self):
        """The monthly plan quota is not copied into the contract's per-collection threshold."""
        self.plan.included_monthly_weight_kg = 500.0
        before = self.contract.included_weight
        sub = self._sub()
        sub.with_user(self.manager).action_activate()
        self.assertEqual(sub.state, 'active')
        self.assertEqual(self.contract.included_weight, before)

    def test_cron_resumes_subscription_after_planned_pause_end(self):
        """A subscription paused until a date (service hold) resumes by itself on that date."""
        sub = self._sub()
        sub.with_user(self.manager).action_activate()
        sub.action_pause(resume_date=date.today())
        self.assertEqual(sub.state, 'paused')
        self.env['wm.subscription']._cron_process_subscriptions()
        self.assertEqual(sub.state, 'active')
