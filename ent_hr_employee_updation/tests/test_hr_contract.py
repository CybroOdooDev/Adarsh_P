from odoo.tests.common import TransactionCase


class TestHrContractNoticePeriod(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.icp = cls.env['ir.config_parameter'].sudo()

    def test_get_default_notice_days_enabled(self):
        """Should return configured notice days"""

        self.icp.set_param(
            'ent_hr_employee_updation.notice_period',
            True
        )
        self.icp.set_param(
            'ent_hr_employee_updation.no_of_days',
            90
        )

        contract = self.env['hr.contract']

        self.assertEqual(
            contract._get_default_notice_days(),
            '90'  # get_param returns string
        )

    def test_get_default_notice_days_disabled(self):
        """Should return 0 when notice period disabled"""

        self.icp.set_param(
            'ent_hr_employee_updation.notice_period',
            False
        )

        contract = self.env['hr.contract']

        self.assertEqual(
            contract._get_default_notice_days(),
            0
        )

    def test_notice_days_default_on_create(self):
        """notice_days should use configured default"""

        self.icp.set_param(
            'ent_hr_employee_updation.notice_period',
            True
        )
        self.icp.set_param(
            'ent_hr_employee_updation.no_of_days',
            60
        )

        employee = self.env['hr.employee'].create({
            'name': 'Test Employee',
        })

        contract = self.env['hr.contract'].create({
            'name': 'Test Contract',
            'employee_id': employee.id,
            'wage': 30000,
        })

        self.assertEqual(contract.notice_days, 60)