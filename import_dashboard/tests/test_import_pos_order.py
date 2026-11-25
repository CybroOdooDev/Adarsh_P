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
import datetime

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TestImportCommon


@tagged('post_install', '-at_install')
class TestImportPosOrder(TestImportCommon):

    def _import(self, content, **values):
        wizard = self.env['import.pos.order'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(content),
            **values,
        })
        return wizard.action_import_pos_order()

    def _row(self, order_ref, product_column, product_value):
        return ("Order Ref,Session,Responsible,%s,Quantity,Unit Price\n"
                "%s,%s,%s,%s,2,50" % (product_column, order_ref,
                                      self.pos_session.name,
                                      self.env.user.name, product_value))

    def test_import_pos_order_csv(self):
        self._import(self._row('POS/001', 'Product', 'Test Product'))

        pos_order = self.env['pos.order'].search([('name', '=', 'POS/001')])
        self.assertTrue(pos_order, "POS Order should be created")
        self.assertEqual(len(pos_order.lines), 1)
        self.assertEqual(pos_order.lines[0].qty, 2)

    def test_import_by_product_code(self):
        """'Import order by' is used to find the product."""
        self._import(self._row('POS/002', 'Product Code', 'TEST_PROD'),
                     import_product_by='default_code')

        pos_order = self.env['pos.order'].search([('name', '=', 'POS/002')])
        self.assertEqual(pos_order.lines.product_id, self.product)

    def test_unknown_product_is_reported(self):
        with self.assertRaisesRegex(ValidationError, 'not found'):
            self._import(self._row('POS/003', 'Product', 'No Such Product'))

    def test_order_date_is_in_the_user_timezone(self):
        """The Order Date is the importing user's local time, stored in
        UTC."""
        self.env.user.tz = 'Asia/Kolkata'
        content = ("Order Ref,Session,Responsible,Order Date,Product,"
                   "Quantity,Unit Price\nPOS/004,%s,%s,2026-11-25 10:00:00,"
                   "Test Product,1,50" % (self.pos_session.name,
                                          self.env.user.name))
        wizard = self.env['import.pos.order'].with_context(
            tz='Asia/Kolkata').create({
                'file_type': 'csv',
                'file_upload': self.encode_file(content),
            })
        wizard.action_import_pos_order()

        pos_order = self.env['pos.order'].search([('name', '=', 'POS/004')])
        self.assertEqual(pos_order.date_order,
                         datetime.datetime(2026, 11, 25, 4, 30))
