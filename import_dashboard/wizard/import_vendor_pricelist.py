# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
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
import base64
import csv
import io

from odoo import fields, models
from odoo.exceptions import ValidationError

from .spreadsheet import open_workbook


class ImportVendorPricelist(models.TransientModel):
    """ Model for import vendor pricelist. """
    _name = 'import.vendor.pricelist'
    _description = 'Vendor Pricelist Import'

    file_type = fields.Selection(
        selection=[('csv', 'CSV File'), ('xls', 'Excel File')],
        string='Select File Type', default='csv', help='File type')
    company_id = fields.Many2one(comodel_name='res.company', string='Company',
                                 help="Company", required=True,
                                 default=lambda self: self.env.company)
    file_upload = fields.Binary(string="Upload File",
                                help="Helps to upload your file")

    def action_import_vendor_pricelist(self):
        """Creating vendor pricelist record using uploaded xl/csv files"""
        items = False
        if self.file_type == 'csv':
            try:
                csv_data = base64.b64decode(self.file_upload)
                data_file = io.StringIO(csv_data.decode("utf-8"))
                data_file.seek(0)
                csv_reader = csv.DictReader(data_file, delimiter=',')
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the type and format "
                    "of the file and try again!")
            items = csv_reader
        if self.file_type == 'xls':
            try:
                workbook = open_workbook(
                    file_contents=base64.b64decode(self.file_upload))
                sheet = workbook.sheet_by_index(0)
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the type and format of "
                    "the file and try again!")
            headers = sheet.row_values(0)  # list
            data = []
            for row_index in range(1, sheet.nrows):
                row = sheet.row_values(row_index)  # list
                data += [{k: v for k, v in zip(headers, row)}]
            items = data
        info_msg = ""
        error_msg = ""
        imported = 0
        row_count = 0
        company_currency = self.company_id.currency_id
        for item in items:
            row_count += 1
            row_error = ""
            if not item.get('Vendor'):
                row_error += "\n\tMissing 'Vendor' name."
            if not item.get('Product Template'):
                row_error += "\n\tMissing 'Product Template' name."
            numbers = {}
            for key, columns, convert in (
                    ('min_qty', ('Quantity',), float),
                    ('price', ('Price', 'Unit Price'), float),
                    ('delay', ('Delivery Lead Time', 'Lead Time'), int)):
                raw = next((item.get(column) for column in columns
                            if item.get(column) not in (None, '')), 0)
                try:
                    numbers[key] = convert(float(str(raw).strip()))
                except ValueError:
                    row_error += "\n\tInvalid number in '%s': %s" % (
                        columns[0], raw)
            if row_error:
                error_msg += "\nRow %d not imported: %s" % (
                    row_count, row_error)
                continue

            vendor = self.env['res.partner'].search(
                [('name', '=', item['Vendor'])], limit=1)
            if not vendor:
                vendor = self.env['res.partner'].create({
                    'name': item['Vendor'],
                })
                info_msg += ("\nCreated new partner with name: %s"
                             % item['Vendor'])
            product = self.env['product.template'].search(
                [('name', '=', item['Product Template'])], limit=1)
            if not product:
                product = self.env['product.template'].create(
                    {'name': item['Product Template']})
                info_msg += ("\nCreated new product with name: %s"
                             % item['Product Template'])

            currency = company_currency
            if item.get('Currency'):
                currency = self.env['res.currency'].search(
                    ['|',
                     ('name', '=', item['Currency']),
                     ('symbol', '=', item['Currency'])],
                    limit=1
                ) or company_currency
            self.env['product.supplierinfo'].create({
                'product_tmpl_id': product.id,
                'partner_id': vendor.id,
                'company_id': self.company_id.id,
                'currency_id': currency.id,
                **numbers,
            })
            imported += 1

        if error_msg:
            error_msg = "\n\n⚠⚠⚠ ERROR !!! ⚠⚠⚠" + error_msg
            error_message = self.env['import.message'].create(
                {'message': error_msg})
            return {
                'name': 'Error!',
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'import.message',
                'res_id': error_message.id,
                'target': 'new'
            }

        if info_msg:
            info_msg = "\nInformation : %s" % info_msg
        msg = (("Imported %d records."
                % imported) + info_msg)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': msg,
                'type': 'rainbow_man',
            }
        }
