from odoo.tests.common import TransactionCase


class TestHrContract(TransactionCase):

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

        cls.transfer.write({'state': 'transfer'})

    def test_create_contract_with_transfer(self):
        """Creating contract with transfer should mark transfer done"""

        contract = self.env['hr.contract'].create({
            'name': 'Transfer Contract',
            'employee_id': self.employee.id,
            'emp_transfer_id': self.transfer.id,
            'wage': 30000,
        })

        self.assertTrue(contract)

        self.transfer.invalidate_recordset()

        self.assertEqual(
            self.transfer.state,
            'done'
        )

    def test_create_contract_without_transfer(self):
        """Creating normal contract should not affect transfer"""

        transfer = self.transfer.copy({
            'state': 'transfer',
            'transfer_company_id': self.company_2.id
        })

        contract = self.env['hr.contract'].create({
            'name': 'Normal Contract',
            'employee_id': self.employee.id,
            'wage': 30000,
        })

        self.assertTrue(contract)

        transfer.invalidate_recordset()

        self.assertEqual(
            transfer.state,
            'transfer'
        )