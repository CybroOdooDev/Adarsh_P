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
import logging
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class WmSubscription(models.Model):
    """Customer recurring billing subscription linked to an operational waste management contract."""
    _name = 'wm.subscription'
    _description = 'Waste Management Customer Subscription'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.audit.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Subscription Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env._('New'),
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True,
        index=True,
    )
    contract_id = fields.Many2one(
        'wm.partner.contract',

        required=True,
        domain="[('partner_id', '=', partner_id)]",
        tracking=True,
        help='The legal and operational contract governing service locations, schedules, and SLAs.'
    )
    plan_id = fields.Many2one(
        'wm.subscription.plan',
        string='Subscription Plan',
        required=True,
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False)

    date_start = fields.Date(string='Start Date', tracking=True)
    next_invoice_date = fields.Date(tracking=True)
    date_end = fields.Date(
        string='End Date',
        compute='_compute_date_end',
        inverse='_inverse_date_end',
        store=True,
        readonly=False,
        tracking=True,
        help='Subscription expiration date, auto-calculated based on billing cycle duration.'
    )
    auto_renew = fields.Boolean(

        default=True,
        help='If true, the subscription automatically renews upon reaching the end date.'
    )

    pause_start_date = fields.Date(readonly=True, copy=False)
    pause_end_date = fields.Date(string='Planned Resume Date', copy=False)
    cancel_reason = fields.Text(string='Cancellation Reason', copy=False)

    currency_id = fields.Many2one(
        'res.currency',

    )
    recurring_price = fields.Monetary(

        currency_field='currency_id',
    )
    company_id = fields.Many2one(
        'res.company',

        required=True,
        default=lambda self: self.env.company,
    )

    # Related read-only projections from Contract (DO NOT DUPLICATE DATA)
    related_sla_id = fields.Many2one(
        'wm.sla',
        related='contract_id.sla_id',
        string='Contract SLA',
        readonly=True,
    )
    related_site_ids = fields.Many2many(
        'wm.collection.point',
        related='contract_id.collection_point_ids',
        string='Covered Sites',
        readonly=True,
    )

    # Benefit Projections from Plan (Stored & Frozen once active)
    extra_pickup_discount = fields.Float(
        string='Extra Pickup Discount (%)',
    )
    included_monthly_weight_kg = fields.Float(
        string='Included Monthly Weight (kg)',
    )
    current_cycle_weight_kg = fields.Float(
        string='Current Cycle Collected Weight (kg)',
        compute='_compute_weight_quota_usage',
        help='Actual total waste weight collected for this subscriber in the current billing cycle.'
    )
    remaining_quota_kg = fields.Float(
        string='Remaining Quota (kg)',
        compute='_compute_weight_quota_usage',
        help='Remaining free weight quota for this subscriber in the current cycle.'
    )
    is_quota_exceeded = fields.Boolean(
        string='Weight Quota Exceeded',
        compute='_compute_weight_quota_usage',
        help='True if current cycle collected weight exceeds the monthly allowance.'
    )
    free_container_swaps_per_year = fields.Integer(
        string='Free Swaps / Year',
    )
    priority_sla_level = fields.Selection([
        ('standard', 'Standard SLA'),
        ('priority_24h', 'Priority 24h Response'),
        ('vip_same_day', 'VIP Same-Day Response'),
    ], string='Priority SLA Level', default='standard')

    used_free_swaps_count = fields.Integer(
        string='Used Free Swaps (Current Year)',
        compute='_compute_used_free_swaps_count',
        readonly=True,
        help='Automated count of approved/completed free container swaps used in the current calendar year.'
    )
    invoice_ids = fields.One2many(
        'account.move',
        'subscription_id',
        string='Invoices',
        readonly=True,
    )
    invoice_count = fields.Integer(

        compute='_compute_invoice_count',
    )

    @api.depends('partner_id', 'date_start', 'date_end', 'included_monthly_weight_kg',
                 'plan_id.allow_rollover_weight')
    def _compute_weight_quota_usage(self):
        """Compute collected weight and check against monthly quota for the current cycle."""
        today = fields.Date.today()
        for sub in self:
            if not sub.partner_id or not sub.date_start:
                sub.current_cycle_weight_kg = 0.0
                sub.remaining_quota_kg = sub.included_monthly_weight_kg
                sub.is_quota_exceeded = False
                continue

            # The quota is monthly: use the month-long window, anchored on
            # the subscription start, that contains today (next_invoice_date
            # moves a whole billing cycle ahead on renewal, which may be a
            # quarter or a year, so it cannot be used).
            cycle_start, cycle_end = sub._get_allowance_period(max(today, sub.date_start))
            if sub.date_end and sub.date_end >= cycle_start:
                cycle_end = min(cycle_end, sub.date_end)

            collected = sub._get_collected_weight(cycle_start, cycle_end)

            sub.current_cycle_weight_kg = collected
            quota = sub._get_period_allowance_kg(cycle_start)
            sub.remaining_quota_kg = max(0.0, quota - collected)
            sub.is_quota_exceeded = bool(quota > 0 and collected > quota)

    def _get_collected_weight(self, date_from, date_to):
        """
        Confirmed weight of the subscriber's completed collections scheduled
        from ``date_from`` to ``date_to``: those of the subscription's
        contract (the only ones its allowance covers), else all of the
        customer's.
        """
        self.ensure_one()
        if not self.partner_id or 'wm.collection.order' not in self.env:
            return 0.0
        scope = ([('contract_id', '=', self.contract_id.id)] if self.contract_id
                 else [('partner_id', '=', self.partner_id.id)])
        orders = self.env['wm.collection.order'].sudo().search(scope + [
            ('state', 'in', ('completed', 'signed')),
            ('scheduled_start', '>=', datetime.combine(date_from, time.min)),
            ('scheduled_start', '<=', datetime.combine(date_to, time.max)),
        ])
        return sum(orders.mapped('confirmed_weight'))

    def _get_rollover_kg(self, period_start):
        """
        Allowance carried into the monthly window starting ``period_start``:
        when the plan allows weight rollover, what the previous window left
        unused of its own monthly allowance. Only one month carries over (a
        window's carried-in weight does not roll on again), so unused
        allowance cannot pile up.
        """
        self.ensure_one()
        quota = self.included_monthly_weight_kg or 0.0
        if not quota or not self.plan_id.allow_rollover_weight or not period_start:
            return 0.0
        previous = self._get_allowance_period(period_start - timedelta(days=1))
        if not previous:
            return 0.0
        return max(quota - self._get_collected_weight(*previous), 0.0)

    def _get_period_allowance_kg(self, period_start):
        """Free weight of the monthly window starting ``period_start``: the monthly allowance plus any rollover."""
        self.ensure_one()
        return (self.included_monthly_weight_kg or 0.0) + self._get_rollover_kg(period_start)

    def _get_allowance_period(self, day):
        """
        The month-long weight allowance window (start, end) containing
        ``day``, anchored on the subscription start date (a subscription
        starting on the 10th has windows from the 10th to the 9th). None
        before the subscription starts.
        """
        self.ensure_one()
        start = self.date_start
        if not start or not day or day < start:
            return None
        months = (day.year - start.year) * 12 + day.month - start.month
        if start + relativedelta(months=months) > day:
            months -= 1
        # Both ends from the start date, so that short months leave no gap
        # between windows (a start on the 31st)
        return (start + relativedelta(months=months),
                start + relativedelta(months=months + 1) - timedelta(days=1))

    @api.depends('date_start', 'plan_id', 'plan_id.billing_cycle')
    def _compute_date_end(self):
        """
        Compute subscription end date based on start date and plan billing cycle duration.
        """
        for sub in self:
            if sub.id and sub.state != 'draft' and sub.date_end:
                # A running subscription keeps its term: editing the plan's
                # billing cycle must not rewrite its end date.
                continue
            if sub.date_start and sub.plan_id:
                cycle = sub.plan_id.billing_cycle or 'monthly'
                step = {
                    'monthly': relativedelta(months=1, days=-1),
                    'quarterly': relativedelta(months=3, days=-1),
                    'annually': relativedelta(years=1, days=-1),
                }.get(cycle, relativedelta(months=1, days=-1))
                sub.date_end = sub.date_start + step
            elif not sub.date_end:
                sub.date_end = False

    def _inverse_date_end(self):
        """
        Reverse compute subscription start date if end date is updated manually.
        """
        if self.env.context.get('wm_skip_date_end_inverse'):
            # Renewal extends the end date only; the start date must stay put.
            return
        for sub in self:
            if sub.date_end and sub.plan_id:
                cycle = sub.plan_id.billing_cycle or 'monthly'
                months = {'monthly': 1, 'quarterly': 3, 'annually': 12}.get(cycle, 1)
                sub.date_start = (sub.date_end + timedelta(days=1)) - relativedelta(months=months)

    @api.onchange('plan_id', 'date_start')
    def _onchange_plan_id(self):
        """
        Copy pricing and benefits from plan_id onto the subscription if in draft state.
        Recalculate date_end based on start date and billing cycle.
        """
        if self.plan_id and (not self.state or self.state == 'draft'):
            self.currency_id = self.plan_id.currency_id
            self.recurring_price = self.plan_id.recurring_price
            self.extra_pickup_discount = self.plan_id.extra_pickup_discount
            self.included_monthly_weight_kg = self.plan_id.included_monthly_weight_kg
            self.free_container_swaps_per_year = self.plan_id.free_container_swaps_per_year
            self.priority_sla_level = self.plan_id.priority_sla_level or 'standard'
            if self.date_start:
                cycle = self.plan_id.billing_cycle or 'monthly'
                step = {
                    'monthly': relativedelta(months=1, days=-1),
                    'quarterly': relativedelta(months=3, days=-1),
                    'annually': relativedelta(years=1, days=-1),
                }.get(cycle, relativedelta(months=1, days=-1))
                self.date_end = self.date_start + step

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        """Compute the total number of customer invoices linked to this subscription."""
        for sub in self:
            invoices = self.env['account.move'].sudo().search([
                ('subscription_id', '=', sub.id)
            ])
            sub.invoice_count = len(invoices)

    def action_view_invoices(self):
        """
        Open customer invoices associated with this subscription.
        """
        self.ensure_one()
        invoices = self.env['account.move'].sudo().search([
            ('subscription_id', '=', self.id)
        ])
        action = {
            'name': self.env._('Subscription Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'context': {
                'default_move_type': 'out_invoice',
                'default_partner_id': self.partner_id.id,
                'default_subscription_id': self.id,
            },
        }
        if len(invoices) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = invoices.id
        else:
            action['view_mode'] = 'list,form'
        return action

    def _count_free_swaps(self, exclude_request=None):
        """Free container swaps already granted this year (pending, approved
        or completed), optionally ignoring one request (the one being priced)."""
        self.ensure_one()
        if not self.partner_id or 'wm.portal.service.request' not in self.env:
            return 0
        year_start = date(fields.Date.today().year, 1, 1)
        year_end = date(fields.Date.today().year, 12, 31)
        effective_start = max(year_start, self.date_start or year_start)
        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('request_type', '=', 'container_swap'),
            ('is_free_swap', '=', True),
            ('state', 'in', ['submitted', 'approved', 'in_progress', 'completed']),
            ('requested_date', '>=', effective_start),
            ('requested_date', '<=', year_end),
        ]
        if exclude_request and exclude_request.id:
            domain.append(('id', '!=', exclude_request.id))
        return self.env['wm.portal.service.request'].sudo().search_count(domain)

    @api.depends('partner_id', 'date_start')
    def _compute_used_free_swaps_count(self):
        """
        Compute total approved or completed free container swap requests for
        the customer in the current calendar year.
        """
        current_year = fields.Date.today().year
        year_start = date(current_year, 1, 1)
        year_end = date(current_year, 12, 31)

        for sub in self:
            if not sub.partner_id or 'wm.portal.service.request' not in self.env:
                sub.used_free_swaps_count = 0
                continue

            sub_start = sub.date_start or year_start
            effective_start = max(year_start, sub_start)

            count = self.env['wm.portal.service.request'].sudo().search_count([
                ('partner_id', '=', sub.partner_id.id),
                ('request_type', '=', 'container_swap'),
                ('is_free_swap', '=', True),
                ('state', 'in', ['approved', 'in_progress', 'completed']),
                ('requested_date', '>=', effective_start),
                ('requested_date', '<=', year_end),
            ])
            sub.used_free_swaps_count = count

    @api.constrains('partner_id', 'contract_id')
    def _check_contract_partner(self):
        """Constraint: contract must belong to the selected customer."""
        for sub in self:
            if sub.contract_id and sub.partner_id and sub.contract_id.partner_id != sub.partner_id:
                raise ValidationError(self.env._("Contract '%(contract)s' does not belong to customer '%(customer)s'.", contract=sub.contract_id.name, customer=sub.partner_id.name))

    @api.constrains('contract_id', 'state')
    def _check_single_live_subscription(self):
        """A contract can have only one active or paused subscription at a time."""
        for sub in self.filtered(lambda s: s.contract_id and s.state in ('active', 'paused')):
            other = self.search_count([
                ('contract_id', '=', sub.contract_id.id),
                ('state', 'in', ('active', 'paused')),
                ('id', '!=', sub.id),
            ])
            if other:
                raise ValidationError(self.env._("Contract '%s' already has an active or paused subscription.", sub.contract_id.name))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        """Constraint: end date cannot be before start date."""
        for sub in self:
            if sub.date_start and sub.date_end and sub.date_end < sub.date_start:
                raise ValidationError(self.env._("Subscription End Date cannot be earlier than Start Date."))

    @api.constrains('pause_start_date', 'pause_end_date')
    def _check_pause_dates(self):
        """Constraint: pause end date cannot be before pause start date."""
        for sub in self:
            if sub.pause_start_date and sub.pause_end_date and sub.pause_end_date < sub.pause_start_date:
                raise ValidationError(self.env._("Planned Resume Date cannot be earlier than Pause Start Date."))

    @api.model_create_multi
    def create(self, vals_list):
        """Assign sequence number and populate plan default values on creation."""
        for vals in vals_list:
            if vals.get('name', self.env._('New')) == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.subscription') or self.env._('New')
            if vals.get('plan_id'):
                plan = self.env['wm.subscription.plan'].browse(vals['plan_id'])
                if plan.exists():
                    vals.setdefault('currency_id', plan.currency_id.id)
                    vals.setdefault('recurring_price', plan.recurring_price)
                    vals.setdefault('extra_pickup_discount', plan.extra_pickup_discount)
                    vals.setdefault('included_monthly_weight_kg', plan.included_monthly_weight_kg)
                    vals.setdefault('free_container_swaps_per_year', plan.free_container_swaps_per_year)
                    vals.setdefault('priority_sla_level', plan.priority_sla_level or 'standard')
        return super().create(vals_list)

    def _generate_term_invoices(self, term_start, term_end):
        """
        Create one draft invoice per billing cycle between term_start and
        term_end for this subscription's recurring fee. Skips any cycle date
        that already has a non-cancelled invoice, so this is safe to call
        repeatedly for the same term without creating duplicates.
        Returns (invoices_created_or_found, next_term_start_date).
        """
        self.ensure_one()
        cycle = self.plan_id.billing_cycle if self.plan_id else 'monthly'
        step = {'monthly': relativedelta(months=1),
                'quarterly': relativedelta(months=3),
                'annually': relativedelta(years=1)}.get(cycle, relativedelta(months=1))

        cycle_dates = []
        curr_date = term_start
        while curr_date <= term_end:
            cycle_dates.append(curr_date)
            curr_date += step
        if not cycle_dates:
            cycle_dates = [term_start]

        invoices = self.env['account.move']
        for i, inv_date in enumerate(cycle_dates, 1):
            existing = self.env['account.move'].sudo().search([
                ('subscription_id', '=', self.id),
                ('invoice_date', '=', inv_date),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if existing:
                invoices |= existing
                continue
            if self.recurring_price <= 0:
                continue
            with (self.company_id or self.env.company)._wm_invoicing_guard():
                invoice = self.env['account.move'].sudo().create({
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_id.id,
                    'company_id': self.company_id.id,
                    'invoice_date': inv_date,
                    'invoice_date_due': inv_date,
                    'currency_id': (self.currency_id or self.company_id.currency_id).id,
                    'ref': self.env._("%(name)s - Cycle %(cycle)d/%(total)d", name=self.name, cycle=i, total=len(cycle_dates)),
                    'subscription_id': self.id,
                    'invoice_line_ids': [(0, 0, {
                        'name': self.env._("Subscription Recurring Fee — %(plan)s (%(name)s) [Cycle %(cycle)d/%(total)d]", plan=self.plan_id.name, name=self.name, cycle=i, total=len(cycle_dates)),
                        'quantity': 1.0,
                        'price_unit': self.recurring_price,
                    })],
                })
            invoices |= invoice

        return invoices, term_end + relativedelta(days=1)

    def _check_subscription_manager(self):
        """
        Activating, renewing and cancelling create or cancel customer invoices
        (as superuser): reserve them to contract managers and WM admins.
        System calls (crons, sudo flows such as portal holds) are allowed.
        """
        if self.env.su:
            return
        user = self.env.user
        if not (user.has_group('wm_contracts_billing.group_wm_contract_manager')
                or user.has_group('wm_base.group_wm_admin')):
            raise AccessError(self.env._("Only Contract Managers can activate, renew or cancel subscriptions."))

    def action_activate(self):
        """
        Activate subscription against a valid signed/confirmed/ongoing contract
        and pre-generate recurring cycle invoices for the subscription term.
        """
        self._check_subscription_manager()
        for sub in self:
            # Re-activating a cancelled/expired subscription would back-date
            # a whole new term of invoices
            if sub.state != 'draft':
                raise UserError(self.env._("Only draft subscriptions can be activated (%(sub_name)s is %(state)s).", sub_name=sub.name, state=sub.state))
            if not sub.partner_id:
                raise ValidationError(self.env._("Customer is required to activate a subscription."))
            if not sub.contract_id:
                raise ValidationError(self.env._("Contract is required to activate a subscription."))
            if not sub.plan_id:
                raise ValidationError(self.env._("Subscription Plan is required to activate a subscription."))

            if sub.contract_id.partner_id != sub.partner_id:
                raise ValidationError(self.env._("Selected contract %(contract)s does not belong to customer %(customer)s.", contract=sub.contract_id.name, customer=sub.partner_id.name))

            valid_states = ('signed', 'confirmed', 'ongoing')
            if sub.contract_id.state not in valid_states:
                raise ValidationError(self.env._("Cannot activate subscription %(sub_name)s: Linked contract %(contract)s is in state '%(state)s'. "
                    "Subscriptions can only be activated for signed, confirmed, or ongoing contracts.", sub_name=sub.name, contract=sub.contract_id.name, state=sub.contract_id.state))

            today = fields.Date.today()
            start = sub.date_start or today
            if sub.date_end:
                end = sub.date_end
            else:
                cycle = sub.plan_id.billing_cycle if sub.plan_id else 'monthly'
                step = {
                    'monthly': relativedelta(months=1, days=-1),
                    'quarterly': relativedelta(months=3, days=-1),
                    'annually': relativedelta(years=1, days=-1),
                }.get(cycle, relativedelta(months=1, days=-1))
                end = start + step

            invoices, next_term_start = sub._generate_term_invoices(start, end)

            sub.write({
                'state': 'active',
                'date_start': start,
                'date_end': end,
                'next_invoice_date': next_term_start,
                'pause_start_date': False,
                'pause_end_date': False,
            })
            sub.message_post(body=self.env._("Subscription activated under contract %(contract)s. Generated %(invoices)d invoice(s) for term %(start)s to %(end)s.", contract=sub.contract_id.name, invoices=len(invoices), start=start, end=end))

    def action_pause(self, resume_date=None):
        """
        Pause an active subscription.
        """
        for sub in self:
            if sub.state != 'active':
                raise UserError(self.env._("Only active subscriptions can be paused."))

            today = fields.Date.today()
            end_d = resume_date or sub.pause_end_date or False
            sub.write({
                'state': 'paused',
                'pause_start_date': today,
                'pause_end_date': end_d,
            })
            sub.message_post(body=self.env._("Subscription paused. Resume date: %s", end_d or self.env._('Not specified')))

    def action_resume(self):
        """
        Resume a paused subscription back to active state.
        """
        for sub in self:
            if sub.state != 'paused':
                raise UserError(self.env._("Only paused subscriptions can be resumed."))

            today = fields.Date.today()
            sub.write({
                'state': 'active',
                'pause_start_date': False,
                'pause_end_date': False,
            })
            if sub.next_invoice_date and sub.next_invoice_date < today:
                # Align next billing date to today if it fell during pause
                sub.next_invoice_date = today
            sub.message_post(body=self.env._("Subscription resumed to active status."))

    def action_cancel(self, reason=None):
        """
        Cancel an active, paused, or draft subscription.
        Automatically cancels any remaining unposted DRAFT invoices pre-generated for future cycles.
        If any draft invoices cannot be cancelled, posts a chatter warning and displays a UI notification.
        """
        self._check_subscription_manager()
        failed_invoices_all = self.env['account.move']
        for sub in self:
            if sub.state not in ('active', 'paused', 'draft'):
                raise UserError(self.env._("Only active, paused, or draft subscriptions can be cancelled."))

            r_text = reason or sub.cancel_reason or self.env._("Cancelled by user/system")

            draft_invoices = self.env['account.move'].sudo().search([
                ('subscription_id', '=', sub.id),
                ('state', '=', 'draft'),
            ])
            today = fields.Date.context_today(sub)
            future_draft_invoices = draft_invoices.filtered(
                lambda inv: not inv.invoice_date or inv.invoice_date >= today
            )
            past_draft_invoices = draft_invoices - future_draft_invoices
            failed_invoices = self.env['account.move']
            cancelled_count = 0

            if future_draft_invoices:
                try:
                    future_draft_invoices.button_cancel()
                    remaining = future_draft_invoices.filtered(lambda inv: inv.state == 'draft')
                    cancelled_count = len(future_draft_invoices) - len(remaining)
                    failed_invoices = remaining
                except Exception as e:
                    _logger.warning("Could not auto-cancel draft invoices for sub %s: %s", sub.name, e)
                    remaining = future_draft_invoices.filtered(lambda inv: inv.state == 'draft')
                    cancelled_count = len(future_draft_invoices) - len(remaining)
                    failed_invoices = remaining or future_draft_invoices

            failed_invoices_all |= failed_invoices

            sub.write({
                'state': 'cancelled',
                'cancel_reason': r_text,
            })

            msg = self.env._("Subscription cancelled. Reason: %s.", r_text)
            if cancelled_count:
                msg += self.env._(" Automatically cancelled %d unposted draft invoice(s) for future cycles.", cancelled_count)
            if past_draft_invoices:
                past_names = ", ".join(past_draft_invoices.mapped(lambda i: i.name or str(i.id)))
                msg += self.env._("\nNOTE: %(count)d past-cycle unposted draft invoice(s) (%(invoices)s) were preserved for accounting review.", count=len(past_draft_invoices), invoices=past_names)
            if failed_invoices:
                failed_names = ", ".join(failed_invoices.mapped(lambda i: i.name or str(i.id)))
                msg += self.env._("\nWARNING: %(failed_invoices)d draft invoice(s) (%(failed_names)s) could not be cancelled automatically. Please review and cancel them manually.", failed_invoices=len(failed_invoices), failed_names=failed_names)
            sub.message_post(body=msg)

        if failed_invoices_all:
            failed_names = ", ".join(failed_invoices_all.mapped(lambda i: i.name or str(i.id)))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': self.env._('Subscription Cancelled with Warning'),
                    'message': self.env._('Subscription cancelled, but draft invoice(s) %s could not be auto-cancelled. Please check chatter for details.', failed_names),
                    'type': 'warning',
                    'sticky': True,
                }
            }
        return True

    def action_renew(self):
        """
        Renew an active subscription for ONE more billing cycle (monthly:
        1 month, quarterly: 3 months, annually: 1 year — the same step used
        at activation) and generate that cycle's recurring invoice.

        The manual Renew button is an explicit user action and works even
        when auto_renew is disabled; only the cron restricts itself to
        auto_renew subscriptions (see _cron_process_subscriptions).
        """
        self._check_subscription_manager()
        today = fields.Date.today()
        for sub in self:
            # Serialize concurrent renewals (cron + manual click): wait for the
            # row lock, then re-read so the second caller sees the new term.
            self.env.cr.execute("SELECT id FROM wm_subscription WHERE id = %s FOR UPDATE", [sub.id])
            sub.invalidate_recordset(['state', 'next_invoice_date', 'date_end'])
            # Renewing bills a new cycle: only for active subscriptions whose
            # current cycle is actually due (the cron applies the same filter).
            if sub.state != 'active':
                raise UserError(self.env._("Only active subscriptions can be renewed (%(sub_name)s is %(state)s).", sub_name=sub.name, state=sub.state))
            if sub.next_invoice_date and sub.next_invoice_date > today:
                raise UserError(self.env._("Subscription %(sub_name)s is not due for renewal yet: the next term starts on %(next_invoice_date)s.", sub_name=sub.name, next_invoice_date=sub.next_invoice_date))
            valid_contract_states = ('signed', 'confirmed', 'ongoing')
            if sub.contract_id and sub.contract_id.state not in valid_contract_states:
                _logger.warning(
                    "Cannot renew subscription %s: Linked contract %s is in state '%s'.",
                    sub.name, sub.contract_id.name, sub.contract_id.state
                )
                sub.message_post(body=self.env._("Renewal skipped: Linked contract %(contract)s is in state '%(state)s'.", contract=sub.contract_id.name, state=sub.contract_id.state))
                continue

            new_start = sub.next_invoice_date or fields.Date.today()
            cycle = sub.plan_id.billing_cycle if sub.plan_id else 'monthly'
            step = {
                'monthly': relativedelta(months=1, days=-1),
                'quarterly': relativedelta(months=3, days=-1),
                'annually': relativedelta(years=1, days=-1),
            }.get(cycle, relativedelta(months=1, days=-1))
            new_end = new_start + step

            invoices, next_term_start = sub._generate_term_invoices(new_start, new_end)

            sub.with_context(wm_skip_date_end_inverse=True).write({
                'date_end': new_end,
                'next_invoice_date': next_term_start,
            })
            sub.message_post(body=self.env._("Subscription renewed. Generated %(invoices)d invoice(s) for term %(new_start)s to %(new_end)s.", invoices=len(invoices), new_start=new_start, new_end=new_end))

    @api.model
    def _cron_process_subscriptions(self):
        """
        Cron job to process subscription expirations and renew active subscriptions due for next term batch.
        """
        today = fields.Date.today()

        expiring_subs = self.search([
            ('state', 'in', ['active', 'paused']),
            ('date_end', '!=', False), ('date_end', '<', today),
            '|', ('auto_renew', '=', False), ('contract_id.state', 'in', ['cancelled', 'expired']),
        ])
        for sub in expiring_subs:
            sub.write({'state': 'expired'})
            sub.message_post(body=self.env._("Subscription expired on end date %s.", sub.date_end))

        # Subscriptions paused until a planned date (e.g. by a service-hold
        # request) resume on that date and are billed again from then on.
        resuming_subs = self.search([
            ('state', '=', 'paused'),
            ('pause_end_date', '!=', False), ('pause_end_date', '<=', today),
        ])
        for sub in resuming_subs:
            try:
                with self.env.cr.savepoint():
                    sub.action_resume()
            except Exception as e:
                _logger.error("Error resuming subscription %s: %s", sub.name, e, exc_info=True)
                sub.message_post(body=self.env._("ERROR resuming the subscription: %s", e))

        due_subs = self.search([
            ('state', '=', 'active'), ('auto_renew', '=', True),
            ('next_invoice_date', '<=', today),
        ])
        for sub in due_subs:
            try:
                # Savepoint: a failing renewal must not leave half-created
                # invoices behind nor abort the other subscriptions.
                with self.env.cr.savepoint():
                    sub.action_renew()
            except Exception as e:
                _logger.error("Error renewing subscription %s: %s", sub.name, e, exc_info=True)
                sub.message_post(body=self.env._("ERROR generating next term invoices: %s", e))
