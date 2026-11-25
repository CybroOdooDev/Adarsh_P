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
class TestImportPurchaseOrder(TestImportCommon):

    def _import(self, content, **values):
        wizard = self.env['import.purchase.order'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(content),
            'order_number': 'from_file',
            'import_product_by': 'name',
            **values,
        })
        return wizard.action_import_purchase_order()

    def _order(self, name):
        return self.env['purchase.order'].search([('name', '=', name)])

    def test_import_purchase_order_csv(self):
        self._import("Vendor,Order Reference,Product,Quantity,Unit Price\n"
                     "Test Partner,PO-TEST-01,Test Product,10,150")

        purchase_order = self._order('PO-TEST-01')
        self.assertTrue(purchase_order, "Purchase Order should be created")
        self.assertEqual(purchase_order.partner_id.id, self.partner.id)
        self.assertEqual(len(purchase_order.order_line), 1)
        self.assertEqual(purchase_order.order_line[0].product_qty, 10)
        self.assertEqual(purchase_order.order_line[0].price_unit, 150)

    def test_import_by_internal_reference(self):
        """Products are matched on the Internal Reference column, not on the
        order number."""
        self._import("Vendor,Order Reference,Product,Internal Reference,"
                     "Quantity,Unit Price\n"
                     "Test Partner,PO-TEST-02,Other Name,TEST_PROD,3,20",
                     import_product_by='default_code')

        line = self._order('PO-TEST-02').order_line
        self.assertEqual(line.product_id, self.product)

    def test_new_product_does_not_get_order_number(self):
        self._import("Vendor,Order Reference,Product,Quantity,Unit Price\n"
                     "Test Partner,PO-TEST-03,Brand New Product,1,5")

        product = self._order('PO-TEST-03').order_line.product_id
        self.assertEqual(product.name, 'Brand New Product')
        self.assertFalse(product.default_code)

    def test_missing_internal_reference_is_reported(self):
        result = self._import("Vendor,Order Reference,Product,Quantity\n"
                              "Test Partner,PO-TEST-04,Test Product,1",
                              import_product_by='default_code')

        message = self.env['import.message'].browse(result['res_id'])
        self.assertIn('Internal Reference missing', message.message)
        self.assertFalse(self._order('PO-TEST-04').order_line)

    def test_import_purchase_sample_xlsx(self):
        """The shipped .xlsx sample template can be imported."""
        wizard = self.env['import.purchase.order'].create({
            'file_type': 'xlsx',
            'file_upload': self.encode_sample('Purchase_Template.xlsx'),
            'order_number': 'from_file',
            'import_product_by': 'default_code',
        })
        wizard.action_import_purchase_order()

        # demo data may already hold an order P00020: check the line the
        # import added
        line = self._order('P00020').order_line.sorted('id')[-1:]
        self.assertEqual(line.product_id.default_code, 'FURN_6666')
        self.assertEqual(line.product_qty, 2)
        self.assertEqual(line.price_unit, 800)
        self.assertEqual(line.product_uom.name, 'Units')
        self.assertEqual(line.taxes_id.name, 'Tax 10%')

    def test_reimport_keeps_prices_of_existing_lines(self):
        """Importing an order again adds its lines, but does not change
        the price of the lines already on the order, even when the vendor
        has another price in its pricelist."""
        self.env['product.supplierinfo'].create({
            'partner_id': self.partner.id,
            'product_tmpl_id': self.product.product_tmpl_id.id,
            'price': 66,
            'delay': 4,
        })
        content = ("Vendor,Order Reference,Product,Quantity,Unit Price,"
                   "Receipt Date\n"
                   "Test Partner,PO-TEST-05,Test Product,3,70,11/30/2026")
        self._import(content)
        self._import(content)

        lines = self._order('PO-TEST-05').order_line.sorted('id')
        self.assertEqual(lines.mapped('price_unit'), [70, 70])

    def test_reimport_updates_changed_header_values(self):
        self._import("Vendor,Order Reference,Vendor Reference,Product,"
                     "Quantity,Unit Price\n"
                     "Test Partner,PO-TEST-06,REF-1,Test Product,1,10")
        self._import("Vendor,Order Reference,Vendor Reference,Product,"
                     "Quantity,Unit Price\n"
                     "Test Partner,PO-TEST-06,REF-2,Test Product,1,10")

        self.assertEqual(self._order('PO-TEST-06').partner_ref, 'REF-2')
