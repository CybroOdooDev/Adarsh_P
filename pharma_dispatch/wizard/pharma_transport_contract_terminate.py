# -*- coding: utf-8 -*-
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


class PharmaTransportContractTerminate(models.TransientModel):
    _name = 'pharma.transport.contract.terminate'
    _description = 'Terminate Transport Contract'

    contract_ids = fields.Many2many('pharma.transport.contract', 'pharma_tc_terminate_rel',
                                    'wizard_id', 'contract_id', required=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.contract_ids.write({'state': 'terminated', 'termination_reason': self.reason})
        for contract in self.contract_ids:
            contract.message_post(body=self.env._('Contract terminated: %s', self.reason))
        return {'type': 'ir.actions.act_window_close'}
