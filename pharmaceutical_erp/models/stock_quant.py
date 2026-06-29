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

from odoo import fields,models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class StockQuant(models.Model):
    """Extends stock.quant to support GMP Quarantine Queue operations."""
    _inherit = 'stock.quant'

    has_incoming_qc = fields.Boolean(
        string='Has Incoming QC',
        compute='_compute_has_incoming_qc',
    )

    def _compute_has_incoming_qc(self):
        for quant in self:
            if not quant.lot_id:
                quant.has_incoming_qc = False
                continue
            
            existing = self.env['pharma.qc.test.order'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('stage', '=', 'incoming')
            ], limit=1)
            quant.has_incoming_qc = bool(existing)




    def action_quant_create_qc_test(self):
        """
        Creates QC Test Orders for the selected quant lots.
        """
        created_count = 0
        for quant in self:
            lot = quant.lot_id
            if not lot:
                continue
            existing_order = self.env['pharma.qc.test.order'].search([
                ('lot_id', '=', lot.id),
                ('stage', '=', 'incoming')
            ], limit=1)
            
            if existing_order:
                continue
                
            product_tmpl = quant.product_id.product_tmpl_id
            self.env['pharma.qc.test.order'].create({
                'product_id': product_tmpl.id,
                'lot_id': lot.id,
                'stage': 'incoming'
            })
            created_count += 1
            
        if created_count == 0:
            raise UserError(_('No QC Test Orders were created. They may already exist or lack a lot/batch.'))
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('QC Test Orders Created'),
                'message': _('Successfully created %d QC Test Order(s).') % created_count,
                'sticky': False,
                'type': 'success',
            }
        }

    def action_quant_open_lot(self):
        """Open the lot / batch record for full details and disposition."""
        self.ensure_one()
        if not self.lot_id:
            raise UserError(_('No lot/batch linked to this record.'))
        return {
            'name': _('Lot / Batch'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot',
            'view_mode': 'form',
            'res_id': self.lot_id.id,
            'target': 'current',
        }
