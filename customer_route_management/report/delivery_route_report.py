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
from odoo import api, models


class RouteReportTemplate(models.AbstractModel):
    """Values of the PDF report of delivery routes."""
    _name = 'report.customer_route_management.route_report_template'
    _description = 'Delivery Route Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Routes chosen in the wizard and the report options."""
        data = data or {}
        return {
            'docs': self.env['delivery.route'].browse(data.get('route_ids', [])).exists(),
            'pay': data.get('payment', False),
            'consolidated': data.get('consolidated', False),
        }
