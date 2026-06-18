from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestEmployeeTransfer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_1 = cls.env['res.company'].create({
            'name': 'Company A',
        })

        cls.company_2 = cls.env['res.company'].create({
            'name': 'Company B',
        })

        cls.employee = cls.env['hr.employee'].create({
            'name': 'John Doe',
            'company_id': cls.company_1.id,
        })

        cls.transfer = cls.env['employee.transfer'].create({
            'employee_id': cls.employee.id,
            'transfer_company_id': cls.company_2.id,
        })

    def test_create_transfer_name(self):
        """Test overridden create()"""
        self.assertEqual(
            self.transfer.name,
            f"Transfer: {self.employee.name}"
        )

    def test_action_transfer(self):
        """Test transfer action"""
        self.transfer.action_transfer()

        self.assertEqual(
            self.transfer.state,
            'transfer'
        )

    def test_action_transfer_same_company(self):
        """Should raise error when transferring to same company"""

        transfer = self.env['employee.transfer'].create({
            'employee_id': self.employee.id,
            'transfer_company_id': self.company_1.id,
        })

        with self.assertRaises(UserError):
            transfer.action_transfer()

    def test_action_cancel_transfer(self):
        """Test cancel action"""

        self.transfer.action_cancel_transfer()

        self.assertEqual(
            self.transfer.state,
            'cancel'
        )

    def test_compute_transferred(self):
        """Test compute field"""

        self.transfer._compute_transferred()

        expected = (
            self.company_2 in self.env.user.company_ids
        )

        self.assertEqual(
            self.transfer.transferred,
            expected
        )