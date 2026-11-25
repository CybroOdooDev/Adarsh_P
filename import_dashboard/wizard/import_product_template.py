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

from .spreadsheet import cell_text, number_error, open_workbook


class ImportProductTemplate(models.TransientModel):
    """ Model for import product template. """
    _name = 'import.product.template'
    _description = 'Product Template Import'

    file_type = fields.Selection(
        selection=[('csv', 'CSV File'), ('xls', 'Excel File')],
        string='Select File Type', default='csv', help="file type")
    method = fields.Selection(selection=[('create_product', 'Create Product'),
                                         ('update_product',
                                          'Create or Update Product')],
                              string='Method', default='create_product',
                              help="method")
    import_product_by = fields.Selection(
        selection=[('name', 'Name'),
                   ('internal_reference', 'Internal Reference'),
                   ], string="Product Update By",
        default='name', help="It helps to import product")
    file_upload = fields.Binary(string='File Upload',
                                help="It helps to upload file")

    def action_import_product_template(self):
        """Creating product record using uploaded xl/csv files"""

        if self.file_type == 'csv':
            try:
                csv_data = base64.b64decode(self.file_upload)
                data_file = io.StringIO(csv_data.decode("utf-8"))
                data_file.seek(0)
                items = csv.DictReader(data_file, delimiter=',')
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the file format and "
                    "try again!"
                )

        elif self.file_type == 'xls':
            try:
                workbook = open_workbook(
                    file_contents=base64.b64decode(self.file_upload))
                sheet = workbook.sheet_by_index(0)
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the file format and "
                    "try again!"
                )

            headers = sheet.row_values(0)
            items = []
            for row_index in range(1, sheet.nrows):
                row = sheet.row_values(row_index)
                items.append(dict(zip(headers, row)))

        else:
            raise ValidationError("Unsupported file type.")

        PRODUCT_TYPE_MAP = {
            'goods': 'consu',
            'consu': 'consu',
            'service': 'service',
            'combo': 'combo',
        }
        created = 0
        updated = 0
        for row, item in enumerate(items, start=1):
            product = False
            problem = number_error(item, ('Sales Price', 'Cost'))
            if problem:
                raise ValidationError("Row %d: %s." % (row, problem))
            # Excel gives numeric codes as floats (12345.0)
            internal_ref = cell_text(item.get('Internal Reference')) or False
            raw_type = (item.get('Product Type') or 'consu').strip().lower()
            product_type = PRODUCT_TYPE_MAP.get(raw_type)

            if not product_type:
                raise ValidationError(
                    "Invalid Product Type '%s'.\n"
                    "Allowed values: consu (Goods), service, combo"
                    % item.get('Product Type'))
            vals = {
                "name": item.get('Name'),
                "type": product_type,
                "default_code": internal_ref,
                "list_price": item.get('Sales Price') or 0.0,
                "standard_price": item.get('Cost') or 0.0,
            }
            if self.method == "create_product":
                product = self.env['product.template'].search(
                    [('name', '=', item.get('Name'))],
                    limit=1
                )
            elif self.method == "update_product":
                if self.import_product_by == "name":
                    product = self.env['product.template'].search(
                        [('name', '=', item.get('Name'))],
                        limit=1
                    )
                elif self.import_product_by == "internal_reference":
                    product = self.env['product.template'].search(
                        [('default_code', '=', internal_ref)],
                        limit=1
                    )
                if product:
                    product.write(vals)
                    updated += 1
            if not product:
                self.env['product.template'].create(vals)
                created += 1

        msg = "Imported %d records.\nUpdated %d records." % (created, updated)
        self.env['import.message'].create({'message': msg})
        return {
            'effect': {
                'fadeout': 'slow',
                'message': msg,
                'type': 'rainbow_man',
            }
        }
