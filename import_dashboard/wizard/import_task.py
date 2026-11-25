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

from .spreadsheet import open_workbook, parse_date


class ImportTask(models.TransientModel):
    """ Model for import project task. """
    _name = 'import.task'
    _description = 'Task Import'

    file_type = fields.Selection(
        selection=[('csv', 'CSV File'), ('xls', 'XLS File')], default='csv',
        string='Select File Type', help='File type')
    file_upload = fields.Binary(string="Upload File",
                                help="Helps to upload your file")
    user_id = fields.Many2one(comodel_name='res.users', string='Assigned to',
                              help="assigned to user")

    def action_import_task(self):
        """Creating task record using uploaded xl/csv files"""
        res_partner = self.env['res.partner']
        project_project = self.env['project.project']
        project_task = self.env['project.task']
        items = False
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
            datemode = workbook.datemode
            headers = sheet.row_values(0)  # list
            data = []
            for row_index in range(1, sheet.nrows):
                row = sheet.row_values(row_index)  # list
                data += [{k: v for k, v in zip(headers, row)}]
            items = data
        imported = 0
        row = 0
        info_msg = ""
        error_msg = ""
        for item in items:
            row += 1
            vals = {}
            if item.get('Title'):
                vals['name'] = item.get('Title')
            else:
                error_msg += "\n\tTitle missing in file! (row %d)" % row
                continue
            try:
                # MM/DD/YYYY is the format the sample template uses
                deadline = parse_date(item.get('Deadline'), datemode,
                                      ('%m/%d/%Y',))
            except ValueError:
                error_msg += ("\n\tInvalid Deadline (%s), use YYYY-MM-DD or "
                              "MM/DD/YYYY! (row %d)"
                              % (item.get('Deadline'), row))
                continue
            if deadline:
                vals['date_deadline'] = deadline
            # look both up before creating anything, so a row that is not
            # imported leaves no new project or partner behind
            project = partner = None
            if item.get('Project'):
                project = project_project.search(
                    [('name', '=', item.get('Project'))])
                if len(project) > 1:
                    error_msg += ("\n\tMultiple projects with name (%s) "
                                  "found! (row %d)"
                                  % (item.get('Project'), row))
                    continue
            if item.get('Customer'):
                partner = res_partner.search(
                    [('name', '=', item.get('Customer'))])
                if len(partner) > 1:
                    error_msg += ("\n\tMultiple partners with name (%s) "
                                  "found! (row %d)"
                                  % (item.get('Customer'), row))
                    continue
            if project is not None:
                if not project:
                    project = project_project.create({
                        'name': item.get('Project')
                    })
                    info_msg += ("\nCreated new project with name :%s"
                                 % item.get('Project'))
                vals['project_id'] = project.id
            if partner is not None:
                if not partner:
                    partner = res_partner.create({
                        'name': item.get('Customer')
                    })
                    info_msg += ("\nCreated new partner with name :%s"
                                 % item.get('Customer'))
                vals['partner_id'] = partner.id
            if item.get('Parent Task'):
                parent_task = project_task.search(
                    [('name', '=', item.get('Parent Task'))])
                if len(parent_task) > 1:
                    parent_task = parent_task[0]
                vals['parent_id'] = parent_task.id
            if self.user_id:
                vals['user_ids'] = [(6, 0, self.user_id.ids)]
            project_task.create(vals)
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
        if info_msg:
            info_msg = "\nInformation : %s" % info_msg
        msg = ("Imported %d records." % imported) + info_msg
        return {
            'effect': {
                'fadeout': 'slow',
                'message': msg,
                'type': 'rainbow_man',
            }
        }
