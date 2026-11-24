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
import io
import json
import re

import xlsxwriter
from xlsxwriter.utility import xl_cell_to_rowcol

from odoo import fields, models
from odoo.tools import format_date, json_default


# Width of an Excel column in characters: default and maximum
DEFAULT_COLUMN_WIDTH = 8.43
MAX_COLUMN_WIDTH = 255


class RouteReport(models.TransientModel):
    """Wizard printing the customers of delivery routes, with their dues."""
    _name = 'route.report'
    _description = 'Route Report'

    route_ids = fields.Many2many('delivery.route', string='Routes',
                                 help="Delivery routes to print.")
    payment = fields.Boolean(string='Show Due Amount',
                             help="Show the amounts due by each customer.")
    consolidated = fields.Boolean(string='Total Due Only',
                                  help="Show only the total due by each customer.")

    def _get_report_data(self):
        """Options of the report, shared by the PDF and XLSX reports."""
        self.ensure_one()
        return {
            'route_ids': self.route_ids.ids,
            'payment': self.payment,
            'consolidated': self.payment and self.consolidated,
        }

    def print_route_details(self):
        """Print the PDF report of the selected routes."""
        return self.env.ref('customer_route_management.report_route_report').report_action(
            self, data=self._get_report_data())

    def print_xlsx_report_route(self):
        """Download the XLSX report of the selected routes."""
        return {
            'type': 'ir.actions.report',
            'report_type': 'xlsx',
            'data': {
                'model': self._name,
                'options': json.dumps(self._get_report_data(), default=json_default),
                'output_format': 'xlsx',
                'report_name': self.env._('Customer Route Management Report'),
            },
        }

    @staticmethod
    def _partner_address(partner):
        """Address and email of a customer on one line."""
        return ' '.join(filter(None, [
            partner.street, partner.street2, partner.city, partner.state_id.name,
            partner.zip, partner.country_id.name, partner.email]))

    @staticmethod
    def _sheet_name(route, used_names):
        """Unique sheet name for a route, within the limits of Excel."""
        name = re.sub(r'[\[\]:*?/\\]', ' ', route.name or '').strip()[:31] or str(route.id)
        if name.lower() in used_names:
            suffix = f' ({route.id})'
            name = name[:31 - len(suffix)] + suffix
        used_names.add(name.lower())
        return name

    def _format_amount(self, amount, currency):
        """Amount with the currency symbol on the side the currency uses."""
        value = f'{amount:.{currency.decimal_places}f}'
        return f'{value}{currency.symbol}' if currency.position == 'after' \
            else f'{currency.symbol}{value}'

    @staticmethod
    def _fit_columns(sheet, longest):
        """Widen columns so that each merged range shows its longest text.

        Merged cells never overflow into the next column, and xlsxwriter's
        autofit skips them, so the widths are set from the text written.

        :param longest: longest text length per (first column, last column)
            of the merged ranges of the sheet
        """
        widths = {}
        for (first, last), length in sorted(longest.items()):
            needed = min(length * 1.15 + 2, MAX_COLUMN_WIDTH)
            current = sum(widths.get(col, DEFAULT_COLUMN_WIDTH) for col in range(first, last + 1))
            if needed > current:
                widths[last] = min(widths.get(last, DEFAULT_COLUMN_WIDTH) + needed - current,
                                   MAX_COLUMN_WIDTH)
        for col, width in widths.items():
            sheet.set_column(col, col, width)

    def get_xlsx_report(self, data, response):
        """Write the XLSX report of the routes in ``data`` into ``response``:
        one sheet per route, with the customers of each area and, when
        asked, their dues or their total due."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        title_format = workbook.add_format(
            {'align': 'center', 'bold': True, 'bg_color': '#d3d3d3', 'color': '#191081'})
        left = workbook.add_format({'align': 'left'})
        area_format = workbook.add_format({'bold': True})
        customer_format = workbook.add_format({'color': '#031311'})
        bold = workbook.add_format({'bold': data['payment'], 'align': 'left'})
        show_dues = data['payment'] and not data['consolidated']
        routes = self.env['delivery.route'].browse(data['route_ids']).exists()
        used_names = set()
        for route in routes:
            sheet = workbook.add_worksheet(self._sheet_name(route, used_names))
            longest = {}

            def write(cells, value, cell_format, sheet=sheet, longest=longest):
                """Write a merged range and remember the length of its text."""
                first, last = (xl_cell_to_rowcol(cell)[1] for cell in cells.split(':'))
                longest[first, last] = max(longest.get((first, last), 0), len(value))
                sheet.merge_range(cells, value, cell_format)

            currency = route.company_id.currency_id or self.env.company.currency_id
            row = 3
            write('F1:J1', (route.name or '').upper(), title_format)
            for area in route.route_line_ids:
                if area.route:
                    write(f'A{row - 1}:B{row - 1}', area.route.upper() + ':', area_format)
                if show_dues:
                    write(f'D{row - 1}:E{row - 1}', self.env._('Invoice Number'), bold)
                    write(f'F{row - 1}:G{row - 1}', self.env._('Date'), bold)
                    write(f'H{row - 1}:I{row - 1}', self.env._('Amount Due'), bold)
                for customer in area._get_customers():
                    address = self._partner_address(customer)
                    if show_dues:
                        write(f'B{row}:C{row}',
                              ' '.join(filter(None, [customer.name, customer.phone, address])),
                              customer_format)
                    else:
                        write(f'B{row}:C{row}', customer.name or '', customer_format)
                        write(f'D{row}:E{row}', customer.phone or '', customer_format)
                        write(f'F{row}:G{row}', address, customer_format)
                    row += 1
                    if not data['payment']:
                        continue
                    dues = customer.get_all_dues(route.company_id.id)
                    if show_dues:
                        for due in dues:
                            write(f'D{row}:E{row}', due['name'], left)
                            write(f'F{row}:G{row}',
                                  format_date(self.env, due['invoice_date_due'])
                                  if due['invoice_date_due'] else '', left)
                            write(f'H{row}:I{row}',
                                  self._format_amount(due['amount_residual_signed'], currency),
                                  left)
                            row += 1
                    if dues:
                        # Shown as in the PDF report, also when the dues cancel out
                        total = sum(due['amount_residual_signed'] for due in dues)
                        write(f'D{row}:E{row}', self.env._('Total'), bold)
                        write(f'F{row}:G{row}', '', left)
                        write(f'H{row}:I{row}', self._format_amount(total, currency), bold)
                        row += 1
                row += 1
            self._fit_columns(sheet, longest)
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
