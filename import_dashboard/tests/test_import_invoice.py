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
class TestImportInvoice(TestImportCommon):

    def test_import_invoice_csv(self):
        # headers matching HEADER_MAP in import_invoice.py
        wizard = self.env['import.invoice'].create({
            'file_type': 'csv',
            'file': self.encode_file(
                "Partner,Number,Product,Quantity,Price\n"
                "Test Partner,INV-TEST-01,Test Product,10,150"),
            'type': 'out_invoice',
            'order_number': 'from_file',
            'import_product_by': 'name',
        })
        wizard.action_import_invoice()

        invoice = self.env['account.move'].search(
            [('name', '=', 'INV-TEST-01')])
        self.assertTrue(invoice, "Invoice should be created")
        self.assertEqual(invoice.partner_id.id, self.partner.id)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        line = invoice.invoice_line_ids[0]
        self.assertEqual(line.product_id.id, self.product.id)
        self.assertEqual(line.quantity, 10)
        self.assertEqual(line.price_unit, 150)
