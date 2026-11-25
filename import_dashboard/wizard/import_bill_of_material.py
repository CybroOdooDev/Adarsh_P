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


class ImportBillOfMaterial(models.TransientModel):
    """ Model for importing Bill of Materials. """
    _name = 'import.bill.of.material'
    _description = 'Bill of Material Import'

    file_type = fields.Selection(selection=[('csv', 'CSV File'),
                                            ('xls', 'XLS File')],
                                 default='csv',
                                 string='Select File Type',
                                 help="Uploading file Type")
    file_upload = fields.Binary(string='Upload File',
                                help="Helps to upload file")
    import_product_by = fields.Selection(
        selection=[
            ('default_code', 'Internal Reference'), ('barcode', 'Barcode')],
        default='default_code', string="Import Products By",
        help="Helps to import product")
    bom_type = fields.Selection(
        selection=[('manufacture_this_product', 'Manufacture this Product'),
                   ('kit', 'Kit'), ('both', 'Both')], string="Bom Type",
        default='both', help="Helps to choose the bom type")
    bom_component = fields.Selection(
        selection=[('add', 'Add Components'),
                   ('do_not', 'Do not add Components')], default='add',
        string="Bom Component", help="Helps to choose the bom component")

    def action_import_bom(self):
        """Creating bill of material records using uploaded xl/csv files"""
        datas = {}
        if self.file_type == 'csv':
            try:
                csv_data = base64.b64decode(self.file_upload)
                data_file = io.StringIO(csv_data.decode("utf-8"))
                data_file.seek(0)
                datas = csv.DictReader(data_file, delimiter=',')
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the type and format "
                    "of the file and try again!")
        if self.file_type == 'xls':
            try:
                workbook = open_workbook(
                    file_contents=base64.b64decode(self.file_upload))
                sheet = workbook.sheet_by_index(0)
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the type and format "
                    "of the file and try again!")
            headers = sheet.row_values(0)
            data = []
            for row_index in range(1, sheet.nrows):
                row = sheet.row_values(row_index)
                data += [{k: v for k, v in zip(headers, row)}]
            datas = data
        row = 0
        imported = 0
        updated = 0
        error_msg = ""
        warning_msg = ""
        product_template = self.env['product.template']
        product_product = self.env['product.product']
        for item in datas:
            row += 1
            vals = {}
            if not item.get('Product'):
                error_msg += (
                    "\n\t⚠ Product name missing in file! (row %d)" % row)
                continue
            # Excel gives numeric codes as floats (12345.0)
            codes = {column: cell_text(item.get(column)) for column in (
                'Product/Internal Reference', 'Product/Barcode',
                'Components/Internal Reference', 'Components/Barcode')}
            problem = number_error(item, ('Quantity', 'BoM Lines/Quantity'))
            if problem:
                error_msg += "\n\t⚠ %s (row %d)" % (problem, row)
                continue
            # look the product and the component up before creating
            # anything, so a row that is not imported leaves nothing behind
            if (self.import_product_by == 'default_code'
                    and codes['Product/Internal Reference']):
                key, value = ('Internal Reference',
                              codes['Product/Internal Reference'])
                product_tmpl = product_template.search(
                    [('default_code', '=', value)])
            elif (self.import_product_by == 'barcode'
                    and codes['Product/Barcode']):
                key, value = 'Barcode', codes['Product/Barcode']
                product_tmpl = product_template.search(
                    [('barcode', '=', value)])
            else:
                key, value = 'name', item.get('Product')
                product_tmpl = product_template.search(
                    [('name', '=', value)])
            if len(product_tmpl) > 1:
                error_msg += ("\n\t⚠ Multiple products with %s (%s) found! "
                              "(row %d)" % (key, value, row))
                continue
            component = product_product
            add_component = (self.bom_component == 'add'
                             and item.get('Components'))
            if add_component:
                if codes['Components/Internal Reference']:
                    key, value = ('Internal Reference',
                                  codes['Components/Internal Reference'])
                    component = product_product.search(
                        [('default_code', '=', value)])
                elif codes['Components/Barcode']:
                    key, value = 'Barcode', codes['Components/Barcode']
                    component = product_product.search(
                        [('barcode', '=', value)])
                else:
                    key, value = 'name', item.get('Components')
                    component = product_product.search(
                        [('name', '=', value)])
                if len(component) > 1:
                    error_msg += ("\n\t⚠ Multiple components with %s (%s) "
                                  "found! (row %d)" % (key, value, row))
                    continue
            elif self.bom_component == 'add':
                raise ValidationError(
                    "File not contain any BoM Lines/Components."
                    "\n\nPlease check the file.")
            if not product_tmpl:
                product_tmpl = product_template.create({
                    'name': item.get('Product'),
                    'default_code': codes['Product/Internal Reference']
                    or False,
                    'barcode': codes['Product/Barcode'] or False,
                })
                warning_msg += ("\n◼ A Product is created with "
                                "\"Internal Reference\" as "
                                "product name since \"Product\""
                                " name is missing in file."
                                "(row %d)" % row)
            vals['product_tmpl_id'] = product_tmpl.id
            if item.get('Quantity'):
                vals['product_qty'] = item.get('Quantity')
            if item.get('Reference'):
                vals['code'] = item.get('Reference')
            if self.bom_type == 'manufacture_this_product':
                vals['type'] = 'normal'
            elif self.bom_type == 'kit':
                vals['type'] = 'phantom'
            else:
                if item.get('BoM Type'):
                    if item.get('BoM Type') == 'Manufacture this product':
                        vals['type'] = 'normal'
                    else:
                        vals['type'] = 'phantom'
            components = {}
            if add_component:
                if not component:
                    component = product_product.create({
                        'name': item.get('Components'),
                        'default_code': codes['Components/Internal Reference']
                        or False,
                        'barcode': codes['Components/Barcode'] or False,
                    })
                    warning_msg += (
                        "\n◼ A Component Product is created with "
                        "\"Internal Reference\" as "
                        "product name since \"Product\""
                        " name is missing in file."
                        "(row %d)" % row)
                components['product_id'] = component.id
                if item.get('BoM Lines/Quantity'):
                    components['product_qty'] = item.get(
                        'BoM Lines/Quantity')
                vals['bom_line_ids'] = [(0, 0, components)]
            bom_id = self.env['mrp.bom'].search(
                [('product_tmpl_id', '=', vals['product_tmpl_id'])], limit=1)
            if bom_id and self.bom_component == 'add':
                bom_id.write({
                    'bom_line_ids': [(0, 0, components)]
                })
                updated += 1
            else:
                self.env['mrp.bom'].create(vals)
                imported += 1
        if error_msg:
            error_msg = "\n\nERROR" + error_msg
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
        msg = (("Imported %d records.\nUpdated %d records"
                % (imported, updated)) +
               warning_msg)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': msg,
                'type': 'rainbow_man',
            }
        }
