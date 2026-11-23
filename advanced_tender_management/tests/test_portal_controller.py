# -*- coding: utf-8 -*-
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.advanced_tender_management.controllers.portal import PortalController

from .common import TenderManagementTestCommon


@tagged('post_install', '-at_install')
class TestPortalController(TenderManagementTestCommon):
    """Tests for portal tender page controller."""

    def test_portal_my_tenders_renders_current_vendor_bids(self):
        tender = self.create_tender()
        bid = self.create_bid(tender, self.vendor_1)
        self.create_bid(tender, self.vendor_2)
        portal_user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Vendor One',
            'login': 'vendor_one_portal@example.com',
            'partner_id': self.vendor_1.id,
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        dummy_request = SimpleNamespace(
            env=self.env(user=portal_user.id),
            render=lambda template, values: {'template': template, 'values': values},
        )

        with patch('odoo.addons.advanced_tender_management.controllers.portal.request', dummy_request):
            result = self.call_route(PortalController().portal_my_tenders)

        self.assertEqual(result['template'], 'advanced_tender_management.portal_my_tenders')
        self.assertEqual(result['values']['bid_records'], bid)
        self.assertEqual(result['values']['page_name'], 'tenders')
