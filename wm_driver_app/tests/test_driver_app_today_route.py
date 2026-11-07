#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
#    For full details, see https://www.odoo.com/documentation/20.0/legal/licenses/licenses.html
#
#############################################################################
from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytz

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..controllers import main
from ..controllers.main import DriverAppController


@tagged('post_install', '-at_install')
class TestDriverAppTodayRouteTimezone(TransactionCase):
    """Test /driver/api/route/today day boundary conversions using user's timezone."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()

        cls.partner_customer = cls.env['res.partner'].create({
            'name': 'Customer Test Route TZ',
        })
        cls.collection_point = cls.env['wm.collection.point'].create({
            'name': 'Test Collection Point TZ',
            'partner_id': cls.partner_customer.id,
        })
        cls.waste_cat = cls.env['wm.waste.category'].create({
            'name': 'Organic Waste TZ',
            'code': 'ORG-TZ',
        })

        # Driver 1 in Asia/Kolkata (UTC +05:30)
        cls.driver_user_in = cls.env['res.users'].create({
            'name': 'Driver India User',
            'login': 'driver_in_user',
            'tz': 'Asia/Kolkata',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref('wm_base.group_wm_driver').id])],
        })

        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Test Brand TZ'})
        cls.vehicle_model = cls.env['fleet.vehicle.model'].create({
            'name': 'Test Truck TZ',
            'brand_id': brand.id,
        })
        cls.vehicle_in = cls.env['fleet.vehicle'].create({
            'license_plate': 'TZ-TRUCK-01',
            'model_id': cls.vehicle_model.id,
            'driver_id': cls.driver_user_in.partner_id.id,
        })
        cls.route_in = cls.env['wm.route'].create({
            'name': 'Test Route TZ IN',
            'date': fields.Date.today(),
            'vehicle_id': cls.vehicle_in.id,
            'driver_id': cls.driver_user_in.partner_id.id,
        })

    def _create_order(self, scheduled_start, scheduled_end=None, state='dispatched'):
        if not scheduled_end:
            scheduled_end = scheduled_start + timedelta(hours=1)
        return self.env['wm.collection.order'].create({
            'partner_id': self.partner_customer.id,
            'collection_point_id': self.collection_point.id,
            'route_id': self.route_in.id,
            'scheduled_start': fields.Datetime.to_string(scheduled_start),
            'scheduled_end': fields.Datetime.to_string(scheduled_end),
            'state': state,
            'order_line_ids': [(0, 0, {'category_id': self.waste_cat.id})],
        })

    def test_01_driver_in_india_timezone_boundaries(self):
        """Stops between 00:00 and 05:30 IST (which are previous day in UTC)
        must appear in today's route for a driver in Asia/Kolkata.
        Stops scheduled on tomorrow IST (even if late today in UTC) must be excluded.
        """
        tz = pytz.timezone('Asia/Kolkata')
        today_ist = fields.Date.context_today(self.driver_user_in)

        # 1. Stop at 02:00 IST today
        # In UTC, 02:00 IST = previous day 20:30 UTC
        local_0200 = datetime.combine(today_ist, time(2, 0, 0))
        utc_0200 = tz.localize(local_0200).astimezone(pytz.utc).replace(tzinfo=None)
        order_early_morning = self._create_order(utc_0200)

        # 2. Stop at 14:00 IST today
        # In UTC, 14:00 IST = today 08:30 UTC
        local_1400 = datetime.combine(today_ist, time(14, 0, 0))
        utc_1400 = tz.localize(local_1400).astimezone(pytz.utc).replace(tzinfo=None)
        order_afternoon = self._create_order(utc_1400)

        # 3. Stop at 23:30 IST today
        # In UTC, 23:30 IST = today 18:00 UTC
        local_2330 = datetime.combine(today_ist, time(23, 30, 0))
        utc_2330 = tz.localize(local_2330).astimezone(pytz.utc).replace(tzinfo=None)
        order_late_night = self._create_order(utc_2330)

        # 4. Stop at 23:00 IST yesterday
        # In UTC, 23:00 IST yesterday = yesterday 17:30 UTC -> MUST BE EXCLUDED
        local_yesterday = datetime.combine(today_ist - timedelta(days=1), time(23, 0, 0))
        utc_yesterday = tz.localize(local_yesterday).astimezone(pytz.utc).replace(tzinfo=None)
        order_yesterday = self._create_order(utc_yesterday)

        # 5. Stop at 01:00 IST tomorrow
        # In UTC, 01:00 IST tomorrow = today 19:30 UTC -> MUST BE EXCLUDED even though UTC date is today!
        local_tomorrow = datetime.combine(today_ist + timedelta(days=1), time(1, 0, 0))
        utc_tomorrow = tz.localize(local_tomorrow).astimezone(pytz.utc).replace(tzinfo=None)
        order_tomorrow = self._create_order(utc_tomorrow)

        # Ensure order driver_ids were computed
        self.assertEqual(order_early_morning.driver_id, self.driver_user_in.partner_id)

        # Mock request with driver_user_in
        mock_req = MagicMock()
        mock_req.env = self.env(user=self.driver_user_in)

        with patch.object(main, 'request', mock_req):
            res = self.controller.today_route()

        stop_order_ids = [stop['order_id'] for stop in res.get('stops', [])]

        # Early morning stop (02:00 IST) must be present
        self.assertIn(
            order_early_morning.id, stop_order_ids,
            "Early morning stop (02:00 IST / previous day in UTC) should be included in today's route for Asia/Kolkata"
        )
        # Midday stop (14:00 IST) must be present
        self.assertIn(
            order_afternoon.id, stop_order_ids,
            "Afternoon stop (14:00 IST) should be included in today's route"
        )
        # Late night stop (23:30 IST) must be present
        self.assertIn(
            order_late_night.id, stop_order_ids,
            "Late night stop (23:30 IST) should be included in today's route"
        )

        # Yesterday's stop must NOT be present
        self.assertNotIn(
            order_yesterday.id, stop_order_ids,
            "Yesterday's stop must NOT be included in today's route"
        )

        # Tomorrow's stop (01:00 IST tomorrow, even if still today in UTC) must NOT be present
        self.assertNotIn(
            order_tomorrow.id, stop_order_ids,
            "Tomorrow's stop (01:00 IST tomorrow) must NOT be included in today's route"
        )

    def test_02_fallback_to_utc_when_invalid_or_no_tz(self):
        """When user timezone is unset or invalid, fallback cleanly to UTC."""
        driver_user_notz = self.env['res.users'].create({
            'name': 'Driver No TZ User',
            'login': 'driver_notz_user',
            'tz': False,
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('wm_base.group_wm_driver').id])],
        })
        vehicle_notz = self.env['fleet.vehicle'].create({
            'license_plate': 'NOTZ-TRUCK-01',
            'model_id': self.vehicle_model.id,
            'driver_id': driver_user_notz.partner_id.id,
        })
        route_notz = self.env['wm.route'].create({
            'name': 'Test Route UTC',
            'date': fields.Date.today(),
            'vehicle_id': vehicle_notz.id,
            'driver_id': driver_user_notz.partner_id.id,
        })

        today_utc = fields.Date.today()
        # Today at 10:00 UTC
        utc_1000 = datetime.combine(today_utc, time(10, 0, 0))
        order_utc = self.env['wm.collection.order'].create({
            'partner_id': self.partner_customer.id,
            'collection_point_id': self.collection_point.id,
            'route_id': route_notz.id,
            'scheduled_start': fields.Datetime.to_string(utc_1000),
            'scheduled_end': fields.Datetime.to_string(utc_1000 + timedelta(hours=1)),
            'state': 'dispatched',
        })

        mock_req = MagicMock()
        mock_req.env = self.env(user=driver_user_notz)

        with patch.object(main, 'request', mock_req):
            res = self.controller.today_route()

        stop_order_ids = [stop['order_id'] for stop in res.get('stops', [])]
        self.assertIn(order_utc.id, stop_order_ids, "Should fall back gracefully to UTC and find today's order")
