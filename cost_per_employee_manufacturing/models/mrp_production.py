# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is under the terms of the Odoo Proprietary License v1.0
#    (OPL-1) It is forbidden to publish, distribute, sublicense, or
#    sell copies of the Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
#    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
#    OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
#    THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#############################################################################
from odoo import api, fields, models


class MrpProduction(models.Model):
    """Adding fields to mrp production"""

    _inherit = "mrp.production"

    cost_per_hour = fields.Float(
        compute="_compute_cost_per_hour",
        store=True,
        string="Cost per hour",
        help="Cost per hour of production",
    )
    cost = fields.Float(
        related="cost_per_hour", store=True, string="Cost", help="Cost of production"
    )

    @api.depends("workorder_ids", "workorder_ids.duration")
    def _compute_cost_per_hour(self):
        """Calculate cost per hour of employee across work orders"""
        for record in self:
            logged_in_employee = record.env.user.employee_id
            total_cost = 0.0
            if logged_in_employee:
                hourly_cost = logged_in_employee.hour_per_cost or 0.0
                for work_order in record.workorder_ids:
                    work_center_employee_ids = work_order.workcenter_id.cost_per_employee_ids.employee_id.ids
                    if logged_in_employee.id in work_center_employee_ids:
                        total_cost += hourly_cost * (work_order.duration / 60.0)
            record.cost_per_hour = total_cost