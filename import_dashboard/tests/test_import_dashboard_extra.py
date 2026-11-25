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
from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TestImportCommon


@tagged('post_install', '-at_install')
class TestImportDashboardExtra(TestImportCommon):

    def test_config_parameter_validation(self):
        """Enabling an import whose module is not installed is refused."""
        mrp_module = self.env['ir.module.module'].search(
            [('name', '=', 'mrp')])
        if mrp_module:
            original_state = mrp_module.state
            try:
                mrp_module.write({'state': 'uninstalled'})
                with self.assertRaises(ValidationError):
                    self.env['ir.config_parameter'].create({
                        'key': 'import_dashboard.import_bom',
                        'value': 'True'
                    })
            finally:
                mrp_module.write({'state': original_state})

    def test_check_user_group(self):
        """check_user_group returns a key for every import."""
        res = self.env['ir.config_parameter'].check_user_group()
        for key in ('bill_of_material', 'pos', 'import_attendance',
                    'import_payment', 'import_task', 'import_sale',
                    'import_purchase', 'import_product_template',
                    'import_partner', 'import_invoice', 'import_pricelist',
                    'import_vendor_pricelist'):
            self.assertIn(key, res)

    def test_button_uninstall_resets_config(self):
        """Uninstalling a module turns its import setting off."""
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('import_dashboard.import_bom', 'True')

        mrp_module = self.env['ir.module.module'].search(
            [('name', '=', 'mrp')])
        if mrp_module:
            with patch('odoo.addons.base.models.ir_module.Module.'
                       'button_uninstall', return_value=True):
                mrp_module.button_uninstall()

            self.assertFalse(icp.get_param('import_dashboard.import_bom'))

    def test_wizard_validation_invalid_file(self):
        """Wizards raise ValidationError on invalid or corrupted files."""
        wizard_attendance_bad = self.env['import.attendance'].create({
            'file_type': 'csv',
            'file_upload': base64.b64encode(b'\xff\xfe\xff\xfe'),
        })
        with self.assertRaises(ValidationError):
            wizard_attendance_bad.action_import_attendance()

        wizard_partner_bad = self.env['import.partner'].create({
            'file_type': 'csv',
            'method': 'create',
            'file_upload': base64.b64encode(b'\xff\xfe\xff\xfe'),
        })
        with self.assertRaises(ValidationError):
            wizard_partner_bad.action_import_partner()

    def test_wizard_validation_missing_employee(self):
        """import.attendance raises ValidationError for unknown employees."""
        wizard = self.env['import.attendance'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Employee,Check In,Check Out\n"
                "Non Existent Employee,2026-05-16 08:00:00,"
                "2026-05-16 17:00:00"),
        })
        with self.assertRaises(ValidationError):
            wizard.action_import_attendance()

    def test_wizard_xls_import_mocked(self):
        """Legacy .xls files are read with xlrd."""
        mock_workbook = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.nrows = 2
        mock_sheet.row_values.side_effect = [
            ['Name', 'Email', 'Phone', 'Is company? (y/n)'],
            ['Excel Partner', 'excel@example.com', '999999', 'y']
        ]
        mock_workbook.sheet_by_index.return_value = mock_sheet

        with patch('xlrd.open_workbook', return_value=mock_workbook):
            wizard = self.env['import.partner'].create({
                'file_type': 'xlsx',
                'method': 'create',
                'file_upload': base64.b64encode(b'dummy excel data')
            })
            wizard.action_import_partner()

        partner = self.env['res.partner'].search(
            [('name', '=', 'Excel Partner')])
        self.assertTrue(
            partner, "Partner should have been created from mocked XLS data")
        self.assertEqual(partner.email, 'excel@example.com')
