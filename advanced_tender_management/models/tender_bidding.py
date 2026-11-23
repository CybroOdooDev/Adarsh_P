# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
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
#    If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from odoo import api, fields, models
from odoo.exceptions import UserError


class TenderBidding(models.Model):
    """Bid of a vendor for a tender."""
    _name = "tender.bidding"
    _inherit = 'mail.thread'
    _description = 'Tender Bidding'

    name = fields.Char(string="Bidding Reference", help='Bidding Reference', readonly=True,
                       copy=False)
    vendor_id = fields.Many2one('res.partner', help="Vendor who submitted the bid.")
    tender_id = fields.Many2one('tender.management', help="Tender of the bid.",
                                index=True)
    bidding_state = fields.Selection(
        [('pre_qualification', 'Pre Qualification'), ('bid', 'Bid'), ('bid_close', 'Bid Close'),
         ('won', 'Won'), ('lost', 'Lost')],
        default='pre_qualification', help="Stage of the bid.", tracking=True, readonly=True,
        copy=False)
    tender_state = fields.Selection(related='tender_id.tender_state',
                                    help="Stage of the tender of the bid.")
    bidding_date = fields.Date(string="Date", help="Date the bid was submitted.")
    vendor_attachments_ids = fields.Many2many('ir.attachment', string='Attachments',
                                              help='Documents attached by the vendor.')
    tender_bid_products_ids = fields.One2many('tender.bidding.product.lines', 'tender_bidding_id',
                                              help='Prices offered for the tender lines.')
    total_bidding_amount = fields.Float(string="Total Amount", help="Total of the bid.",
                                        compute="_compute_total_bidding_amount", store=True)
    qualification_stage = fields.Selection(
        [('initial', 'Initial'), ('qualified', 'Qualified'), ('disqualified', 'Disqualified')],
        help="Whether the bid is qualified for selection.", default='initial', tracking=True)
    legit_bid = fields.Boolean(help="Every product of the bid has a price.",
                               compute="_compute_legit_bid", store=True)
    edit_request = fields.Boolean(string="Edit Requested", default=False,
                                  help='The vendor asked to edit the bid.')
    vendor_rank = fields.Integer(help="Rank of the vendor among the qualified bids.",
                                 compute="_compute_vendor_rank", store=True)

    @api.depends('tender_id', 'total_bidding_amount', 'qualification_stage')
    def _compute_vendor_rank(self):
        """Rank the qualified bids of a tender by total amount, lowest first."""
        for rec in self:
            rec.vendor_rank = 0
            if rec.qualification_stage == 'qualified' and rec.tender_id:
                ranked = self.search(
                    [('tender_id', '=', rec.tender_id.id), ('qualification_stage', '=', 'qualified')],
                    order='total_bidding_amount asc, id asc')
                if rec.id in ranked.ids:
                    rec.vendor_rank = ranked.ids.index(rec.id) + 1

    @api.depends('tender_bid_products_ids.product_total')
    def _compute_total_bidding_amount(self):
        """Sum the line totals of the bid."""
        for rec in self:
            rec.total_bidding_amount = sum(rec.tender_bid_products_ids.mapped('product_total'))

    @api.depends('tender_bid_products_ids.product_price', 'tender_bid_products_ids.display_type')
    def _compute_legit_bid(self):
        """A bid is legit when every product line has a price."""
        for rec in self:
            prices = rec.tender_bid_products_ids.filtered(
                lambda line: not line.display_type).mapped('product_price')
            rec.legit_bid = not any(price == 0 for price in prices)

    def _recompute_tender_ranks(self, tenders):
        """Rank again every bid of the given tenders."""
        if tenders:
            self.search([('tender_id', 'in', tenders.ids)])._compute_vendor_rank()

    @api.model_create_multi
    def create(self, vals_list):
        """Give the bid a reference and rank the bids of its tender again."""
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('tender.bidding')
        bids = super().create(vals_list)
        self._recompute_tender_ranks(bids.tender_id)
        return bids

    def write(self, vals):
        """Rank the bids again when the amount, stage or tender changes."""
        tenders = self.tender_id
        res = super().write(vals)
        if {'total_bidding_amount', 'qualification_stage', 'tender_id',
                'tender_bid_products_ids'} & set(vals):
            self._recompute_tender_ranks(tenders | self.tender_id)
        return res

    def _can_request_edit(self):
        """A submitted bid can be reopened while its tender takes bids."""
        self.ensure_one()
        return self.tender_state == 'bid_submission' and self.bidding_state == 'bid_close'

    def action_approve_edit_request(self):
        """Let the vendor edit the bid again."""
        template = self.env.ref('advanced_tender_management.edit_request_approved_template')
        for rec in self:
            if not rec.edit_request or not rec._can_request_edit():
                raise UserError(self.env._(
                    'Edit requests of %s can only be approved while its tender takes bids.',
                    rec.name))
            rec.write({'bidding_state': 'bid', 'edit_request': False})
            template.send_mail(rec.id, force_send=True)

    def _set_qualification(self, stage, template_xmlid):
        """Record the qualification decision and tell the vendor when it
        changes. Bids are evaluated after bidding closes and before the
        tender is decided."""
        template = self.env.ref(template_xmlid)
        for rec in self:
            if rec.tender_state not in ('bid_evaluation', 'bid_selection') \
                    or rec.bidding_state in ('won', 'lost'):
                raise UserError(self.env._(
                    'Bids can only be qualified or disqualified while their tender is in '
                    'Bid Evaluation or Bid Selection, and before they are won or lost.'))
            if rec.qualification_stage != stage:
                rec.qualification_stage = stage
                template.send_mail(rec.id, force_send=True)

    def action_qualify(self):
        """Qualify the bid for selection."""
        self._set_qualification('qualified', 'advanced_tender_management.bidding_qualified_template')

    def action_disqualify(self):
        """Exclude the bid from selection."""
        self._set_qualification('disqualified', 'advanced_tender_management.bidding_disqualified_template')
