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

from freezegun import freeze_time

from odoo.tests import TransactionCase, tagged

from odoo.addons.wm_contracts_billing.controllers.portal import WmPortalController
from odoo.addons.wm_subscription.models.wm_subscription import WmSubscription


@tagged('post_install', '-at_install', 'wm_subscription')
class TestSubscriptionLowFixes(TransactionCase):
    """Regression tests: locked recurring price on the report, renewal cron
    savepoints, plus billing low fixes (contract date default, landfill
    diversion flag, lead conversion wizard price/chatter)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Low Fix Sub Customer'})
        cls.sla = cls.env['wm.sla'].create({'name': 'Low Fix SLA', 'terms_and_conditions': 'Terms'})
        cls.contract = cls.env['wm.partner.contract'].create({
            'name': 'Low Fix Contract',
            'partner_id': cls.partner.id,
            'sla_id': cls.sla.id,
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
            'name': 'Low Fix Monthly',
            'code': 'LOW_FIX_M',
            'recurring_price': 123.0,
            'billing_cycle': 'monthly',
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

    # ------------------------------------------------------------------
    # L-13: report shows the price locked on the subscription
    # ------------------------------------------------------------------
    @freeze_time('2026-01-15')
    def test_report_shows_locked_recurring_price(self):
        sub = self._active_sub()
        self.assertEqual(sub.recurring_price, 123.0)
        self.plan.recurring_price = 987.0
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'wm_subscription.action_report_wm_subscription', sub.ids)
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn('123.00', html)
        self.assertNotIn('987.00', html)

    # ------------------------------------------------------------------
    # L-14: one failing renewal is rolled back without blocking the others
    # ------------------------------------------------------------------
    @freeze_time('2026-02-10')
    def test_cron_renewal_failure_rolled_back(self):
        failing = self._active_sub()
        ok = self._active_sub(contract_id=self._other_contract().id)
        failing_invoices = len(failing.invoice_ids)
        failing_end = failing.date_end
        original = WmSubscription._generate_term_invoices

        def _generate(sub, *args, **kwargs):
            res = original(sub, *args, **kwargs)
            if sub == failing:
                raise ValueError('boom')
            return res

        with patch.object(WmSubscription, '_generate_term_invoices', _generate):
            self.env['wm.subscription']._cron_process_subscriptions()

        self.assertEqual(len(failing.invoice_ids), failing_invoices,
                         'Invoices of a failed renewal must be rolled back.')
        self.assertEqual(failing.date_end, failing_end)
        self.assertTrue(failing.message_ids.filtered(lambda m: 'boom' in (m.body or '')))
        # One billing cycle (monthly plan): Feb 2026.
        self.assertEqual(ok.date_end, date(2026, 2, 28), 'Other due subscriptions are still renewed.')

    # ------------------------------------------------------------------
    # L-07 (billing): contract from_date default is evaluated per call
    # ------------------------------------------------------------------
    def test_contract_from_date_default_not_frozen(self):
        field = self.env['wm.partner.contract']._fields['from_date']
        self.assertTrue(callable(field.default))
        with freeze_time('2030-06-15'):
            defaults = self.env['wm.partner.contract'].default_get(['from_date'])
        self.assertEqual(defaults['from_date'], date(2030, 6, 15))

    # ------------------------------------------------------------------
    # L-08 (billing): landfill diversion uses real recyclable flags
    # ------------------------------------------------------------------
    def test_portal_diversion_uses_recyclable_flag(self):
        recycle_cat = self.env['wm.waste.category'].create({
            'name': 'Low Fix Recycle', 'code': 'LF-REC', 'default_processing': 'recycle'})
        dispose_cat = self.env['wm.waste.category'].create({
            'name': 'Low Fix Dispose', 'code': 'LF-DIS', 'default_processing': 'dispose'})
        recyclable = self.env['product.product'].create({'name': 'LF Recyclable', 'recyclable': True})
        landfill = self.env['product.product'].create({'name': 'LF Landfill', 'recyclable': False})
        Line = self.env['wm.collection.order.line']
        check = WmPortalController._wm_line_is_diverted
        line = Line.new({'category_id': recycle_cat.id, 'product_id': landfill.id})
        self.assertFalse(check(line, recycle_cat))
        line = Line.new({'category_id': dispose_cat.id, 'product_id': recyclable.id})
        self.assertTrue(check(line, dispose_cat))
        line = Line.new({'category_id': dispose_cat.id})
        self.assertFalse(check(line, dispose_cat))
        line = Line.new({'category_id': recycle_cat.id})
        self.assertTrue(check(line, recycle_cat))
        # Without a product only 'recycle' / 'compost' count as diverted
        for method, expected in (('recycle', True), ('compost', True),
                                 ('sort', False), ('dispose', False),
                                 ('hazardous_treatment', False), (False, False)):
            cat = self.env['wm.waste.category'].create({
                'name': 'Diversion Rule %s' % method, 'code': 'DIV-%s' % method,
                'default_processing': method})
            line = Line.new({'category_id': cat.id})
            self.assertEqual(check(line, cat), expected, method)
        # Product recyclable flag still wins over the category method
        sort_cat = self.env['wm.waste.category'].search(
            [('code', '=', 'DIV-sort')], limit=1)
        line = Line.new({'category_id': sort_cat.id, 'product_id': recyclable.id})
        self.assertTrue(check(line, sort_cat))

    # ------------------------------------------------------------------
    # L-08 (billing): lead conversion wizard price and chatter link
    # ------------------------------------------------------------------
    def test_conversion_wizard_no_amount_total_prefill_and_html_link(self):
        product = self.env['product.product'].create({'name': 'LF Service', 'type': 'service', 'list_price': 500.0})
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})],
        })
        self.assertGreater(order.amount_total, 0.0)
        action = order.action_convert_to_wm_contract()
        self.assertNotIn('default_fixed_price', action['context'])
        Wizard = self.env['wm.lead.conversion.wizard'].with_context(**action['context'])
        defaults = Wizard.default_get(['order_id', 'fixed_price'])
        self.assertEqual(defaults['fixed_price'], 0.0)
        wizard = Wizard.create({
            'order_id': order.id,
            'partner_id': self.partner.id,
            'contract_to_date': date(2099, 1, 1),
            'sla_id': self.sla.id,
            'fixed_price': 25.0,
        })
        res = wizard.action_confirm_conversion()
        contract = self.env['wm.partner.contract'].browse(res['res_id'])
        message = order.message_ids.filtered(lambda m: contract.name in (m.body or ''))[:1]
        self.assertTrue(message)
        self.assertIn('<a href=', message.body)
        self.assertNotIn('&lt;a', message.body)
