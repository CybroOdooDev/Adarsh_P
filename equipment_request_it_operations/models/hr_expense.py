# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#############################################################################
from odoo import fields, models


class HrExpense(models.Model):
    """
    Model representing expenses associated with equipment requests.
    This model inherits from the `hr.expense` model and adds a Many2one field
    `equipment_expense_id` to link expenses with equipment requests. This field
    is used to associate expenses with the corresponding equipment request.
    """
    _inherit = "hr.expense"

    equipment_expense_id = fields.Many2one(
        'equipment.request', string='Equipment',
        help="Equipment request whose damages generated this expense")
