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
from odoo import models


class ReportMoOverview(models.AbstractModel):
    """Override method for adding cost per employee to MO Overview report."""

    _inherit = 'report.mrp.report_mo_overview'

    def _get_report_data(self, production_id):
        """Add employee cost to MO overview report data."""
        res = super()._get_report_data(production_id)
        production = self.env['mrp.production'].browse(production_id)
        res['cost_per_employ'] = production.cost_per_hour
        return res

    def _get_report_extra_lines(self, summary, components, operations, production):
        """Include employee cost into unit and total cost extras."""
        extras = super()._get_report_extra_lines(summary, components, operations, production)
        if production.cost_per_hour:
            production_qty = summary.get('quantity') or 1.0
            unit_employee_cost = production.cost_per_hour / production_qty
            extras['unit_mo_cost'] = (extras.get('unit_mo_cost') or 0.0) + unit_employee_cost
            if 'total_mo_cost' in extras:
                extras['total_mo_cost'] += production.cost_per_hour
        return extras
