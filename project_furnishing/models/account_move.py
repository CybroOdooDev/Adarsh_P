# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_furnishing_project = fields.Boolean(
        string='Furnishing Project',
        compute='_compute_is_furnishing_project',
        store=True,
        index=True,
    )

    @api.depends(
        'line_ids.sale_line_ids.order_id.is_furnishing_project',
        'line_ids.purchase_line_id.order_id.is_furnishing_project',
        'line_ids.analytic_distribution',
    )
    def _compute_is_furnishing_project(self):
        furnishing_analytic_ids = None
        for move in self:
            is_furnishing = False
            # Check sales order project
            if any(line.sale_line_ids.order_id.is_furnishing_project for line in move.line_ids):
                is_furnishing = True
            # Check purchase order project
            elif any(
                line.purchase_line_id.order_id.is_furnishing_project
                for line in move.line_ids
            ):
                is_furnishing = True
            # Check analytic accounts linked to furnishing projects
            elif any(move.line_ids.mapped('analytic_distribution')):
                if furnishing_analytic_ids is None:
                    furnishing_analytic_ids = set(self.env['project.project'].search([
                        ('is_furnishing_project', '=', True),
                        ('account_id', '!=', False),
                    ]).account_id.ids)
                for line in move.line_ids:
                    if line.analytic_distribution and any(
                        acc_id.isdigit() and int(acc_id) in furnishing_analytic_ids
                        for acc_id in line.analytic_distribution
                    ):
                        is_furnishing = True
                        break
            move.is_furnishing_project = is_furnishing


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_furnishing_project = fields.Boolean(
        string='Furnishing Project',
        compute='_compute_is_furnishing_project',
        search='_search_is_furnishing_project',
    )

    def _compute_is_furnishing_project(self):
        for payment in self:
            is_furnishing = False
            moves = payment.reconciled_invoice_ids | payment.reconciled_bill_ids
            if any(move.is_furnishing_project for move in moves):
                is_furnishing = True
            payment.is_furnishing_project = is_furnishing

    def _search_is_furnishing_project(self, operator, value):
        furnishing_moves = self.env['account.move'].search([('is_furnishing_project', '=', True)])
        if not furnishing_moves:
            return [('id', '=', 0)] if (operator in ('=', '==') and value) else []
        payments = self.env['account.payment'].search([
            '|',
            ('reconciled_invoice_ids', 'in', furnishing_moves.ids),
            ('reconciled_bill_ids', 'in', furnishing_moves.ids),
        ])
        matching_ids = payments.ids
        if (operator in ('=', '==') and value) or (operator == '!=' and not value):
            return [('id', 'in', matching_ids)]
        else:
            return [('id', 'not in', matching_ids)]
