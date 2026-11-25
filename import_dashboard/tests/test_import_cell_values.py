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
"""Cell values: Excel dates (in both date systems), numeric product codes
read from Excel, and number columns holding text that is not a number."""
import base64
import datetime
import io

import xlwt

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TestImportCommon

DAY = datetime.date(2026, 11, 25)


@tagged('post_install', '-at_install')
class TestImportCellValues(TestImportCommon):

    def _xls_1904(self, rows):
        """A legacy .xls file saved with the 1904 date system (old Mac
        Excel), where the same date has a serial number 1462 days lower."""
        workbook = xlwt.Workbook()
        workbook.dates_1904 = True
        sheet = workbook.add_sheet('Sheet1')
        date_style = xlwt.easyxf(num_format_str='YYYY-MM-DD')
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if isinstance(value, datetime.date):
                    sheet.write(r, c, datetime.datetime.combine(
                        value, datetime.time()), date_style)
                else:
                    sheet.write(r, c, value)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return base64.b64encode(buffer.getvalue())

    def _message(self, action):
        """Text of the import.message dialog an import returned."""
        self.assertEqual(action.get('res_model'), 'import.message', action)
        return self.env['import.message'].browse(action['res_id']).message

    def _coded_product(self):
        return self.env['product.product'].create(
            {'name': 'Coded Product', 'default_code': '12345',
             'barcode': '5824693'})

    # Tasks: Deadline

    def _import_task(self, file_upload, file_type='csv'):
        wizard = self.env['import.task'].create(
            {'file_type': file_type, 'file_upload': file_upload})
        return wizard.action_import_task()

    def _task(self, name):
        return self.env['project.task'].search([('name', '=', name)])

    def test_task_deadline_from_excel_date_cell(self):
        self._import_task(self.encode_xlsx(
            [['Title', 'Deadline'], ['Excel Task', DAY]]), 'xls')
        self.assertEqual(self._task('Excel Task').date_deadline.date(), DAY)

    def test_task_deadline_from_1904_workbook(self):
        self._import_task(self._xls_1904(
            [['Title', 'Deadline'], ['Mac Task', DAY]]), 'xls')
        self.assertEqual(self._task('Mac Task').date_deadline.date(), DAY)

    def test_task_deadline_formats(self):
        """ISO dates and the template's MM/DD/YYYY are both read."""
        self._import_task(self.encode_file(
            "Title,Deadline\nIso Task,2026-11-25\nUs Task,11/25/2026"))
        self.assertEqual(self._task('Iso Task').date_deadline.date(), DAY)
        self.assertEqual(self._task('Us Task').date_deadline.date(), DAY)

    def test_task_invalid_deadline_is_reported(self):
        message = self._message(self._import_task(self.encode_file(
            "Project,Title,Deadline\nUnseen Project,Bad Task,someday")))
        self.assertIn('someday', message)
        self.assertFalse(self._task('Bad Task'))
        self.assertFalse(self.env['project.project'].search(
            [('name', '=', 'Unseen Project')]))

    # Product pricelist: dates and codes

    def _import_pricelist(self, file_upload, file_type='xlsx', **values):
        wizard = self.env['import.product.pricelist'].create({
            'file_type': file_type,
            'file_upload': file_upload,
            'import_product_by': 'name',
            'product_pricelist_setting': 'basic',
            **values,
        })
        return wizard.action_import_product_pricelist()

    def _pricelist_items(self, name):
        return self.env['product.pricelist'].search(
            [('name', '=', name)]).item_ids

    def test_pricelist_dates_from_excel_date_cells(self):
        self._import_pricelist(self.encode_xlsx(
            [['Name', 'Product', 'Fixed Price', 'Start_date', 'End_date'],
             ['Dated PL', 'Test Product', 100, DAY,
              datetime.datetime(2026, 12, 31, 18, 0)]]))
        item = self._pricelist_items('Dated PL')
        self.assertEqual(item.date_start, datetime.datetime(2026, 11, 25))
        self.assertEqual(item.date_end, datetime.datetime(2026, 12, 31, 18))

    def test_pricelist_dates_from_template_text(self):
        self._import_pricelist(self.encode_file(
            "Name,Product,Fixed Price,Start_date\n"
            "Text PL,Test Product,100,2026-08-28 07:32:33"), 'csv')
        self.assertEqual(self._pricelist_items('Text PL').date_start,
                         datetime.datetime(2026, 8, 28, 7, 32, 33))

    def test_pricelist_invalid_date_is_reported(self):
        message = self._message(self._import_pricelist(self.encode_file(
            "Name,Product,Fixed Price,Start_date\n"
            "Bad Date PL,Test Product,100,tomorrow"), 'csv'))
        self.assertIn('tomorrow', message)
        self.assertFalse(self._pricelist_items('Bad Date PL'))

    def test_pricelist_numeric_barcode(self):
        product = self._coded_product()
        self._import_pricelist(self.encode_xlsx(
            [['Name', 'Barcode', 'Fixed Price'],
             ['Barcode PL', 5824693, 100]]), import_product_by='barcode')
        self.assertEqual(self._pricelist_items('Barcode PL').product_tmpl_id,
                         product.product_tmpl_id)

    def test_pricelist_template_header_with_trailing_space(self):
        """The sample template's header is 'Internal Reference '."""
        product = self._coded_product()
        self._import_pricelist(self.encode_xlsx(
            [['Name', 'Internal Reference ', 'Fixed Price'],
             ['Code PL', 12345, 100]]), import_product_by='default_code')
        self.assertEqual(self._pricelist_items('Code PL').product_tmpl_id,
                         product.product_tmpl_id)

    def test_pricelist_sample_template_by_internal_reference(self):
        # the template's product; Odoo's demo data already has it
        product = self.env['product.product'].search(
            [('default_code', '=', 'E-COM11')])
        if not product:
            product = self.env['product.product'].create(
                {'name': 'Cabinet with Doors', 'default_code': 'E-COM11'})
        self._import_pricelist(
            self.encode_sample('Product_Pricelist_Template.xlsx'),
            import_product_by='default_code')
        item = self._pricelist_items('Test Price List')
        self.assertEqual(item.product_tmpl_id, product.product_tmpl_id)
        self.assertEqual(item.date_start,
                         datetime.datetime(2026, 8, 28, 7, 32, 33))

    # Sale and purchase orders: 1904 workbooks

    def test_sale_order_date_from_1904_workbook(self):
        wizard = self.env['import.sale.order'].create({
            'file_type': 'xlsx',
            'file_upload': self._xls_1904(
                [['Customer', 'Order Reference', 'Product', 'Quantity',
                  'Unit Price', 'Quotation Date'],
                 ['Test Partner', 'SO-1904', 'Test Product', 1, 10, DAY]]),
            'order_number': 'from_file',
            'import_product_by': 'name',
        })
        wizard.action_import_sale_order()
        order = self.env['sale.order'].search([('name', '=', 'SO-1904')])
        self.assertEqual(order.date_order.date(), DAY)

    def test_purchase_order_date_from_1904_workbook(self):
        wizard = self.env['import.purchase.order'].create({
            'file_type': 'xlsx',
            'file_upload': self._xls_1904(
                [['Vendor', 'Order Reference', 'Product', 'Quantity',
                  'Unit Price', 'Order Deadline'],
                 ['Test Partner', 'PO-1904', 'Test Product', 1, 10, DAY]]),
            'order_number': 'from_file',
            'import_product_by': 'name',
        })
        wizard.action_import_purchase_order()
        order = self.env['purchase.order'].search([('name', '=', 'PO-1904')])
        self.assertEqual(order.date_order.date(), DAY)

    # Numeric product codes read from Excel

    def test_invoice_numeric_internal_reference(self):
        product = self._coded_product()
        wizard = self.env['import.invoice'].create({
            'file_type': 'xlsx',
            'file': self.encode_xlsx(
                [['Partner', 'Number', 'Internal Reference', 'Quantity',
                  'Price'],
                 ['Test Partner', 'INV-CODE', 12345, 1, 10]]),
            'type': 'out_invoice',
            'order_number': 'from_file',
            'import_product_by': 'default_code',
        })
        wizard.action_import_invoice()
        invoice = self.env['account.move'].search(
            [('name', '=', 'INV-CODE')])
        self.assertEqual(invoice.invoice_line_ids.product_id, product)

    def _import_bom(self, file_upload, file_type='xls', **values):
        wizard = self.env['import.bill.of.material'].create({
            'file_type': file_type,
            'file_upload': file_upload,
            'bom_type': 'manufacture_this_product',
            'bom_component': 'add',
            **values,
        })
        return wizard.action_import_bom()

    def test_bom_numeric_internal_references(self):
        product = self._coded_product()
        component = self.env['product.product'].create(
            {'name': 'Coded Component', 'default_code': '678'})
        self._import_bom(self.encode_xlsx(
            [['Product', 'Product/Internal Reference', 'Quantity',
              'Components', 'Components/Internal Reference',
              'BoM Lines/Quantity'],
             ['Coded Product', 12345, 1, 'Coded Component', 678, 2]]))
        bom = self.env['mrp.bom'].search(
            [('product_tmpl_id', '=', product.product_tmpl_id.id)])
        self.assertTrue(bom, "the BoM is on the existing product 12345")
        self.assertEqual(bom.bom_line_ids.product_id, component)

    def test_bom_duplicate_product_is_reported(self):
        self.env['product.template'].create(
            [{'name': 'Twin Product'} for _i in range(2)])
        message = self._message(self._import_bom(self.encode_file(
            "Product,Quantity,Components,BoM Lines/Quantity\n"
            "Twin Product,1,New Component,2"), 'csv'))
        self.assertIn('Twin Product', message)
        self.assertFalse(self.env['product.product'].search(
            [('name', '=', 'New Component')]),
            "nothing is created for a row that is not imported")

    def test_bom_duplicate_component_is_reported(self):
        self.env['product.product'].create(
            [{'name': 'Twin Component'} for _i in range(2)])
        message = self._message(self._import_bom(self.encode_file(
            "Product,Quantity,Components,BoM Lines/Quantity\n"
            "Test Product,1,Twin Component,2"), 'csv'))
        self.assertIn('Twin Component', message)

    def test_product_template_numeric_internal_reference(self):
        wizard = self.env['import.product.template'].create({
            'file_type': 'xls',
            'file_upload': self.encode_xlsx(
                [['Name', 'Internal Reference', 'Sales Price'],
                 ['Numbered Product', 777, 5]]),
        })
        wizard.action_import_product_template()
        product = self.env['product.template'].search(
            [('name', '=', 'Numbered Product')])
        self.assertEqual(product.default_code, '777')

    # Text that is not a number

    def test_payment_invalid_amount_is_reported(self):
        wizard = self.env['import.payment'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                'Amount,Date,Journal,Customer/Vendor,Payment Type,Number\n'
                '"1,000",2026-11-25,%s,Test Partner,Receive,PAY/BAD'
                % self.journal.name),
        })
        message = self._message(wizard.action_import_payment())
        self.assertIn('1,000', message)
        self.assertFalse(self.env['account.payment'].search(
            [('name', '=', 'PAY/BAD')]))

    def test_pos_invalid_quantity_is_reported(self):
        wizard = self.env['import.pos.order'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Order Ref,Session,Responsible,Product,Quantity,Unit Price\n"
                "POS/BAD,%s,%s,Test Product,two,10"
                % (self.pos_session.name, self.env.user.name)),
        })
        with self.assertRaisesRegex(ValidationError, 'Row 1: .*two'):
            wizard.action_import_pos_order()

    def test_sale_order_invalid_quantity_is_reported(self):
        wizard = self.env['import.sale.order'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Customer,Order Reference,Product,Quantity,Unit Price\n"
                "Test Partner,SO-BAD,Test Product,lots,10"),
            'order_number': 'from_file',
            'import_product_by': 'name',
        })
        message = self._message(wizard.action_import_sale_order())
        self.assertIn('lots', message)
        self.assertFalse(self.env['sale.order'].search(
            [('name', '=', 'SO-BAD')]))

    def test_plain_numbers_still_import(self):
        """Number text Odoo understands ('1000', ' 2.5 ') is unchanged."""
        wizard = self.env['import.payment'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                'Amount,Date,Journal,Customer/Vendor,Payment Type,Number\n'
                ' 1000.50 ,2026-11-25,%s,Test Partner,Receive,PAY/OK'
                % self.journal.name),
        })
        wizard.action_import_payment()
        self.assertEqual(self.env['account.payment'].search(
            [('name', '=', 'PAY/OK')]).amount, 1000.5)
