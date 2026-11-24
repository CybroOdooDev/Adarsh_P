# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is under the terms of the Odoo Proprietary License v1.0
#    (OPL-1) It is forbidden to publish, distribute, sublicense, or
#    sell copies of the Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
#    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
#    OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
#    THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#############################################################################
from odoo import fields, models


class ResPartner(models.Model):
    """Route area of a customer and its delivery order in that area."""
    _inherit = 'res.partner'

    location_id = fields.Many2one(
        'route.line', index='btree_not_null',
        domain="[('company_id', 'in', [False, current_company_id])]",
        help="Area of the delivery route where the customer is delivered.")
    sequence = fields.Integer(
        default=10, help="Delivery order of the customer in its route area.")

    def get_all_dues(self, company_id=None):
        """What the customer and its direct contacts still owe in the given
        company (the current one by default): the open items of their
        receivable account, grouped by journal entry, oldest first.

        These are unpaid invoices (positive), open credit notes and payments
        not yet matched to an invoice (negative). Vendor bills are on the
        payable account and are not included.

        :return: list of dicts with the keys ``name``, ``invoice_date_due``
            and ``amount_residual_signed`` (open amount in company currency)
        """
        self.ensure_one()
        partners = self | self.with_context(active_test=False).child_ids
        # The route reports list the dues of every customer of a route, also
        # for route users without access to accounting.
        lines = self.env['account.move.line'].sudo().search([
            ('move_id.partner_id', 'in', partners.ids),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0),
            ('company_id', '=', company_id or self.env.company.id),
        ])
        dues = []
        for move, move_lines in sorted(lines.grouped('move_id').items(),
                                       key=lambda item: (item[0].create_date, item[0].id)):
            due_dates = [date for date in move_lines.mapped('date_maturity') if date]
            dues.append({
                'name': move.name,
                'invoice_date_due': move.invoice_date_due or min(due_dates, default=False),
                'amount_residual_signed': sum(move_lines.mapped('amount_residual')),
            })
        return dues
