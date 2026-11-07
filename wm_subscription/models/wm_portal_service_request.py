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
from odoo import api, fields, models


class WmPortalServiceRequest(models.Model):
    """Extends Portal Service Request with active subscription discounts and free swaps."""
    _inherit = 'wm.portal.service.request'

    active_subscription_id = fields.Many2one(
        'wm.subscription',

        compute='_compute_subscriber_pricing',
        store=True,
    )
    subscriber_discount_pct = fields.Float(
        string='Subscriber Discount (%)',
        compute='_compute_subscriber_pricing',
        store=True,
    )
    discount_amount = fields.Monetary(
        string='Discount Savings',
        currency_field='currency_id',
        compute='_compute_subscriber_pricing',
        store=True,
    )
    final_estimated_price = fields.Monetary(
        string='Final Price',
        currency_field='currency_id',
        compute='_compute_subscriber_pricing',
        store=True,
    )
    is_free_swap = fields.Boolean(
        string='Covered as Free Swap',
        compute='_compute_subscriber_pricing',
        store=True,
    )
    priority_sla_level = fields.Selection([
        ('standard', 'Standard SLA'),
        ('priority_24h', 'Priority 24h Response'),
        ('vip_same_day', 'VIP Same-Day Response'),
    ], string='Subscriber SLA Response', compute='_compute_subscriber_pricing', store=True)

    base_estimated_price = fields.Monetary(
        compute='_compute_base_estimated_price', store=True, readonly=False, precompute=True)

    @api.depends('request_type', 'category_id')
    def _compute_base_estimated_price(self):
        """Default estimate by request type; a price entered by the user is kept until the type or category changes."""
        PricingRule = self.env['wm.pricing.rule'].sudo() if 'wm.pricing.rule' in self.env else None
        for req in self:
            if req.request_type == 'extra_pickup':
                rule = PricingRule is not None and req.category_id and PricingRule.search([
                    ('waste_category_id', '=', req.category_id.id),
                    ('active', '=', True),
                ], limit=1)
                req.base_estimated_price = rule.min_charge if rule and rule.min_charge else 50.0
            elif req.request_type == 'container_swap':
                req.base_estimated_price = 75.0
            else:
                req.base_estimated_price = 0.0

    @api.depends('partner_id', 'request_type', 'category_id', 'container_type_id',
                 'base_estimated_price', 'requested_date')
    def _compute_subscriber_pricing(self):
        """
        Compute dynamic pricing, plan discounts, free swaps, and SLA level
        based on the customer's active subscription.
        """
        for req in self:
            sub = False
            discount_pct = 0.0
            free_swap = False
            sla_level = 'standard'

            if req.partner_id:
                req_dt = req.requested_date or fields.Date.today()
                domain = [
                    ('partner_id', '=', req.partner_id.id),
                    ('state', '=', 'active'),
                    '|',
                    ('date_start', '=', False),
                    ('date_start', '<=', req_dt),
                ]
                active_sub = self.env['wm.subscription'].sudo().search(domain, limit=1)
                if active_sub:
                    sub = active_sub
                    # Use the benefits frozen on the subscription, not the
                    # (possibly since edited) plan defaults.
                    sla_level = active_sub.priority_sla_level or 'standard'

                    if req.request_type == 'extra_pickup':
                        discount_pct = active_sub.extra_pickup_discount or 0.0
                    elif req.request_type == 'container_swap':
                        if active_sub.free_container_swaps_per_year > active_sub._count_free_swaps(exclude_request=req):
                            free_swap = True
                            discount_pct = 100.0

            req.active_subscription_id = sub
            req.subscriber_discount_pct = discount_pct
            req.is_free_swap = free_swap
            req.priority_sla_level = sla_level

            base_price = req.base_estimated_price
            disc_amt = (base_price * discount_pct / 100.0) if discount_pct else 0.0
            req.discount_amount = disc_amt
            req.final_estimated_price = max(0.0, base_price - disc_amt)
