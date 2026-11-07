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
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'wm_subscription')
class TestWeightRollover(TransactionCase):
    """Allow Weight Rollover adds the previous month's unused allowance to the next one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Rollover Customer'})
        cls.plan = cls.env['wm.subscription.plan'].create({
            'name': 'Rollover Plan',
            'code': 'ROLL_TEST',
            'recurring_price': 100.0,
            'billing_cycle': 'annually',
            'included_monthly_weight_kg': 300.0,
            'allow_rollover_weight': True,
        })
        sla = cls.env['wm.sla'].create({'name': 'Rollover SLA', 'terms_and_conditions': 'Terms'})
        contract = cls.env['wm.partner.contract'].create({
            'name': 'Rollover Contract',
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
        cls.sub = cls.env['wm.subscription'].create({
            'partner_id': cls.partner.id,
            'contract_id': contract.id,
            'plan_id': cls.plan.id,
            'date_start': date(2026, 1, 10),
        })

    def _with_collected(self, weights):
        """Patch the collected weight per window start."""
        return patch.object(
            type(self.sub), '_get_collected_weight',
            lambda sub, date_from, date_to: weights.get(date_from, 0.0))

    def test_unused_allowance_rolls_over(self):
        with self._with_collected({date(2026, 1, 10): 100.0}):
            self.assertEqual(self.sub._get_rollover_kg(date(2026, 2, 10)), 200.0)
            self.assertEqual(self.sub._get_period_allowance_kg(date(2026, 2, 10)), 500.0)

    def test_overused_month_carries_nothing(self):
        with self._with_collected({date(2026, 1, 10): 450.0}):
            self.assertEqual(self.sub._get_period_allowance_kg(date(2026, 2, 10)), 300.0)

    def test_only_one_month_carries(self):
        """Nothing used for two months: only one month's allowance is carried."""
        with self._with_collected({}):
            self.assertEqual(self.sub._get_period_allowance_kg(date(2026, 3, 10)), 600.0)

    def test_first_month_has_no_rollover(self):
        with self._with_collected({}):
            self.assertEqual(self.sub._get_period_allowance_kg(date(2026, 1, 10)), 300.0)

    def test_rollover_disabled(self):
        self.plan.allow_rollover_weight = False
        with self._with_collected({}):
            self.assertEqual(self.sub._get_period_allowance_kg(date(2026, 2, 10)), 300.0)
