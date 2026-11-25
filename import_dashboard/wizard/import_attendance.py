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

from .spreadsheet import number_error, open_workbook, to_utc_datetime


class ImportAttendance(models.TransientModel):
    """ Model for Attendance import wizard. """
    _name = 'import.attendance'
    _description = 'Attendance Import'

    file_type = fields.Selection(
        selection=[('csv', 'CSV File'), ('xls', 'XLS File')],
        string='Select File Type', default='csv',
        help="It helps to select File Type")
    file_upload = fields.Binary(string="Upload File",
                                help="It helps to upload files")

    def action_import_attendance(self):
        """Creating attendance record using uploaded xl/csv files"""
        hr_employee = self.env['hr.employee']
        hr_attendance = self.env['hr.attendance']
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
                row = sheet.row_values(row_index)
                data += [{k: v for k, v in zip(headers, row)}]
            datas = data
        user_tz = self.env.context.get('tz') or self.env.user.tz
        for row, item in enumerate(datas, start=1):
            vals = {}
            if item.get('Employee'):
                employee = hr_employee.search(
                    [('name', '=', item.get('Employee'))])
                if len(employee) > 1:
                    raise ValidationError(
                        "Row %d: several employees are named %s."
                        % (row, item.get('Employee')))
                if employee:
                    vals['employee_id'] = employee.id
                else:
                    raise ValidationError(
                        "There is no employee with that name."
                        "\n\nPlease check and try again!")
            for column, field_name in (('Check In', 'check_in'),
                                       ('Check Out', 'check_out')):
                value = item.get(column)
                if not value:
                    continue
                # times in the file are the importing user's local time
                try:
                    vals[field_name] = to_utc_datetime(
                        value, user_tz, datemode)
                except ValueError:
                    raise ValidationError(
                        "Row %d: '%s' is not a valid %s date and time. "
                        "Use the format YYYY-MM-DD HH:MM:SS."
                        % (row, value, column))
            problem = number_error(item, ('Worked Hours',))
            if problem:
                raise ValidationError("Row %d: %s." % (row, problem))
            if item.get('Worked Hours'):
                vals['worked_hours'] = item.get('Worked Hours')
            hr_attendance.create(vals)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Imported Successfully',
                'type': 'rainbow_man',
            }
        }
