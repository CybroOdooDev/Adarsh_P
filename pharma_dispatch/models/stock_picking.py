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
from odoo.exceptions import UserError


def _unreleased_lots_message(env, lots):
    labels = dict(env['stock.lot']._fields['lot_status']._description_selection(env))
    return '\n'.join(
        '- %s (%s): %s' % (lot.name, lot.product_id.display_name,
                           labels.get(lot.lot_status, lot.lot_status))
        for lot in lots)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    shipment_ids = fields.One2many('pharma.shipment', 'picking_id',
                                   string='Shipments')
    checklist_template_id = fields.Many2one(
        'pharma.dispatch.checklist.template', string='Dispatch Checklist',
        tracking=True, copy=False,
        domain="[('company_id', 'in', (False, company_id))]",
        help='Pre-loading checklist the vehicle must pass before this delivery '
             'is dispatched. Required to create the shipment.')
    shipment_count = fields.Integer(compute='_compute_shipment_count')
    active_shipment_count = fields.Integer(compute='_compute_shipment_count')

    def _compute_shipment_count(self):
        for picking in self:
            picking.shipment_count = len(picking.shipment_ids)
            picking.active_shipment_count = len(
                picking.shipment_ids.filtered(lambda s: s.state != 'cancel'))

    def _pharma_is_customer_delivery(self):
        self.ensure_one()
        return (self.picking_type_code == 'outgoing'
                and self.location_dest_id.usage == 'customer')

    def _pharma_unreleased_lots(self):
        """Batches on the delivery that QA has not released."""
        return self.move_line_ids.filtered('quantity').lot_id.filtered(
            lambda lot: lot.lot_status != 'released')

    def _pharma_check_released_lots(self):
        """Only QA-released batches may leave for a customer."""
        for picking in self.filtered(lambda p: p._pharma_is_customer_delivery()):
            lots = picking._pharma_unreleased_lots()
            if lots:
                raise UserError(self.env._(
                    'GMP: only QA-released batches can be delivered to a customer. '
                    '%(picking)s contains batches that are not released:\n%(lots)s',
                    picking=picking.name,
                    lots=_unreleased_lots_message(self.env, lots)))

    def _action_done(self):
        self._pharma_check_released_lots()
        return super()._action_done()

    def action_create_shipment(self):
        """Dispatch button: create the shipment of this delivery order and
        open it so the transporter, drivers and dates can be filled in."""
        self.ensure_one()
        if self.picking_type_code != 'outgoing' or self.state != 'done':
            raise UserError(self.env._('Only validated delivery orders can be dispatched.'))
        if self.shipment_ids.filtered(lambda s: s.state != 'cancel'):
            raise UserError(self.env._('%s already has a shipment.', self.name))
        self._pharma_check_released_lots()
        if not self.checklist_template_id:
            raise UserError(self.env._(
                'Select the dispatch checklist of %s before creating its shipment.',
                self.name))
        # The partial unique index is checked by SQL: write pending
        # cancellations first so a cancelled shipment does not block.
        self.shipment_ids.flush_recordset(['state'])
        Shipment = self.env['pharma.shipment']
        shipment = Shipment.create(Shipment._prepare_from_picking(self))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'pharma.shipment',
            'res_id': shipment.id,
            'view_mode': 'form',
        }

    def action_view_shipments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'pharma_dispatch.pharma_shipment_action')
        action['domain'] = [('picking_id', '=', self.id)]
        action['context'] = {'create': False}
        if len(self.shipment_ids) == 1:
            action.update(view_mode='form', views=[(False, 'form')],
                          res_id=self.shipment_ids.id)
        return action
