# -*- coding: utf-8 -*-
import json

from odoo.tests import tagged

from .common import TenderManagementTestCommon


@tagged('post_install', '-at_install')
class TestResConfigSettings(TenderManagementTestCommon):
    """Tests for settings persistence."""

    def test_set_values_and_get_values_for_manual_approval_users(self):
        approver = self.env.ref('base.user_admin')
        settings = self.env['res.config.settings'].create({
            'auto_approval': False,
            'manual_approval_users_ids': [(
                6, 0, [approver.id]
            )],
        })

        settings.set_values()
        values = self.env['res.config.settings'].get_values()

        self.assertEqual(
            self.env['ir.config_parameter'].sudo().get_str(
                'advanced_tender_management.manual_approval_users_ids'
            ),
            json.dumps([approver.id]),
        )
        self.assertEqual(values['manual_approval_users_ids'], approver)

    def test_set_values_stores_empty_list_without_manual_users(self):
        settings = self.env['res.config.settings'].create({
            'manual_approval_users_ids': [(6, 0, [])],
        })

        settings.set_values()

        self.assertEqual(
            self.env['ir.config_parameter'].sudo().get_str(
                'advanced_tender_management.manual_approval_users_ids'
            ),
            '[]',
        )
