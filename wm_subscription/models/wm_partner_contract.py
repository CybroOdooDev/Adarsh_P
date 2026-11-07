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


class WmPartnerContract(models.Model):
    """Extends Partner Contract with linked subscription tracking."""
    _inherit = 'wm.partner.contract'

    subscription_ids = fields.One2many(
        'wm.subscription',
        'contract_id',
        string='Subscriptions'
    )
    subscription_count = fields.Integer(

        compute='_compute_subscription_count'
    )

    @api.depends('subscription_ids')
    def _compute_subscription_count(self):
        """Compute total subscriptions linked to this contract."""
        for contract in self:
            contract.subscription_count = len(contract.subscription_ids)

    def action_view_subscriptions(self):
        """Open customer subscriptions linked to this contract."""
        self.ensure_one()
        action = {
            'name': self.env._('Linked Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'wm.subscription',
            'domain': [('contract_id', '=', self.id)],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_contract_id': self.id,
            },
        }
        subscriptions = self.subscription_ids
        if len(subscriptions) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = subscriptions.id
        else:
            action['view_mode'] = 'list,form'
        return action
