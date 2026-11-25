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
class TestImportProduct(TestImportCommon):

    def test_import_product_template_csv(self):
        wizard = self.env['import.product.template'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Name,Internal Reference,Sales Price,Cost,Product Type\n"
                "New Product,NP-001,500,300,consu"),
        })
        wizard.action_import_product_template()

        product = self.env['product.template'].search(
            [('default_code', '=', 'NP-001')])
        self.assertTrue(product, "Product should be created")
        self.assertEqual(product.name, 'New Product')
        self.assertEqual(product.list_price, 500.0)
        self.assertEqual(product.standard_price, 300.0)
