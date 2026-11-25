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
class TestImportPartner(TestImportCommon):

    def _import(self, content, **values):
        wizard = self.env['import.partner'].create({
            'file_type': 'csv',
            'method': 'create',
            'file_upload': self.encode_file(content),
            **values,
        })
        return wizard.action_import_partner()

    def test_import_partner_csv(self):
        self._import("Name,Email,Phone,Is company? (y/n)\n"
                     "Imported Partner,imported@example.com,987654321,y")

        partner = self.env['res.partner'].search(
            [('name', '=', 'Imported Partner')])
        self.assertTrue(partner, "Partner should be created")
        self.assertEqual(partner.email, 'imported@example.com')
        self.assertEqual(partner.phone, '987654321')
        self.assertEqual(partner.company_type, 'company')

    def test_import_partner_update(self):
        self._import("Name,Email,Phone\n"
                     "Test Partner,updated@example.com,111222333",
                     method='create_update', update_by='name')

        self.assertEqual(self.partner.email, 'updated@example.com')
        self.assertEqual(self.partner.phone, '111222333')

    def test_related_company_is_linked(self):
        company = self.env['res.partner'].create(
            {'name': 'Parent Co', 'is_company': True})
        self._import("Name,Related Company\nNew Contact,Parent Co")

        contact = self.env['res.partner'].search(
            [('name', '=', 'New Contact')])
        self.assertEqual(contact.parent_id, company)

    def test_unknown_related_company_keeps_existing_parent(self):
        """An unknown related company is reported and does not clear the
        company the contact already belongs to."""
        company = self.env['res.partner'].create(
            {'name': 'Parent Co', 'is_company': True})
        contact = self.env['res.partner'].create(
            {'name': 'Known Contact', 'parent_id': company.id})

        result = self._import("Name,Related Company\n"
                              "Known Contact,Missing Co",
                              method='create_update', update_by='name')

        self.assertEqual(contact.parent_id, company)
        self.assertIn('Related Company (Missing Co) not found',
                      result['effect']['message'])

    def test_ambiguous_related_company_is_reported(self):
        self.env['res.partner'].create([{'name': 'Twin Co'},
                                        {'name': 'Twin Co'}])
        result = self._import("Name,Related Company\nTwin Contact,Twin Co")

        contact = self.env['res.partner'].search(
            [('name', '=', 'Twin Contact')])
        self.assertTrue(contact, "The contact is still created")
        self.assertFalse(contact.parent_id)
        self.assertIn('Multiple partners with name (Twin Co)',
                      result['effect']['message'])

    def test_empty_file_returns_summary(self):
        """A file with only a header row still returns the import summary."""
        wizard = self.env['import.partner'].create({
            'file_type': 'xlsx',
            'method': 'create',
            'file_upload': self.encode_xlsx([['Name', 'Email']]),
        })
        result = wizard.action_import_partner()
        self.assertIn('Created 0 records', result['effect']['message'])

    def test_import_partner_sample_xlsx(self):
        """The shipped .xlsx sample template can be imported."""
        wizard = self.env['import.partner'].create({
            'file_type': 'xlsx',
            'method': 'create',
            'file_upload': self.encode_sample('Partner_Template.xlsx'),
        })
        wizard.action_import_partner()
        self.assertTrue(self.env['res.partner'].search(
            [('name', '=', 'Sukus'), ('is_company', '=', True)]))
