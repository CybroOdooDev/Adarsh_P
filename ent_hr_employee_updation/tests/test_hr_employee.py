from datetime import date, timedelta
from unittest.mock import patch
from odoo.tests.common import TransactionCase
from odoo import fields

class TestHrEmployee(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.employee = cls.env['hr.employee'].create({
            'name': 'John Doe',
            'work_email': 'john@test.com',
            'identification_id': 'ID123',
            'passport_id': 'PASS123',
        })

    def test_compute_joining_date(self):
        self.env['hr.contract'].create({
            'name': 'Contract 1',
            'employee_id': self.employee.id,
            'date_start': date(2024, 5, 1),
            'wage': 30000,
        })

        self.env['hr.contract'].create({
            'name': 'Contract 2',
            'employee_id': self.employee.id,
            'date_start': date(2024, 1, 1),
            'wage': 40000,
        })

        self.employee._compute_joining_date()

        self.assertEqual(
            self.employee.joining_date,
            date(2024, 1, 1)
        )

    def test_compute_joining_date_without_contract(self):
        employee = self.env['hr.employee'].create({
            'name': 'No Contract Employee',
        })

        employee._compute_joining_date()

        self.assertFalse(employee.joining_date)

    def test_onchange_spouse(self):
        relation = self.env.ref(
            'ent_hr_employee_updation.hr_employee_relation_spouse'
        )

        employee = self.env['hr.employee'].new({
            'name': 'Test Employee',
            'spouse_complete_name': 'Jane Doe',
            'spouse_birthdate': date(1995, 1, 1),
        })

        employee._onchange_spouse()

        self.assertEqual(len(employee.fam_ids), 1)

        family = employee.fam_ids[0]

        self.assertEqual(
            family.member_name,
            'Jane Doe'
        )

        self.assertEqual(
            family.relation_id,
            relation
        )

        self.assertEqual(
            family.birth_date,
            date(1995, 1, 1)
        )

    def test_onchange_spouse_without_birthdate(self):
        employee = self.env['hr.employee'].new({
            'spouse_complete_name': 'Jane Doe',
        })

        employee._onchange_spouse()

        self.assertFalse(employee.fam_ids)

    @patch('odoo.addons.mail.models.mail_mail.MailMail.send')
    def test_mail_reminder_for_id(self, mock_send):
        self.employee.write({
            'id_expiry_date':
                fields.Date.today() + timedelta(days=10),
        })

        self.employee.mail_reminder()

        self.assertTrue(mock_send.called)

    @patch('odoo.addons.mail.models.mail_mail.MailMail.send')
    def test_mail_reminder_for_passport(self, mock_send):
        self.employee.write({
            'passport_expiry_date':
                fields.Date.today() + timedelta(days=100),
        })

        self.employee.mail_reminder()

        self.assertTrue(mock_send.called)

    @patch('odoo.addons.mail.models.mail_mail.MailMail.send')
    def test_no_mail_before_id_threshold(self, mock_send):
        self.employee.write({
            'id_expiry_date':
                fields.Date.today() + timedelta(days=30),
        })

        self.employee.mail_reminder()

        self.assertFalse(mock_send.called)

    @patch('odoo.addons.mail.models.mail_mail.MailMail.send')
    def test_no_mail_before_passport_threshold(self, mock_send):
        self.employee.write({
            'passport_expiry_date':
                fields.Date.today() + timedelta(days=250),
        })

        self.employee.mail_reminder()

        self.assertFalse(mock_send.called)