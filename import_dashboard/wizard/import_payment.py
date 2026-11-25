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
import xlrd

from odoo import fields, models
from odoo.exceptions import ValidationError

from .spreadsheet import number_error, open_workbook


class ImportPayment(models.TransientModel):
    """ Model for import payment """
    _name = 'import.payment'
    _description = 'Payment Import'

    file_type = fields.Selection(
        selection=[('csv', 'CSV File'), ('xlsx', 'XLS File')],
        string='Select File Type', default='xlsx',
        help='It helps to choose the file type')
    file_upload = fields.Binary(string='File Upload',
                                help='It helps to upload files')

    def action_import_payment(self):
        """ Method to import payments from .csv or .xlsx files. """
        datemode = 0
        if self.file_type == 'csv':
            try:
                csv_data = base64.b64decode(self.file_upload)
                data_file = io.StringIO(csv_data.decode("utf-8"))
                data_file.seek(0)
                csv_reader = csv.DictReader(data_file, delimiter=',')
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the type and format "
                    "of the file, and try again!")
            items = csv_reader
        if self.file_type == 'xlsx':
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
                row = sheet.row_values(row_index)
                data += [{k: v for k, v in zip(headers, row)}]
            items = data
        row = 0
        imported = 0
        updated = 0
        error_msg = ""
        info_msg = ""
        for item in items:
            row += 1
            vals = {}
            row_not_import_msg = "\nRow {rn} not imported.".format(rn=row)
            problem = number_error(item, ('Amount',))
            if problem:
                error_msg += row_not_import_msg + "\n\t" + problem
                continue
            if item.get('Amount'):
                vals['amount'] = item['Amount']
            if item.get('Date'):
                date_val = item.get('Date')
                if isinstance(date_val, float):
                    # Excel stores dates as serial numbers
                    date_val = xlrd.xldate_as_datetime(
                        date_val, datemode).date()
                vals['date'] = date_val
            if item.get('Journal'):
                journal = self.env['account.journal'].search([
                    ('name', '=', item.get('Journal')),
                    ('type', 'in', ('bank', 'cash', 'credit')),
                    *self.env['account.journal']._check_company_domain(
                        self.env.company),
                ])
                if not journal:
                    error_msg += row_not_import_msg + (
                        "\n\tPayment journal (%s) not found!"
                        % item.get('Journal'))
                    continue
                if len(journal) > 1:
                    error_msg += row_not_import_msg + (
                        "\n\tMultiple journals with name (%s) found!"
                        % item.get('Journal'))
                    continue
                vals['journal_id'] = journal.id
            if item.get('Customer/Vendor'):
                partner = self.env['res.partner'].search(
                    [('name', '=', item.get('Customer/Vendor'))])
                if len(partner) > 1:
                    error_msg += row_not_import_msg + (
                        "\n\tMultiple partners with name (%s) found!"
                        % item.get('Customer/Vendor'))
                    continue
                if not partner:
                    partner = self.env['res.partner'].create({
                        'name': item.get('Customer/Vendor')
                    })
                    info_msg += ("\nCreated new partner with name :%s"
                                 % item.get('Customer/Vendor'))
                vals['partner_id'] = partner.id
            if item.get('Reference'):
                vals['memo'] = item.get('Reference')
            if item.get('Payment Type') == 'Send':
                vals['payment_type'] = 'outbound'
            elif item.get('Payment Type') == 'Receive':
                vals['payment_type'] = 'inbound'
            else:
                error_msg += row_not_import_msg + (
                    "\n\tPayment type Values is wrong in file!")
                continue
            if item.get('Number'):
                payment_ref = self.env['account.payment'].search(
                    [('name', '=', item.get('Number'))])
                if payment_ref:
                    payment_ref.write(vals)
                    updated += 1
                else:
                    vals['name'] = item.get('Number')
                    self.env['account.payment'].create(vals)
                    imported += 1
        if error_msg:
            error_msg = "\n\n⚠⚠⚠ERROR!!!⚠⚠⚠" + error_msg
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
        msg = (("Imported %d records. Updated %d records"
                % (imported, updated)) + info_msg)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': msg,
                'type': 'rainbow_man',
            }
        }
