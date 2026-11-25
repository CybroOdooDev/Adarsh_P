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
class TestImportPayment(TestImportCommon):

    def test_import_payment_csv(self):
        csv_content = ("Amount,Date,Journal,Customer/Vendor,Payment Type,"
                       "Number\n1000,2026-05-16,%s,Test Partner,Receive,"
                       "PAY/001" % self.journal.name)
        wizard = self.env['import.payment'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(csv_content),
        })
        wizard.action_import_payment()

        payment = self.env['account.payment'].search(
            [('name', '=', 'PAY/001')])
        self.assertTrue(payment, "Payment should be created")
        self.assertEqual(payment.amount, 1000)
        self.assertEqual(payment.partner_id.id, self.partner.id)
        self.assertEqual(payment.payment_type, 'inbound')
