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
from odoo import fields, models


class WmCollectionOrder(models.Model):
    """Tracks the subscription weight allowance each billed collection used."""
    _inherit = 'wm.collection.order'

    allowance_subscription_id = fields.Many2one(
        'wm.subscription',
        readonly=True,
        copy=False,
        ondelete='set null',
        help='Subscription whose monthly weight allowance covered part of this collection.',
    )
    allowance_period_start = fields.Date(
        string='Allowance Month',
        readonly=True,
        copy=False,
        help='Start of the monthly allowance window this collection was counted in.',
    )
    allowance_used_kg = fields.Float(
        string='Covered by Subscription (kg)',
        readonly=True,
        copy=False,
        help='Weight of this collection billed free under the subscription allowance.',
    )

    def _get_allowance_subscription(self):
        """
        The active subscription whose allowance covers this order: the one of
        the order's contract, else a customer subscription not tied to any
        contract (another contract's allowance must never be used).
        """
        self.ensure_one()
        Subscription = self.env['wm.subscription'].sudo()
        sub = Subscription.browse()
        if self.contract_id:
            sub = Subscription.search([
                ('contract_id', '=', self.contract_id.id),
                ('state', '=', 'active'),
            ], limit=1)
        if not sub and self.partner_id:
            sub = Subscription.search([
                ('partner_id', '=', self.partner_id.id),
                ('contract_id', '=', False),
                ('state', '=', 'active'),
            ], limit=1)
        return sub

    def _get_allowance_budgets(self):
        """
        Allowance left per (subscription, monthly window): the plan's monthly
        weight minus what the other orders of that window used and are still
        billed with. Orders billed again (e.g. after their invoice was reset)
        give back what they used before.
        """
        budget_of = {}
        subs = self.env['wm.subscription'].sudo()
        for order in self:
            sub = order._get_allowance_subscription()
            period = sub and sub._get_allowance_period(order._get_billing_service_date())
            if period:
                budget_of[order.id] = (sub.id, period[0])
                subs |= sub
        if not subs:
            return budget_of, {}
        # Serialize concurrent invoicing against the same allowance, then read it
        self.env.cr.execute(
            "SELECT id FROM wm_subscription WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(subs.ids)])
        Order = self.env['wm.collection.order'].sudo()
        remaining = {}
        for sub_id, period_start in set(budget_of.values()):
            sub = subs.browse(sub_id)
            used = sum(Order.search([
                ('allowance_subscription_id', '=', sub_id),
                ('allowance_period_start', '=', period_start),
                ('is_billed', '=', True),
                ('id', 'not in', self.ids),
            ]).mapped('allowance_used_kg'))
            remaining[(sub_id, period_start)] = max(sub._get_period_allowance_kg(period_start) - used, 0.0)
        return budget_of, remaining

    def _record_allowance_usage(self, budget_of, used):
        for order in self.sudo():
            kg = used.get(order.id, 0.0)
            sub_id, period_start = budget_of.get(order.id) if kg else (False, False)
            order.write({
                'allowance_subscription_id': sub_id,
                'allowance_period_start': period_start,
                'allowance_used_kg': kg,
            })
