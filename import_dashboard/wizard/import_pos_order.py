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

from odoo import fields, models, _
from odoo.exceptions import ValidationError

from .spreadsheet import (cell_text, number_error, open_workbook,
                          to_utc_datetime)


class ImportPosOrder(models.TransientModel):
    """ Model for import POS Orders """
    _name = 'import.pos.order'
    _description = 'Pos Orders Import'

    file_type = fields.Selection(
        selection=[('csv', 'CSV File'), ('xls', 'XLS File')],
        string='Select File Type', default='xls',
        help='It helps to choose the file type')
    file_upload = fields.Binary(string='File Upload',
                                help="It helps to upload file")
    import_product_by = fields.Selection(
        selection=[('name', 'Name'), ('default_code', 'Internal Reference'),
                   ('barcode', 'Barcode')], string="Import order by",
        help="Import product", default="name")

    def _find_product(self, item):
        """Return the product of a row, matched as chosen in 'Import order
        by': by name ('Product'), internal reference ('Product Code') or
        barcode ('Barcode')."""
        product_product = self.env['product.product']
        if self.import_product_by == 'default_code':
            key, value = 'default_code', cell_text(item.get('Product Code'))
        elif self.import_product_by == 'barcode':
            key, value = 'barcode', cell_text(item.get('Barcode'))
        else:
            key, value = 'name', cell_text(item.get('Product'))
        if not value:
            return product_product
        return product_product.search([(key, '=', value)], limit=1)

    def action_import_pos_order(self):
        """Creating POS Order record using uploaded xl/csv files"""
        datas = {}
        datemode = 0
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
            datemode = workbook.datemode
            headers = sheet.row_values(0)
            data = []
            for row_index in range(1, sheet.nrows):
                values = sheet.row_values(row_index)
                data += [{k: v for k, v in zip(headers, values)}]
            datas = data
        user_tz = self.env.context.get('tz') or self.env.user.tz
        row = 0
        for item in datas:
            row += 1
            vals = {}
            problem = number_error(item, (
                'Tax Amount', 'Total', 'Paid Amount', 'Amount Returned',
                'Quantity', 'Unit Price', 'Discount %', 'Sub Total'))
            if problem:
                raise ValidationError(
                    _("Row %(row)d: %(problem)s.", row=row, problem=problem))
            order_ref = None
            if item.get('Order Ref'):
                order_ref = self.env['pos.order'].search(
                    [('name', '=', item.get('Order Ref'))])
            if order_ref:
                error_msg = (
                        'A POS order with the reference "%s" already '
                        'exists.' % item.get('Order Ref'))
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
            else:
                vals['company_id'] = self.env.user.company_id.id
                vals['name'] = item.get('Order Ref')
                vals['amount_tax'] = item.get('Tax Amount') if item.get(
                    'Tax Amount') else 0.0
                vals['amount_total'] = item.get('Total') if item.get(
                    'Total') else 0.0
                vals['amount_paid'] = item.get('Paid Amount') if item.get(
                    'Paid Amount') else 0.0
                vals['amount_return'] = item.get(
                    'Amount Returned') if item.get(
                    'Amount Returned') else 0.0
                if not item.get('Responsible'):
                    raise ValidationError(
                        _("Row %d: 'Responsible' column is required for POS "
                          "order import.", row))
                # archived users included: imported orders are often from
                # employees who have since left. Not named ``user``: _()
                # reads a local of that name to pick the language.
                responsible = self.env['res.users'].with_context(
                    active_test=False).search(
                    [('name', '=', item.get('Responsible'))])
                if not responsible:
                    raise ValidationError(
                        _("Row %(row)d: responsible user %(name)s not found.",
                          row=row, name=item.get('Responsible')))
                if len(responsible) > 1:
                    raise ValidationError(
                        _("Row %(row)d: several users are named %(name)s.",
                          row=row, name=item.get('Responsible')))
                vals['user_id'] = responsible.id
                if item.get('Session'):
                    # Search for an existing session by name
                    # (any non-closed state)
                    session = self.env['pos.session'].search(
                        [('name', '=', item.get('Session')),
                         ('state', '!=', 'closed')], limit=1)
                    if not session:
                        # Fallback: find any open session (state='opened')
                        session = self.env['pos.session'].search(
                            [('state', '=', 'opened')], limit=1)
                    if not session:
                        raise ValidationError(
                            _("No open POS session found. Please open a "
                              "POS session before importing orders."))
                    vals['session_id'] = session.id
                else:
                    raise ValidationError(
                        _("Row %d: 'Session' column is required for POS "
                          "order import.", row))
                if item.get('Receipt Number'):
                    vals['pos_reference'] = item.get('Receipt Number')
                order_date = item.get('Order Date')
                if order_date:
                    # times in the file are the importing user's local time
                    try:
                        vals['date_order'] = to_utc_datetime(
                            order_date, user_tz, datemode)
                    except ValueError:
                        raise ValidationError(
                            _("Row %(row)d: '%(value)s' is not a valid Order "
                              "Date. Use the format YYYY-MM-DD HH:MM:SS.",
                              row=row, value=order_date))
                if item.get('Customer'):
                    partner_id = self.env['res.partner'].search(
                        [('name', '=', item.get('Customer'))])
                    if len(partner_id) > 1:
                        raise ValidationError(
                            _("Row %(row)d: several customers are named "
                              "%(name)s.", row=row,
                              name=item.get('Customer')))
                    if not partner_id:
                        partner_id = self.env['res.partner'].create({
                            'name': item.get('Customer')
                        })
                    vals['partner_id'] = partner_id.id
                lines = {}
                if (item.get('Product') or item.get('Product Code')
                        or item.get('Barcode')):
                    product = self._find_product(item)
                    if not product:
                        raise ValidationError(
                            _("Row %(row)d: product %(product)s not found.",
                              row=row,
                              product=item.get('Product')
                              or item.get('Product Code')
                              or item.get('Barcode')))
                    lines['product_id'] = product.id
                    lines['full_product_name'] = (item.get('Product')
                                                  or product.display_name)
                    lines['qty'] = item.get('Quantity')
                    lines['price_unit'] = item.get('Unit Price')
                    lines['discount'] = item.get('Discount %')
                    lines['price_subtotal'] = item.get('Sub Total')
                    lines['price_subtotal_incl'] = 0.0
                vals['lines'] = [(0, 0, lines)]
                self.env['pos.order'].create(vals)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Imported Successfully',
                'type': 'rainbow_man',
            }
        }
