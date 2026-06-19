# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
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
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from odoo.tests.common import TransactionCase


class TestHrDepartmentChart(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestHrDepartmentChart, cls).setUpClass()

        cls.parent_dept = cls.env['hr.department'].create({
            'name': 'Parent Department',
        })
        cls.self_dept = cls.env['hr.department'].create({
            'name': 'Self Department',
            'parent_id': cls.parent_dept.id,
        })
        cls.child_dept = cls.env['hr.department'].create({
            'name': 'Child Department',
            'parent_id': cls.self_dept.id,
        })

    def test_get_child_dept(self):
        """Test fetching hierarchical parent, self, and children information"""
        res = self.env['hr.department'].get_child_dept(self.self_dept.id, 'hr.department')

        self.assertEqual(res['self'], 'Self Department')
        self.assertEqual(res['parent']['name'], 'Parent Department')
        self.assertEqual(res['parent']['id'], self.parent_dept.id)
        self.assertEqual(len(res['child']), 1)
        self.assertEqual(res['child'][0]['name'], 'Child Department')
        self.assertEqual(res['child'][0]['id'], self.child_dept.id)

    def test_create_is_parent_child(self):
        """Test is_parent_child calculation during department creation"""
        dept_standalone = self.env['hr.department'].create({
            'name': 'Standalone Department',
        })
        self.assertFalse(dept_standalone.is_parent_child)

        dept_with_parent = self.env['hr.department'].create({
            'name': 'Dept With Parent',
            'parent_id': self.parent_dept.id,
        })
        self.assertTrue(dept_with_parent.is_parent_child)

    def test_write_is_parent_child(self):
        """Test is_parent_child calculation during writing parent_id"""
        dept = self.env['hr.department'].create({
            'name': 'Standalone Department',
        })
        self.assertFalse(dept.is_parent_child)

        dept.write({
            'parent_id': self.parent_dept.id,
        })
        self.assertTrue(dept.is_parent_child)