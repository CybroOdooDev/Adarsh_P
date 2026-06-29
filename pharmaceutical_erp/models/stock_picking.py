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

from odoo import models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class StockPicking(models.Model):
    """Extends stock.picking to enforce GMP lot quarantine on goods receipt."""
    _inherit = 'stock.picking'

    def _action_done(self):
        """
        After the picking is fully validated, force lot_status = 'quarantine'
        on every lot received via an incoming shipment.

        Idempotent: lots already set to approved / rejected / on_hold / recalled
        are never overwritten — only lots with no status or those still in
        quarantine are touched.
        """
        # GMP: block non-incoming moves that consume quarantined / rejected lots
        for picking in self:
            if picking.picking_type_id.code != 'incoming':
                self._check_pharma_lot_status(picking)

        result = super()._action_done()

        for picking in self:
            if picking.picking_type_id.code == 'incoming':
                lines = self.env['stock.move.line'].search([('picking_id', '=', picking.id), ('state', '=', 'done')])
                lots = lines.mapped('lot_id')
                lots_to_quarantine = lots.filtered(
                    lambda l: not l.lot_status or l.lot_status == 'quarantine'
                )
                if lots_to_quarantine:
                    lots_to_quarantine.write({'lot_status': 'quarantine'})
                    msg = _('GMP: %d lot(s) automatically set to Quarantine on receipt validation.') % len(lots_to_quarantine)
                    picking.message_post(body=msg)
        return result

    @staticmethod
    def _check_pharma_lot_status(picking):
        """
        Raise UserError if any move line in the picking uses a lot whose
        pharma status is not 'approved' or 'released'.

        Lots in quarantine, rejected, on_hold, or recalled are blocked from
        being consumed in production or dispatched to customers, enforcing
        the GMP quarantine-to-stock release workflow.
        """
        BLOCKED = {'quarantine', 'rejected', 'on_hold', 'recalled'}
        STATUS_LABEL = {
            'quarantine': 'Quarantine',
            'rejected':   'Rejected',
            'on_hold':    'On Hold',
            'recalled':   'Recalled',
        }
        for line in picking.move_line_ids:
            lot = line.lot_id
            if lot and lot.lot_status in BLOCKED:
                raise UserError(_(
                    'GMP Violation: Lot/Batch \'%(lot)s\' (%(product)s) '
                    'has status \'%(status)s\' and cannot be used in this operation.\n\n'
                    'Release the lot from the Quarantine Queue before proceeding.',
                    lot=lot.name,
                    product=lot.product_id.display_name,
                    status=STATUS_LABEL.get(lot.lot_status, lot.lot_status),
                ))
