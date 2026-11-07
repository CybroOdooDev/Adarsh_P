#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    """Extends Customer Invoice with waste management monthly billing run linkage."""
    _inherit = 'account.move'

    billing_run_id = fields.Many2one(
        'wm.monthly.billing.run',
        string='Monthly Billing Run',
        readonly=True,
        ondelete='set null',
        copy=False,
        help="The monthly billing run that generated this consolidated invoice.",
    )
    wm_billing_released = fields.Boolean(
        string='Billing Released',
        readonly=True,
        copy=False,
        help="Cancelling this invoice released its collection orders and events "
             "so they can be billed again; it can no longer be reset to draft.",
    )

    def button_cancel(self):
        """Cancelling an invoice releases what it had billed, so the orders and
        events are not left marked as billed with no invoice behind them."""
        res = super().button_cancel()
        self._release_billing_links()
        return res

    def button_draft(self):
        """A cancelled invoice whose orders and events were released may
        already be billed again: reposting it would bill them twice."""
        released = self.filtered(lambda move: move.state == 'cancel' and move.wm_billing_released)
        if released:
            raise UserError(self.env._(
                "Invoice %(names)s released its collection orders and billable events for "
                "re-billing when it was cancelled, so it cannot be reset to draft. "
                "Bill them again through a new invoice instead.",
                names=', '.join(released.mapped('display_name')),
            ))
        return super().button_draft()

    def unlink(self):
        """Deleting a draft invoice also releases what it had billed."""
        self._release_billing_links(self)
        return super().unlink()

    def _release_billing_links(self, moves=None):
        """Free the collection orders (monthly billing run or direct invoice)
        and the ad-hoc billable events whose invoice has been cancelled or
        deleted.

        :param moves: invoices to release regardless of their state (used on
            deletion); by default only the cancelled invoices of ``self``.
        """
        cancelled = moves if moves is not None else self.filtered(lambda move: move.state == 'cancel')
        if not cancelled:
            return
        released = self.env['account.move']
        run_lines = self.env['wm.monthly.billing.run.line'].sudo().search([
            ('invoice_id', 'in', cancelled.ids), ('state', '=', 'billed')])
        if run_lines:
            released |= run_lines.invoice_id
            run_lines.collection_order_ids.write({'billing_run_line_id': False})
            run_lines.write({
                'state': 'draft',
                'note': self.env._("Invoice cancelled: the orders were released and can be billed again."),
            })
        direct_orders = self.env['wm.collection.order'].sudo().search([
            ('direct_invoice_id', 'in', cancelled.ids)])
        if direct_orders:
            released |= direct_orders.direct_invoice_id
            direct_orders.write({'direct_invoice_id': False})
        if 'wm.billable.event' in self.env:
            events = self.env['wm.billable.event'].sudo().search([
                ('invoice_id', 'in', cancelled.ids), ('state', '=', 'invoiced')])
            if events:
                released |= events.invoice_id
                events.write({'state': 'confirmed', 'invoice_id': False, 'invoice_line_id': False})
        released = released.sudo().exists().filtered(lambda move: move.state == 'cancel')
        if released:
            released.write({'wm_billing_released': True})
