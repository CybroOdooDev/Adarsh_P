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

from .spreadsheet import cell_text, open_workbook


class ImportPartner(models.TransientModel):
    """ Model for import partners """
    _name = 'import.partner'
    _description = 'Partner Import'

    file_type = fields.Selection(
        selection=[('csv', 'CSV File'), ('xlsx', 'XLSX File')],
        string='Import File Type', default='xlsx', help="File type")
    method = fields.Selection(
        selection=[('create_update', 'Create or Update Customer/Vendor'),
                   ('create', 'Create Customer/Vendor')],
        string='Import Method', default='create_update',
        help="Helps to choose the import Method")
    update_by = fields.Selection(selection=[('name', 'Name'),
                                            ('email', 'Email'),
                                            ('phone', 'Phone')],
                                 string='Update By', default='name',
                                 help="Update using the fields")
    is_customer = fields.Boolean(string='Is Customer', help="Is Customer")
    is_vendor = fields.Boolean(string='Is Vendor', help="Is Vendor")
    file_upload = fields.Binary(string="Upload File",
                                help="It helps to upload files")

    def action_import_partner(self):
        """Creating Partner record using uploaded xl/csv files"""
        res_partner = self.env['res.partner']
        res_users = self.env['res.users']
        res_country_state = self.env['res.country.state']
        res_country = self.env['res.country']
        res_partner_category = self.env['res.partner.category']
        if self.file_type == 'csv':
            try:
                csv_data = base64.b64decode(self.file_upload)
                data_file = io.StringIO(csv_data.decode("utf-8"))
                data_file.seek(0)
                csv_reader = csv.DictReader(data_file, delimiter=',')
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the "
                    "type and format of the file and try again!")
            items = csv_reader
        if self.file_type == 'xlsx':
            try:
                workbook = open_workbook(
                    file_contents=base64.b64decode(self.file_upload))
                sheet = workbook.sheet_by_index(0)
            except Exception:
                raise ValidationError(
                    "File not valid.\n\nPlease check the "
                    "type and format of the file and try again!")
            headers = sheet.row_values(0)  # list
            data = []
            for row_index in range(1, sheet.nrows):
                row = sheet.row_values(row_index)  # list
                data += [{k: v for k, v in zip(headers, row)}]
            items = data
        row = 0
        created = 0
        updated = 0
        error_msg = ""
        warning_msg = ""
        for item in items:
            # every partner column is text; Excel gives numbers as
            # floats (a zip code 12345 is read as 12345.0)
            item = {key: cell_text(value) for key, value in item.items()}
            row += 1
            vals = {}
            row_not_import_msg = "\nRow {rn} not imported.".format(rn=row)
            if item.get('Is company? (y/n)') in ['y', 'Y']:
                vals['company_type'] = 'company'
            else:
                vals['company_type'] = 'person'
                if item.get('Related Company'):
                    rel_company = res_partner.search(
                        [('name', '=', item['Related Company'])])
                    if len(rel_company) == 1:
                        vals['parent_id'] = rel_company.id
                    elif not rel_company:
                        warning_msg += (
                            "\nRelated Company (%s) not found! (row %d)"
                            % (item['Related Company'], row))
                    else:
                        warning_msg += (
                            "\nRelated Company not set for row %d: Multiple "
                            "partners with name (%s) found!"
                            % (row, item['Related Company']))
                if item.get('Job Position'):
                    vals['function'] = item['Job Position']
            name = item.get('Name') or item.get('Complete Name')
            if name:
                vals['name'] = str(name).strip()
            if item.get('Street'):
                vals['street'] = item['Street']
            if item.get('Street2'):
                vals['street2'] = item['Street2']
            if item.get('City'):
                vals['city'] = item['City']
            country = res_country
            if item.get('Country'):
                country = res_country.search(
                    [('name', '=ilike', item['Country'])], limit=1)
                if not country and len(item['Country']) == 2:
                    # the code column holds 2 characters: a longer value
                    # would be cut ('Atlantis' would find Austria, 'AT')
                    country = res_country.search(
                        [('code', '=ilike', item['Country'])], limit=1)
                if country:
                    vals['country_id'] = country.id
                else:
                    warning_msg += ("\nCountry (%s) not found! (row %d)"
                                    % (item['Country'], row))
            if item.get('State'):
                state_name = item['State']
                if country:
                    # state names are only unique within a country
                    # (Limburg is in Belgium and in the Netherlands)
                    country_state = res_country_state.search(
                        [('country_id', '=', country.id), '|',
                         ('name', '=ilike', state_name),
                         ('code', '=ilike', state_name)])
                    if not country_state:
                        country_state = res_country_state.create({
                            'name': state_name,
                            'code': state_name,
                            'country_id': country.id,
                        })
                elif item.get('Country'):
                    # the country was not found: do not guess its state
                    country_state = res_country_state
                    warning_msg += (
                        "\nState (%s) not set for row %d: its country was "
                        "not found!" % (state_name, row))
                else:
                    country_state = res_country_state.search(
                        [('name', '=ilike', state_name)])
                    if not country_state:
                        warning_msg += (
                            "\nState (%s) not found! Add its Country to "
                            "create it. (row %d)" % (state_name, row))
                if len(country_state) > 1:
                    warning_msg += (
                        "\nState not set for row %d: several states are "
                        "named (%s), add the Country to choose one!"
                        % (row, state_name))
                elif country_state:
                    vals['state_id'] = country_state.id
                    vals['country_id'] = country_state.country_id.id
            if item.get('Zip'):
                vals['zip'] = item['Zip']
            if item.get('Tax ID'):
                vals['vat'] = item['Tax ID']
            if item.get('Phone'):
                vals['phone'] = item['Phone']
            if item.get('Email'):
                vals['email'] = item['Email']
            if item.get('Website'):
                vals['website'] = item['Website']
            if item.get('Tags'):
                tags = item['Tags'].split(',')
                tag_list = []
                for tag in tags:
                    tag_list += [tag.strip()]
                tag_ids = res_partner_category.search(
                    [('name', 'in', tag_list)]).ids
                if not tag_ids:
                    tag_ids = []
                    for tag in tag_list:
                        tag_id = res_partner_category.create({
                            'name': tag
                        })
                        tag_ids += [tag_id.id]
                if tag_ids:
                    vals['category_id'] = tag_ids
            if item.get('Salesperson'):
                salesperson = res_users.search(
                    [('name', '=', item['Salesperson'])])
                if not salesperson:
                    warning_msg += ("\nSalesperson (%s) not found!(row %d)"
                                    % (item['Salesperson'], row))
                elif len(salesperson) > 1:
                    warning_msg += ("\nSalesperson not copied from row %d: "
                                    "Multiple Salespersons with name (%s) "
                                    "found!"
                                    % (row, item['Salesperson']))
                else:
                    vals['user_id'] = salesperson.id
            if self.method == 'create_update':
                if self.update_by == 'name':
                    name = item.get('Name') or item.get('Complete Name')
                    if name:
                        partner = res_partner.search([('name', '=',
                                                       name)])
                        if not partner:
                            res_partner.create(vals)
                            created += 1
                        elif len(partner) > 1:
                            error_msg += row_not_import_msg + (
                                    "\n\tMultiple Partners with name "
                                    "(%s) found!" % name)
                            continue
                        else:
                            partner.write(vals)
                            updated += 1
                    else:
                        error_msg += row_not_import_msg + (
                            "\n\tName missing!")
                        continue
                if self.update_by == 'email':
                    if item.get('Email'):
                        partner = res_partner.search([('email', '=',
                                                       item['Email'])])
                        if not partner:
                            if not vals.get('name'):
                                error_msg += row_not_import_msg + (
                                    "\n\tName missing!")
                                continue
                            else:
                                partner = res_partner.search(
                                    [('name', '=', vals['name'])])
                                if not partner:
                                    res_partner.create(vals)
                                    created += 1
                                elif len(partner) > 1:
                                    error_msg += row_not_import_msg + (
                                            "\n\t Multiple Partners with "
                                            "name (%s) found!"
                                            % name)
                                    continue
                                else:
                                    partner.write(vals)
                                    updated += 1
                        elif len(partner) > 1:
                            error_msg += row_not_import_msg + (
                                    "\n\tMultiple Partners with Email "
                                    "(%s) found!" % item['Email'])
                            continue
                        else:
                            partner.write(vals)
                            updated += 1
                    else:
                        error_msg += row_not_import_msg + (
                            "\n\tEmail missing!")
                        continue
                if self.update_by == 'phone':
                    if item.get('Phone'):
                        partner = res_partner.search([('phone', '=',
                                                       item['Phone'])])
                        if not partner:
                            if not vals.get('name'):
                                error_msg += row_not_import_msg + (
                                    "\n\tName missing!")
                                continue
                            else:
                                partner = res_partner.search(
                                    [('name', '=', vals['name'])])
                                if not partner:
                                    res_partner.create(vals)
                                    created += 1
                                elif len(partner) > 1:
                                    error_msg += row_not_import_msg + (
                                            "\n\tMultiple Partners with "
                                            "name (%s) found!"
                                            % name)
                                    continue
                                else:
                                    partner.write(vals)
                                    updated += 1
                        elif len(partner) > 1:
                            error_msg += row_not_import_msg + (
                                    "\n\tMultiple Partners with Phone "
                                    "(%s) found!" % item['Phone'])
                            continue
                        else:
                            partner.write(vals)
                            updated += 1
                    else:
                        error_msg += row_not_import_msg + (
                            "\n\tPhone missing!")
                        continue
            elif self.method == 'create':
                if vals.get('name'):
                    res_partner.create(vals)
                    created += 1
                else:
                    error_msg += row_not_import_msg + (
                        "\n\tName missing!")
                    continue
        if error_msg:
            error_msg = "\n\n⚠ Warning ⚠" + error_msg
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
        msg = (("Created %d records.\nUpdated %d records"
                % (created, updated)) + warning_msg)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': msg,
                'type': 'rainbow_man',
            }
        }
