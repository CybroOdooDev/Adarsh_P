# -*- coding: utf-8 -*-
###############################################################################
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
#    If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import io

from openpyxl import load_workbook

from odoo import fields, models
from odoo.exceptions import UserError


class ImportTenderProductLine(models.TransientModel):
    """Import tender product lines from an XLSX file.

    Columns: product, description, quantity. A row without description
    becomes a section. Unknown products are created."""
    _name = "import.tender.product.line"
    _description = 'Import Tender Product Line'

    file = fields.Binary(required=True, help='XLSX file with the product lines.')
    tender_id = fields.Many2one('tender.management', help='Tender receiving the lines.')

    def _read_rows(self):
        """Rows of every sheet of the file, without the header row."""
        try:
            workbook = load_workbook(io.BytesIO(self.file.content),
                                     read_only=True, data_only=True)
        except Exception as error:
            raise UserError(self.env._('Please upload a valid XLSX file.')) from error
        rows = []
        for sheet in workbook.worksheets:
            rows.extend(row for row in list(sheet.iter_rows(values_only=True))[1:]
                        if row and row[0])
        return rows

    def _prepare_line(self, row):
        """Values of the tender line for one row of the file."""
        name, description = row[0], row[1] if len(row) > 1 else None
        if not description:
            return {'name': name, 'display_type': 'line_section'}
        product = self.env['product.product'].search([('name', '=', name)], limit=1)
        if not product:
            product = self.env['product.product'].create({'name': name})
        quantity = row[2] if len(row) > 2 and row[2] else 1
        return {'product_id': product.id, 'name': description, 'product_qty': quantity}

    def action_import_tender_product_lines(self):
        """Add the lines of the file to the tender."""
        self.ensure_one()
        self.tender_id.tender_product_line_ids = [
            fields.Command.create(self._prepare_line(row)) for row in self._read_rows()]
