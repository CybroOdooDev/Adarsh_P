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
from odoo.tests import tagged

from .common import TestImportCommon


@tagged('post_install', '-at_install')
class TestImportPricelist(TestImportCommon):

    def _supplier_info(self):
        return self.env['product.supplierinfo'].search([
            ('partner_id', '=', self.partner.id),
            ('product_tmpl_id', '=', self.product.product_tmpl_id.id),
        ])

    def test_import_product_pricelist_csv(self):
        wizard = self.env['import.product.pricelist'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Name,Product,Fixed Price\nTest Pricelist,Test Product,100"),
            'import_product_by': 'name',
            'product_pricelist_setting': 'basic',
        })
        wizard.action_import_product_pricelist()

        pricelist = self.env['product.pricelist'].search(
            [('name', '=', 'Test Pricelist')])
        self.assertTrue(pricelist, "Pricelist should be created")
        self.assertEqual(len(pricelist.item_ids), 1)
        self.assertEqual(pricelist.item_ids[0].fixed_price, 100)

    def test_import_vendor_pricelist_csv(self):
        wizard = self.env['import.vendor.pricelist'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Vendor,Product Template,Quantity,Price,Delivery Lead Time\n"
                "Test Partner,Test Product,10,80.5,7"),
        })
        wizard.action_import_vendor_pricelist()

        supplier_info = self._supplier_info()
        self.assertTrue(supplier_info,
                        "Vendor Pricelist (Supplier Info) should be created")
        self.assertEqual(supplier_info.price, 80.5)
        self.assertEqual(supplier_info.min_qty, 10)
        self.assertEqual(supplier_info.delay, 7)

    def test_import_vendor_pricelist_xlsx(self):
        """Excel numbers (floats) are stored, including the integer lead
        time."""
        wizard = self.env['import.vendor.pricelist'].create({
            'file_type': 'xls',
            'file_upload': self.encode_xlsx([
                ['Vendor', 'Product Template', 'Quantity', 'Price',
                 'Delivery Lead Time'],
                ['Test Partner', 'Test Product', 10, 80, 7],
            ]),
        })
        wizard.action_import_vendor_pricelist()

        supplier_info = self._supplier_info()
        self.assertEqual(supplier_info.min_qty, 10)
        self.assertEqual(supplier_info.price, 80)
        self.assertEqual(supplier_info.delay, 7)

    def test_import_vendor_pricelist_invalid_number(self):
        """A value that is not a number is reported for its row instead of
        failing the whole import."""
        wizard = self.env['import.vendor.pricelist'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Vendor,Product Template,Quantity,Price\n"
                "Test Partner,Test Product,ten,80"),
        })
        result = wizard.action_import_vendor_pricelist()

        self.assertFalse(self._supplier_info())
        self.assertEqual(result['res_model'], 'import.message')
        message = self.env['import.message'].browse(result['res_id'])
        self.assertIn("Invalid number in 'Quantity': ten", message.message)
