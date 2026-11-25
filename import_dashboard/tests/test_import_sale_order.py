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
class TestImportSaleOrder(TestImportCommon):

    def _import(self, content, **values):
        wizard = self.env['import.sale.order'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(content),
            'order_number': 'from_file',
            'import_product_by': 'name',
            **values,
        })
        return wizard.action_import_sale_order()

    def _order(self, name):
        return self.env['sale.order'].search([('name', '=', name)])

    def test_import_sale_order_csv(self):
        self._import("Customer,Order Reference,Product,Quantity,Unit Price\n"
                     "Test Partner,SO-TEST-01,Test Product,5,200")

        sale_order = self._order('SO-TEST-01')
        self.assertTrue(sale_order, "Sale Order should be created")
        self.assertEqual(sale_order.partner_id.id, self.partner.id)
        self.assertEqual(len(sale_order.order_line), 1)
        self.assertEqual(sale_order.order_line[0].product_id.id,
                         self.product.id)
        self.assertEqual(sale_order.order_line[0].product_uom_qty, 5)
        self.assertEqual(sale_order.order_line[0].price_unit, 200)

    def test_import_by_internal_reference(self):
        """Products are matched on the Internal Reference column, not on the
        order number."""
        self._import("Customer,Order Reference,Product,Internal Reference,"
                     "Quantity,Unit Price\n"
                     "Test Partner,SO-TEST-02,Other Name,TEST_PROD,3,20",
                     import_product_by='default_code')

        line = self._order('SO-TEST-02').order_line
        self.assertEqual(line.product_id, self.product)

    def test_new_product_does_not_get_order_number(self):
        self._import("Customer,Order Reference,Product,Quantity,Unit Price\n"
                     "Test Partner,SO-TEST-03,Brand New Product,1,5")

        product = self._order('SO-TEST-03').order_line.product_id
        self.assertEqual(product.name, 'Brand New Product')
        self.assertFalse(product.default_code)

    def test_import_sale_sample_xlsx(self):
        """The shipped .xlsx sample template, with unit of measure and tax
        columns, can be imported."""
        wizard = self.env['import.sale.order'].create({
            'file_type': 'xlsx',
            'file_upload': self.encode_sample('Sale_Order_Template.xlsx'),
            'order_number': 'from_file',
            'import_product_by': 'name',
        })
        wizard.action_import_sale_order()

        # demo data may already hold an order S00008: check the line the
        # import added
        line = self._order('S00008').order_line.sorted('id')[-1:]
        self.assertEqual(line.product_uom_qty, 2)
        self.assertEqual(line.price_unit, 750)
        self.assertEqual(line.product_uom.name, 'Units')
        self.assertEqual(line.tax_id.name, 'Tax 15%')

    def test_reimport_keeps_prices_of_existing_lines(self):
        content = ("Customer,Order Reference,Product,Quantity,Unit Price\n"
                   "Test Partner,SO-TEST-04,Test Product,2,40")
        self._import(content)
        self._import(content)

        lines = self._order('SO-TEST-04').order_line.sorted('id')
        self.assertEqual(lines.mapped('price_unit'), [40, 40])
