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
from odoo.exceptions import ValidationError


class WmSubscriptionPlan(models.Model):
    """Reusable catalog of recurring subscription plans/tiers for waste management customers."""
    _name = 'wm.subscription.plan'
    _description = 'Waste Management Subscription Plan'
    _order = 'name asc'

    name = fields.Char(string='Plan Name', required=True)
    code = fields.Char(required=True, copy=False)
    recurring_price = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',

        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    billing_cycle = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    ], required=True, default='monthly')
    description = fields.Text()
    subscription_ids = fields.One2many('wm.subscription', 'plan_id', string='Subscriptions')
    active = fields.Boolean(default=True)

    # Subscriber Benefit Rules
    extra_pickup_discount = fields.Float(
        string='Extra Pickup Discount (%)',
        default=0.0,
        help='Percentage discount applied on on-demand extra pickup requests for subscribers.'
    )
    included_monthly_weight_kg = fields.Float(
        string='Included Monthly Weight (kg)',
        default=0.0,
        help='Free monthly waste collection weight quota included in this plan.'
    )
    free_container_swaps_per_year = fields.Integer(
        string='Free Container Swaps / Year',
        default=0,
        help='Number of free container swap/resize requests allowed per calendar year.'
    )
    priority_sla_level = fields.Selection([
        ('standard', 'Standard SLA'),
        ('priority_24h', 'Priority 24h Response'),
        ('vip_same_day', 'VIP Same-Day Response'),
    ], string='Priority SLA Response', default='standard', help='Service SLA prioritization level for plan subscribers.')
    allow_rollover_weight = fields.Boolean(
        string='Allow Weight Rollover',
        default=False,
        help='Unused included weight of a month is added to the next month\'s allowance '
             '(one month only: weight carried in does not roll over again).'
    )

    _code_uniq = models.Constraint(
        'unique(code)',
        'The subscription plan code must be unique!'
    )

    @api.constrains('recurring_price', 'extra_pickup_discount', 'included_monthly_weight_kg',
                    'free_container_swaps_per_year')
    def _check_plan_values(self):
        """Plan prices, quotas and discounts must be within sensible ranges."""
        for plan in self:
            if plan.recurring_price < 0:
                raise ValidationError(self.env._("The recurring price cannot be negative."))
            if not 0.0 <= plan.extra_pickup_discount <= 100.0:
                raise ValidationError(self.env._("The extra pickup discount must be between 0 and 100%."))
            if plan.included_monthly_weight_kg < 0:
                raise ValidationError(self.env._("The included monthly weight cannot be negative."))
            if plan.free_container_swaps_per_year < 0:
                raise ValidationError(self.env._("The number of free container swaps cannot be negative."))

    def write(self, vals):
        """
        When subscription plan rates or benefits are updated, propagate changes
        ONLY to draft subscriptions. Active or paused subscription rates remain locked.
        """
        res = super().write(vals)
        benefit_fields = {
            'currency_id', 'recurring_price', 'extra_pickup_discount',
            'included_monthly_weight_kg', 'free_container_swaps_per_year', 'priority_sla_level'
        }
        if any(f in vals for f in benefit_fields):
            for plan in self:
                draft_subs = self.env['wm.subscription'].sudo().search([
                    ('plan_id', '=', plan.id),
                    ('state', '=', 'draft'),
                ])
                if draft_subs:
                    sub_vals = {}
                    if 'currency_id' in vals:
                        sub_vals['currency_id'] = plan.currency_id.id
                    if 'recurring_price' in vals:
                        sub_vals['recurring_price'] = plan.recurring_price
                    if 'extra_pickup_discount' in vals:
                        sub_vals['extra_pickup_discount'] = plan.extra_pickup_discount
                    if 'included_monthly_weight_kg' in vals:
                        sub_vals['included_monthly_weight_kg'] = plan.included_monthly_weight_kg
                    if 'free_container_swaps_per_year' in vals:
                        sub_vals['free_container_swaps_per_year'] = plan.free_container_swaps_per_year
                    if 'priority_sla_level' in vals:
                        sub_vals['priority_sla_level'] = plan.priority_sla_level or 'standard'
                    if sub_vals:
                        draft_subs.write(sub_vals)
        return res
