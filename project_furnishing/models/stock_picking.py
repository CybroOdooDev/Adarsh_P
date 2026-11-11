# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        for picking in self:
            if picking.picking_type_code == 'outgoing':
                # Identify project related to this delivery
                project = getattr(picking, 'project_id', False)
                if not project and hasattr(picking, 'sale_id') and picking.sale_id:
                    project = getattr(picking.sale_id, 'project_id', False)
                if not project:
                    for move in picking.move_ids:
                        sale_line = getattr(move, 'sale_line_id', False)
                        if sale_line and sale_line.order_id and getattr(sale_line.order_id, 'project_id', False):
                            project = sale_line.order_id.project_id
                            break

                if project and getattr(project, 'is_furnishing_project', False):
                    # Group outgoing moves by product to check quantity requirements
                    for product in picking.move_ids.mapped('product_id'):
                        moves_for_product = picking.move_ids.filtered(
                            lambda m: m.product_id == product and m.state not in ('done', 'cancel')
                        )
                        qty_to_deliver = sum(moves_for_product.mapped('quantity')) or sum(moves_for_product.mapped('product_uom_qty'))
                        if qty_to_deliver <= 0:
                            continue

                        # Check if moves link directly to specific MOs
                        orig_mos = moves_for_product.mapped('move_orig_ids.production_id')
                        if orig_mos:
                            for mo in orig_mos:
                                unpassed_mo_qcs = mo.quality_check_ids.filtered(lambda q: not q.dispatch_ready)
                                if unpassed_mo_qcs or (mo.state == 'done' and not mo.quality_check_ids.filtered(lambda q: q.dispatch_ready)):
                                    raise UserError(_(
                                        "Cannot validate delivery order '%(picking)s'. Manufacturing Order '%(mo)s' for '%(prod)s' has not passed Quality Inspection (Site-Ready certification)."
                                    ) % {
                                        'picking': picking.name,
                                        'mo': mo.name,
                                        'prod': product.display_name,
                                    })

                        # Quantity-based check for project pieces
                        all_qcs = self.env['furnishing.quality.check'].search([
                            ('project_id', '=', project.id),
                            ('product_id', '=', product.id),
                        ])
                        if all_qcs:
                            passed_qcs = all_qcs.filtered(lambda q: q.state == 'passed' and q.dispatch_ready)
                            total_passed_qty = sum(passed_qcs.mapped('product_qty'))

                            # Sum already delivered quantity for this product and project (excluding current picking moves)
                            delivered_domain = [
                                ('product_id', '=', product.id),
                                ('state', '=', 'done'),
                                ('picking_id.picking_type_code', '=', 'outgoing'),
                                ('id', 'not in', picking.move_ids.ids),
                            ]
                            if hasattr(self.env['stock.move'], 'project_id'):
                                delivered_domain.append(('project_id', '=', project.id))
                            else:
                                delivered_domain.append(('picking_id.project_id', '=', project.id))

                            delivered_moves = self.env['stock.move'].search(delivered_domain)
                            already_delivered_qty = sum(delivered_moves.mapped('quantity'))
                            available_certified_qty = max(0.0, total_passed_qty - already_delivered_qty)

                            if available_certified_qty < qty_to_deliver:
                                unready_qcs = all_qcs.filtered(lambda q: not q.dispatch_ready)
                                pending_info = ", ".join(
                                    f"{q.name} ({dict(q._fields['state'].selection).get(q.state, q.state)})"
                                    for q in unready_qcs[:3]
                                )
                                raise UserError(_(
                                    "Cannot validate delivery order '%(picking)s'. Insufficient certified pieces for '%(product)s'.\n"
                                    "• Delivering: %(deliver_qty)g unit(s)\n"
                                    "• Certified Site-Ready available: %(avail_qty)g unit(s)\n"
                                    "• Total passed: %(passed_qty)g, Already delivered: %(deliv_qty)g\n"
                                    "%(pending_txt)s"
                                ) % {
                                    'picking': picking.name,
                                    'product': product.display_name,
                                    'deliver_qty': qty_to_deliver,
                                    'avail_qty': available_certified_qty,
                                    'passed_qty': total_passed_qty,
                                    'deliv_qty': already_delivered_qty,
                                    'pending_txt': f"• Uncertified inspection(s): {pending_info}" if pending_info else "",
                                })

        return super().button_validate()
