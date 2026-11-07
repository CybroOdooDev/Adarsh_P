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
from odoo import api, fields, models
from odoo.exceptions import UserError


class WmPartnerContractLine(models.Model):
    """Contracted waste category rate line specifying collection basis and price per kg."""
    _name = 'wm.partner.contract.line'
    _description = 'Waste Management Contract Line'

    category_id = fields.Many2one(
        'wm.waste.category',
        required=True,
    )
    contract_id = fields.Many2one('wm.partner.contract', required=True)
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
        domain="[('is_waste_material', '=', True), ('wm_waste_category_id', '=', category_id)]",
    )
    contract_currency_id = fields.Many2one(
        related='contract_id.currency_id', string='Currency'
    )
    price = fields.Float(
        string='Rate per kg',
        digits='WM Rate',
        help="Price per kg for this waste category. Only used when the "
             "contract's Billing is 'Per Category Rate'."
    )

    @api.model_create_multi
    def create(self, vals_list):
        # A new rate on a confirmed contract changes its agreed prices as much
        # as editing one (the contract form path is guarded in its write()).
        if not self.env.su:
            contracts = self.env['wm.partner.contract'].browse(
                {vals['contract_id'] for vals in vals_list if vals.get('contract_id')})
            locked = contracts.filtered(lambda c: c.state in c._PRICE_LOCKED_STATES)
            if locked:
                raise UserError(self.env._("Rates cannot be added to contract '%s' once it is confirmed or ongoing.", locked[0].name))
        return super().create(vals_list)

    def write(self, vals):
        # The override context only counts under sudo(): RPC clients can send any context key.
        if 'price' in vals and not self.env.su:
            locked = self.filtered(lambda line: line.contract_id.state in ('confirmed', 'ongoing'))
            if locked:
                raise UserError(self.env._("The rates of contract '%s' cannot be changed once it is confirmed or ongoing.", locked[0].contract_id.name))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_locked_contract(self):
        if not self.env.su:
            for line in self:
                if line.contract_id.state in ('confirmed', 'ongoing'):
                    raise UserError(self.env._("Lines cannot be deleted from contract '%s' because it is confirmed or ongoing.", line.contract_id.name))
