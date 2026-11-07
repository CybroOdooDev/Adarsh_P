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
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..controllers import main
from ..controllers.main import DriverAppController


@tagged('post_install', '-at_install')
class TestDriverAppStatusTransitions(TransactionCase):
    """Test suite verifying driver app stop status lifecycle transition rules."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()

        cls.partner_customer = cls.env['res.partner'].create({
            'name': 'Customer Test Transition',
        })
        cls.driver_partner = cls.env['res.partner'].create({
            'name': 'Driver Transition Partner',
        })
        cls.driver_user = cls.env['res.users'].create({
            'name': 'Driver Transition User',
            'login': 'driver_transition_user',
            'partner_id': cls.driver_partner.id,
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('wm_base.group_wm_driver').id,
            ])],
        })

        cls.waste_cat = cls.env['wm.waste.category'].create({
            'name': 'Dry Recyclables Transition',
            'code': 'DRY-TR',
        })

        cls.collection_point = cls.env['wm.collection.point'].create({
            'name': 'Collection Point Transition',
            'partner_id': cls.partner_customer.id,
            'category_ids': [(6, 0, [cls.waste_cat.id])],
        })

        cls.route = cls.env['wm.route'].create({
            'name': 'Route Transition',
            'driver_id': cls.driver_partner.id,
        })

    def _create_order(self, name='Order TR'):
        order = self.env['wm.collection.order'].create({
            'name': name,
            'partner_id': self.partner_customer.id,
            'collection_point_id': self.collection_point.id,
            'route_id': self.route.id,
            'state': 'dispatched',
        })
        self.env['wm.collection.order.line'].create({
            'order_id': order.id,
            'category_id': self.waste_cat.id,
            'estimated_weight': 40.0,
            'weight': 0.0,
        })
        return order

    def _mock_request(self, user):
        mock_req = MagicMock()
        mock_req.env = self.env(user=user)
        return mock_req

    def test_01_initial_status_cannot_jump_to_completed_or_weighed(self):
        """From not-started, driver cannot jump straight to completed, weighed, or lifted."""
        order = self._create_order('Order Jump Test')
        mock_req = self._mock_request(self.driver_user)

        # Attempt to complete without starting
        with patch.object(main, 'request', mock_req):
            res_comp = self.controller.log_status(
                order_id=order.id,
                status='completed',
                client_uuid='uuid-tr-01-comp',
            )
        self.assertEqual(res_comp.get('error'), 'invalid_status_transition')

        # Attempt to weigh without starting
        with patch.object(main, 'request', mock_req):
            res_w = self.controller.log_status(
                order_id=order.id,
                status='weighed',
                client_uuid='uuid-tr-01-w',
                line_weights=[{'category_id': self.waste_cat.id, 'weight': 50.0}],
            )
        self.assertEqual(res_w.get('error'), 'invalid_status_transition')

        # Allowed initial status: en_route
        with patch.object(main, 'request', mock_req):
            res_ok = self.controller.log_status(
                order_id=order.id,
                status='en_route',
                client_uuid='uuid-tr-01-enroute',
            )
        self.assertTrue(res_ok.get('log_id'))

    def test_02_sequential_progression_lifecycle(self):
        """Sequential flow: en_route -> arrived -> started -> lifted -> weighed -> completed."""
        order = self._create_order('Order Lifecycle Test')
        mock_req = self._mock_request(self.driver_user)

        base_time = fields.Datetime.now()
        with patch.object(main, 'request', mock_req):
            # 1. en_route
            r1 = self.controller.log_status(order.id, status='en_route', client_uuid='u-seq-1', timestamp=str(base_time))
            self.assertTrue(r1.get('log_id'))

            # Disallowed jump from en_route to completed
            bad_comp = self.controller.log_status(order.id, status='completed', client_uuid='u-seq-bad1')
            self.assertEqual(bad_comp.get('error'), 'invalid_status_transition')

            # 2. arrived
            r2 = self.controller.log_status(order.id, status='arrived', client_uuid='u-seq-2', timestamp=str(base_time + timedelta(minutes=5)))
            self.assertTrue(r2.get('log_id'))

            # Disallowed jump from arrived to lifted
            bad_lift = self.controller.log_status(order.id, status='lifted', client_uuid='u-seq-bad2')
            self.assertEqual(bad_lift.get('error'), 'invalid_status_transition')

            # Disallowed transition backwards from arrived to en_route
            bad_enroute = self.controller.log_status(order.id, status='en_route', client_uuid='u-seq-bad-enroute')
            self.assertEqual(bad_enroute.get('error'), 'invalid_status_transition')

            # 3. started
            r3 = self.controller.log_status(order.id, status='started', client_uuid='u-seq-3', timestamp=str(base_time + timedelta(minutes=10)))
            self.assertTrue(r3.get('log_id'))

            # 4. lifted
            r4 = self.controller.log_status(order.id, status='lifted', client_uuid='u-seq-4', timestamp=str(base_time + timedelta(minutes=15)))
            self.assertTrue(r4.get('log_id'))

            # 5. weighed (first waste stream)
            r5 = self.controller.log_status(
                order.id, status='weighed', client_uuid='u-seq-5',
                timestamp=str(base_time + timedelta(minutes=20)),
                line_weights=[{'category_id': self.waste_cat.id, 'weight': 42.0}],
            )
            self.assertTrue(r5.get('log_id'))

            # 6. weighed again (multiple weighings allowed)
            r6 = self.controller.log_status(
                order.id, status='weighed', client_uuid='u-seq-6',
                timestamp=str(base_time + timedelta(minutes=22)),
                line_weights=[{'category_id': self.waste_cat.id, 'weight': 45.0}],
            )
            self.assertTrue(r6.get('log_id'))

            # 7. completed
            r7 = self.controller.log_status(order.id, status='completed', client_uuid='u-seq-7', timestamp=str(base_time + timedelta(minutes=25)))
            self.assertTrue(r7.get('log_id'))

            # Any subsequent status rejected once completed
            r8 = self.controller.log_status(order.id, status='started', client_uuid='u-seq-8')
            self.assertEqual(r8.get('error'), 'stop_already_completed')

    def test_03_flagged_status_requires_note_and_permits_resumption(self):
        """Flagged needs a note and a reason, marks the order missed, and can be resumed."""
        order = self._create_order('Order Flag Test')
        mock_req = self._mock_request(self.driver_user)
        base_time = fields.Datetime.now()
        reason = self.env.ref('wm_collection.missed_reason_access_issue')

        with patch.object(main, 'request', mock_req):
            # Arrive at customer
            self.controller.log_status(order.id, status='arrived', client_uuid='u-flag-1', timestamp=str(base_time))

            # Flag without note fails
            no_note = self.controller.log_status(order.id, status='flagged', note='', client_uuid='u-flag-2', missed_reason_id=reason.id)
            self.assertEqual(no_note.get('error'), 'note_required_for_flagged_status')

            # Flag without a reason fails too: the flag marks the order missed
            no_reason = self.controller.log_status(order.id, status='flagged', note='Gate locked by security', client_uuid='u-flag-2b')
            self.assertEqual(no_reason.get('error'), 'missed_reason_required')

            # Flag with note succeeds
            r_flag = self.controller.log_status(order.id, status='flagged', note='Gate locked by security', client_uuid='u-flag-3', timestamp=str(base_time + timedelta(minutes=2)), missed_reason_id=reason.id)
            self.assertTrue(r_flag.get('log_id'))

            # ... and the stop is now missed, under the reason the driver chose
            self.assertEqual(order.state, 'missed')
            self.assertTrue(order.is_missed)
            self.assertEqual(order.missed_reason_id, reason)
            self.assertEqual(order.missed_notes, 'Gate locked by security')
            self.assertTrue(order.missed_collection_id)
            # A kerbside flag reschedules nothing and notifies no customer;
            # that stays a dispatcher decision.
            self.assertFalse(order.retry_order_id)
            missed_record = order.missed_collection_id
            self.assertFalse(missed_record.customer_notified)

            # Gate unlocked: resume by starting collection work
            r_resume = self.controller.log_status(order.id, status='started', client_uuid='u-flag-4', timestamp=str(base_time + timedelta(minutes=10)))
            self.assertTrue(r_resume.get('log_id'))

            # Resuming withdraws the missed marking, record included
            self.assertEqual(order.state, 'in_progress')
            self.assertFalse(order.is_missed)
            self.assertFalse(order.missed_reason_id)
            self.assertFalse(order.missed_collection_id)
            self.assertFalse(missed_record.exists())
            # The flag itself survives in the status log, with its reason
            flag_log = order.status_log_ids.filtered(lambda ln: ln.status == 'flagged')
            self.assertEqual(len(flag_log), 1)
            self.assertEqual(flag_log.missed_reason_id, reason)
            self.assertEqual(flag_log.note, 'Gate locked by security')
