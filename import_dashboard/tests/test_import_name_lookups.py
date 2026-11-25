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
"""Records looked up by name: names that match nothing, or more than one
record, must be reported instead of crashing or being silently dropped."""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TestImportCommon


@tagged('post_install', '-at_install')
class TestImportNameLookups(TestImportCommon):

    def _message(self, action):
        """Text of the import.message dialog an import returned."""
        self.assertEqual(action.get('res_model'), 'import.message', action)
        return self.env['import.message'].browse(action['res_id']).message

    def _create_user(self, name, login):
        return self.env['res.users'].create({'name': name, 'login': login})

    # POS orders

    def _import_pos(self, responsible, customer=None):
        header = "Order Ref,Session,Responsible,Product,Quantity,Unit Price"
        row = "POS/L01,%s,%s,Test Product,1,10" % (self.pos_session.name,
                                                  responsible)
        if customer:
            header += ",Customer"
            row += "," + customer
        wizard = self.env['import.pos.order'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(header + "\n" + row),
        })
        return wizard.action_import_pos_order()

    def _pos_order(self):
        return self.env['pos.order'].search([('name', '=', 'POS/L01')])

    def test_pos_unknown_responsible_is_reported(self):
        with self.assertRaisesRegex(ValidationError, 'No Such User'):
            self._import_pos('No Such User')
        self.assertFalse(self._pos_order())

    def test_pos_duplicate_responsible_is_reported(self):
        self._create_user('Twin Cashier', 'twin1')
        self._create_user('Twin Cashier', 'twin2')
        with self.assertRaisesRegex(ValidationError, 'Twin Cashier'):
            self._import_pos('Twin Cashier')

    def test_pos_responsible_is_set(self):
        cashier = self._create_user('Single Cashier', 'single')
        self._import_pos('Single Cashier')
        self.assertEqual(self._pos_order().user_id, cashier)

    def test_pos_duplicate_customer_is_reported(self):
        self.env['res.partner'].create(
            [{'name': 'Twin Customer'} for _i in range(2)])
        with self.assertRaisesRegex(ValidationError, 'Twin Customer'):
            self._import_pos(self.env.user.name, customer='Twin Customer')

    # Attendances

    def test_attendance_duplicate_employee_is_reported(self):
        self.env['hr.employee'].create(
            [{'name': 'Twin Employee'} for _i in range(2)])
        wizard = self.env['import.attendance'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Employee,Check In,Check Out\n"
                "Twin Employee,2026-11-25 09:00:00,2026-11-25 17:00:00"),
        })
        with self.assertRaisesRegex(ValidationError, 'Twin Employee'):
            wizard.action_import_attendance()

    # Payments

    def _import_payment(self, journal, partner='Test Partner'):
        wizard = self.env['import.payment'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Amount,Date,Journal,Customer/Vendor,Payment Type,Number\n"
                "100,2026-11-25,%s,%s,Receive,PAY/L01" % (journal, partner)),
        })
        return wizard.action_import_payment()

    def _payment(self):
        return self.env['account.payment'].search([('name', '=', 'PAY/L01')])

    def test_payment_unknown_journal_is_reported(self):
        message = self._message(self._import_payment('No Such Journal'))
        self.assertIn('No Such Journal', message)
        self.assertFalse(self._payment())

    def test_payment_duplicate_journal_is_reported(self):
        self.env['account.journal'].create({
            'name': self.journal.name, 'type': 'bank', 'code': 'TWIN'})
        message = self._message(self._import_payment(self.journal.name))
        self.assertIn(self.journal.name, message)
        self.assertFalse(self._payment())

    def test_payment_duplicate_partner_is_reported(self):
        self.env['res.partner'].create(
            [{'name': 'Twin Vendor'} for _i in range(2)])
        message = self._message(
            self._import_payment(self.journal.name, partner='Twin Vendor'))
        self.assertIn('Twin Vendor', message)
        self.assertFalse(self._payment())

    def test_payment_journal_is_set(self):
        self._import_payment(self.journal.name)
        self.assertEqual(self._payment().journal_id, self.journal)

    # Tasks

    def _import_task(self, project, customer='Test Partner'):
        wizard = self.env['import.task'].create({
            'file_type': 'csv',
            'file_upload': self.encode_file(
                "Project,Title,Customer\n%s,Lookup Task,%s"
                % (project, customer)),
        })
        return wizard.action_import_task()

    def _task(self):
        return self.env['project.task'].search([('name', '=', 'Lookup Task')])

    def test_task_duplicate_project_is_reported(self):
        self.env['project.project'].create({'name': 'Test Project'})
        message = self._message(self._import_task('Test Project'))
        self.assertIn('Test Project', message)
        self.assertFalse(self._task())

    def test_task_duplicate_customer_is_reported(self):
        self.env['res.partner'].create(
            [{'name': 'Twin Client'} for _i in range(2)])
        message = self._message(
            self._import_task('Brand New Project', customer='Twin Client'))
        self.assertIn('Twin Client', message)
        self.assertFalse(self._task())
        # nothing is created for a row that is not imported
        self.assertFalse(self.env['project.project'].search(
            [('name', '=', 'Brand New Project')]))

    # Partners: country and state

    def _import_partner(self, content):
        wizard = self.env['import.partner'].create({
            'file_type': 'csv',
            'method': 'create',
            'file_upload': self.encode_file(content),
        })
        return wizard.action_import_partner()

    def _partner(self, name):
        return self.env['res.partner'].search([('name', '=', name)])

    def test_state_is_searched_in_the_country(self):
        """Limburg is a state of both Belgium and the Netherlands."""
        self._import_partner("Name,Country,State\nBelgian,Belgium,Limburg")
        partner = self._partner('Belgian')
        self.assertEqual(partner.country_id, self.env.ref('base.be'))
        self.assertEqual(partner.state_id, self.env.ref('base.state_be_2'))

    def test_state_of_another_country_is_not_used(self):
        """Punjab is only known in India: a Pakistani Punjab must not get
        India's."""
        self._import_partner("Name,Country,State\nLahori,Pakistan,Punjab")
        partner = self._partner('Lahori')
        self.assertEqual(partner.country_id, self.env.ref('base.pk'))
        self.assertEqual(partner.state_id.country_id, self.env.ref('base.pk'))

    def test_ambiguous_state_without_country_is_reported(self):
        action = self._import_partner("Name,State\nSomewhere,Limburg")
        partner = self._partner('Somewhere')
        self.assertTrue(partner, "the partner is still imported")
        self.assertFalse(partner.state_id)
        self.assertIn('Limburg', action['effect']['message'])

    def test_state_without_country_is_found(self):
        self._import_partner("Name,State\nGeorgian,Georgia")
        partner = self._partner('Georgian')
        self.assertEqual(partner.state_id, self.env.ref('base.state_us_11'))
        self.assertEqual(partner.country_id, self.env.ref('base.us'))

    def test_unknown_state_without_country_is_reported(self):
        action = self._import_partner("Name,State\nNowhere Man,Nowhereland")
        partner = self._partner('Nowhere Man')
        self.assertTrue(partner, "the partner is still imported")
        self.assertFalse(partner.state_id)
        self.assertIn('Nowhereland', action['effect']['message'])

    def test_unknown_country_is_reported(self):
        action = self._import_partner("Name,Country\nAtlantean,Atlantis")
        partner = self._partner('Atlantean')
        self.assertTrue(partner, "the partner is still imported")
        self.assertFalse(partner.country_id)
        self.assertIn('Atlantis', action['effect']['message'])

    def test_country_by_code(self):
        self._import_partner("Name,Country,State\nBrusselaar,BE,Limburg")
        partner = self._partner('Brusselaar')
        self.assertEqual(partner.country_id, self.env.ref('base.be'))
        self.assertEqual(partner.state_id, self.env.ref('base.state_be_2'))
