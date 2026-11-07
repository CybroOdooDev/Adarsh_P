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

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionDates(TransactionCase):
    """Test subscription date_start and date_end computation and inverse calculation based on billing cycle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Subscription Test Customer',
        })
        sla = cls.env['wm.sla'].create({
            'name': 'Test SLA Subscription',
            'terms_and_conditions': 'Standard SLA Terms',
        })
        cls.contract = cls.env['wm.partner.contract'].create({
            'name': 'Test Sub Contract',
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
        cls.plan_monthly = cls.env['wm.subscription.plan'].create({
            'name': 'Monthly Plan',
            'code': 'SUB_M_01',
            'recurring_price': 100.0,
            'billing_cycle': 'monthly',
        })
        cls.plan_quarterly = cls.env['wm.subscription.plan'].create({
            'name': 'Quarterly Plan',
            'code': 'SUB_Q_01',
            'recurring_price': 250.0,
            'billing_cycle': 'quarterly',
        })
        cls.plan_annual = cls.env['wm.subscription.plan'].create({
            'name': 'Annual Plan',
            'code': 'SUB_A_01',
            'recurring_price': 900.0,
            'billing_cycle': 'annually',
        })

    def test_01_compute_date_end_monthly(self):
        """Verify monthly plan sets date_end to 1 month - 1 day after date_start."""
        sub = self.env['wm.subscription'].create({
            'partner_id': self.partner.id,
            'contract_id': self.contract.id,
            'plan_id': self.plan_monthly.id,
            'date_start': date(2026, 1, 1),
        })
        self.assertEqual(sub.date_end, date(2026, 1, 31))

    def test_02_compute_date_end_quarterly(self):
        """Verify quarterly plan sets date_end to 3 months - 1 day after date_start."""
        sub = self.env['wm.subscription'].create({
            'partner_id': self.partner.id,
            'contract_id': self.contract.id,
            'plan_id': self.plan_quarterly.id,
            'date_start': date(2026, 1, 1),
        })
        self.assertEqual(sub.date_end, date(2026, 3, 31))

    def test_03_compute_date_end_annually(self):
        """Verify annual plan sets date_end to 1 year - 1 day after date_start."""
        sub = self.env['wm.subscription'].create({
            'partner_id': self.partner.id,
            'contract_id': self.contract.id,
            'plan_id': self.plan_annual.id,
            'date_start': date(2026, 1, 1),
        })
        self.assertEqual(sub.date_end, date(2026, 12, 31))

    def test_04_inverse_date_end(self):
        """Verify editing date_end updates date_start inversely."""
        sub = self.env['wm.subscription'].create({
            'partner_id': self.partner.id,
            'contract_id': self.contract.id,
            'plan_id': self.plan_monthly.id,
            'date_start': date(2026, 1, 1),
        })
        sub.write({'date_end': date(2026, 6, 30)})
        self.assertEqual(sub.date_start, date(2026, 6, 1))
