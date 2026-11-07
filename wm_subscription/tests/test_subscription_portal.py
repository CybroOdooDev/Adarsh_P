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

from datetime import date

from odoo.exceptions import AccessError
from odoo.http.requestlib import Request
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionPortal(HttpCase):
    """Customer portal: list, detail, PDF, cancellation, home counter and plan access."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='sub_portal_a', password='sub_portal_a',
                                 groups='base.group_portal')
        cls.other = new_test_user(cls.env, login='sub_portal_b', password='sub_portal_b',
                                  groups='base.group_portal')
        cls.plan = cls.env['wm.subscription.plan'].create({
            'name': 'Portal Plan', 'code': 'PORTALP', 'recurring_price': 25.0, 'billing_cycle': 'monthly'})
        cls.hidden_plan = cls.env['wm.subscription.plan'].create({
            'name': 'Someone Else Plan', 'code': 'HIDDENP', 'recurring_price': 99.0, 'billing_cycle': 'annually'})
        cls.sub = cls._subscription(cls.user.partner_id, cls.plan, 'active')
        cls.other_sub = cls._subscription(cls.other.partner_id, cls.hidden_plan, 'active')

    @classmethod
    def _subscription(cls, partner, plan, state):
        sla = cls.env['wm.sla'].search([], limit=1) or cls.env['wm.sla'].create({'name': 'Portal Sub SLA'})
        contract = cls.env['wm.partner.contract'].create({
            'partner_id': partner.id, 'sla_id': sla.id,
            'from_date': date(2026, 1, 1), 'to_date': date(2028, 12, 31),
            'frequency': 'monthly', 'no_of_frequency': 1, 'billing_basis': 'per_collection',
            'fixed_price': 10.0, 'max_weight': 100.0, 'overweight_price': 1.0, 'state': 'signed'})
        sub = cls.env['wm.subscription'].create({
            'partner_id': partner.id, 'plan_id': plan.id, 'contract_id': contract.id})
        sub.sudo().write({'state': state})
        return sub

    def _post(self, url, data=None):
        data = dict(data or {}, csrf_token=Request.csrf_token(self))
        return self.url_open(url, data=data, allow_redirects=False)

    def test_list_and_detail_show_only_own_subscriptions(self):
        self.authenticate('sub_portal_a', 'sub_portal_a')
        listing = self.url_open('/my/subscriptions')
        self.assertEqual(listing.status_code, 200)
        self.assertIn(self.sub.name, listing.text)
        self.assertNotIn(self.other_sub.name, listing.text)
        detail = self.url_open('/my/subscriptions/%s' % self.sub.id)
        self.assertEqual(detail.status_code, 200)
        self.assertIn('Portal Plan', detail.text)
        foreign = self.url_open('/my/subscriptions/%s' % self.other_sub.id, allow_redirects=False)
        self.assertIn(foreign.status_code, (302, 303))
        self.assertIn('/my/subscriptions', foreign.headers['Location'])

    def test_pdf_download_is_limited_to_the_owner(self):
        self.authenticate('sub_portal_a', 'sub_portal_a')
        res = self.url_open('/my/subscriptions/%s/pdf' % self.sub.id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers['Content-Type'], 'application/pdf')
        foreign = self.url_open('/my/subscriptions/%s/pdf' % self.other_sub.id, allow_redirects=False)
        self.assertIn(foreign.status_code, (302, 303))

    def test_portal_cancel_runs_without_manager_rights(self):
        # the customer is not a contract manager: the route carries out the cancellation
        with self.assertRaises(AccessError):
            self.sub.with_user(self.user).action_cancel(reason='direct call')
        self.authenticate('sub_portal_a', 'sub_portal_a')
        res = self._post('/my/subscriptions/%s/cancel' % self.sub.id, {'reason': 'moving away'})
        self.assertIn(res.status_code, (302, 303))
        self.sub.invalidate_recordset()
        self.assertEqual(self.sub.state, 'cancelled')
        self.assertEqual(self.sub.cancel_reason, 'moving away')

    def test_portal_cancel_cannot_touch_another_customers_subscription(self):
        self.authenticate('sub_portal_a', 'sub_portal_a')
        self._post('/my/subscriptions/%s/cancel' % self.other_sub.id, {'reason': 'nope'})
        self.other_sub.invalidate_recordset()
        self.assertEqual(self.other_sub.state, 'active')

    def test_cancel_ignores_a_subscription_that_is_over(self):
        done = self._subscription(self.user.partner_id, self.plan, 'cancelled')
        self.authenticate('sub_portal_a', 'sub_portal_a')
        res = self._post('/my/subscriptions/%s/cancel' % done.id, {'reason': 'again'})
        self.assertIn(res.status_code, (302, 303))
        done.invalidate_recordset()
        self.assertEqual(done.state, 'cancelled')

    def test_home_counter_and_card(self):
        self.authenticate('sub_portal_a', 'sub_portal_a')
        res = self.make_jsonrpc_request('/my/counters', {'counters': {'subscription_count': 'common_category'}})
        self.assertEqual(res, {'subscription_count': 1})
        home = self.url_open('/my')
        self.assertIn('/my/subscriptions', home.text)

    def test_portal_user_reads_only_plans_of_own_subscriptions(self):
        Plan = self.env['wm.subscription.plan'].with_user(self.user)
        self.assertEqual(Plan.search([('code', 'in', ('PORTALP', 'HIDDENP'))]).code, 'PORTALP')
        with self.assertRaises(AccessError):
            self.hidden_plan.with_user(self.user).read(['name'])
        with self.assertRaises(AccessError):
            self.plan.with_user(self.user).write({'name': 'Hacked'})
