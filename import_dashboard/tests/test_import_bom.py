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
class TestImportBom(TestImportCommon):

    def test_import_bom_csv(self):
        component = self.env['product.product'].create({
            'name': 'Component Product',
            'type': 'consu',
            'default_code': 'COMP_01'
        })
        wizard = self.env['import.bill.of.material'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Product,Quantity,Components,BoM Lines/Quantity\n"
                "Test Product,1,Component Product,5"),
            'bom_type': 'manufacture_this_product',
            'bom_component': 'add',
        })
        wizard.action_import_bom()

        bom = self.env['mrp.bom'].search(
            [('product_tmpl_id', '=', self.product.product_tmpl_id.id)])
        self.assertTrue(bom, "BOM should be created")
        self.assertEqual(len(bom.bom_line_ids), 1)
        self.assertEqual(bom.bom_line_ids[0].product_id.id, component.id)
        self.assertEqual(bom.bom_line_ids[0].product_qty, 5)
