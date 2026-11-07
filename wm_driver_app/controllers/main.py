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
"""
Driver App REST API controllers.

Authentication:  Odoo 20's ``auth='bearer'``.
Every request must carry the header::

    Authorization: Bearer <api-key>

Drivers generate their personal key from:
    Settings → Users → (their account) → API Keys → New Key

The key resolves to the driver's ``res.users`` record.  Ownership checks
against ``wm.collection.order.driver_id`` (which is ``res.partner``) are
done via ``request.env.user.partner_id`` — the partner linked to the user.

Endpoints
---------
POST /driver/api/route/today
    Returns today's dispatched/in-progress collection orders for the
    authenticated driver.

POST /driver/api/stop/<order_id>/status
    Records a stop status event, idempotent via client_uuid.

GET  /driver/app
    Serves the installable PWA shell (HTML page).

GET  /driver/app/manifest.json, /driver/app/sw.js, /driver/app/dbs
    PWA manifest, service worker and database list used by the setup screen.
"""
import base64
import json
import logging
import math
import os
from datetime import datetime, time, timedelta

import psycopg2.errors
import pytz

from odoo import fields, http
from odoo.exceptions import AccessError
from odoo.http import request, router
from odoo.modules.module import get_module_path
from odoo.tools import BinaryBytes, config

_logger = logging.getLogger(__name__)

# Valid stop-level status transitions to ensure logical workflow progression
ALLOWED_STATUS_TRANSITIONS = {
    None: {'en_route', 'arrived', 'flagged'},
    'en_route': {'arrived', 'flagged'},
    'arrived': {'started', 'flagged'},
    'started': {'lifted', 'weighed', 'completed', 'flagged'},
    'lifted': {'weighed', 'completed', 'flagged'},
    'weighed': {'weighed', 'lifted', 'completed', 'flagged'},
    'flagged': {'en_route', 'arrived', 'started', 'lifted', 'weighed', 'completed', 'flagged'},
    'completed': set(),
}


class DriverAppController(http.Controller):

    @property
    def env(self):
        try:
            if request and hasattr(request, 'env') and request.env:
                return request.env
        except Exception:
            _logger.debug("No request environment available", exc_info=True)
        raise AttributeError("No active request environment")

    # ------------------------------------------------------------------
    # PWA shell
    # ------------------------------------------------------------------

    @http.route('/driver/app', type='http', auth='public', methods=['GET'], csrf=False)
    def driver_app_shell(self, **kwargs):
        """Serve the installable PWA shell.

        The shell never touches the browser session (a cross-site GET must
        not be able to log a backend user out): the PWA selects its database
        per request through the ``X-Odoo-Database`` header instead.
        """
        return request.render('wm_driver_app.driver_app_page', {})

    @http.route('/driver/app/dbs', type='jsonrpc', auth='none', methods=['POST'], csrf=False, cors='*')
    def list_databases(self, **kwargs):
        """Return list of available databases for the driver app.

        Honours the ``list_db`` server option: when database listing is
        disabled only the database this request is already bound to (session,
        single database or dbfilter) is returned.
        """
        if not config['list_db']:
            return {'databases': [request.db] if request.db else []}
        try:
            return {'databases': router.db_list(host=request.httprequest.environ.get('HTTP_HOST'))}
        except Exception:
            return {'databases': []}

    @http.route('/driver/app/manifest.json', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def pwa_manifest(self):
        """Serve the PWA web-app manifest."""
        manifest = {
            "id": "/driver/app",
            "name": "WM Driver App",
            "short_name": "Driver",
            "description": "Log collection stop statuses offline-first.",
            "scope": "/driver/app",
            "start_url": "/driver/app",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#090d16",
            "theme_color": "#10b981",
            "icons": [
                {"src": "/wm_driver_app/static/src/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/wm_driver_app/static/src/img/icon-512.png", "sizes": "512x512", "type": "image/png"},
                {"src": "/wm_driver_app/static/src/img/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        }
        return request.make_response(
            json.dumps(manifest, indent=2),
            headers=[('Content-Type', 'application/manifest+json')],
        )

    @http.route('/.well-known/assetlinks.json', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def assetlinks(self):
        """Serve Digital Asset Links for Android Trusted Web Activity (TWA) verification."""
        data = [{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "com.cybrosys.wmdriver",
                "sha256_cert_fingerprints": [],
            },
        }]
        return request.make_response(
            json.dumps(data, indent=2),
            headers=[('Content-Type', 'application/json')],
        )

    @http.route('/driver/app/sw.js', type='http', auth='public', methods=['GET'], csrf=False)
    def service_worker(self):
        """Serve the service worker from the module's static directory.

        The SW *must* be served from the /driver/app path (not from the
        /wm_driver_app/static/... URL) so that its scope covers the app.
        We use the Service-Worker-Allowed header to widen the scope, and
        read the real file from disk rather than querying ir.attachment
        (static files are never stored there).
        """
        sw_path = None
        module_path = get_module_path('wm_driver_app', display_warning=False)
        if module_path:
            sw_path = os.path.join(module_path, 'static', 'src', 'js', 'sw.js')
            if not os.path.isfile(sw_path):
                sw_path = None
        if sw_path:
            try:
                with open(sw_path, encoding='utf-8') as fh:
                    body = fh.read()
            except OSError:
                _logger.exception('Could not read service worker file at %s', sw_path)
                body = "// Service worker load error"
        else:
            _logger.warning('wm_driver_app: sw.js not found in the module directory')
            body = "// Service worker not found"
        return request.make_response(
            body,
            headers=[
                ('Content-Type', 'application/javascript'),
                ('Service-Worker-Allowed', '/driver/app'),
                ('Cache-Control', 'no-cache'),
            ],
        )

    # ------------------------------------------------------------------
    # Route: today's stops
    # ------------------------------------------------------------------

    @http.route('/driver/api/route/today', type='jsonrpc', auth='bearer', bearer_scope='rpc', methods=['POST'], cors='*', csrf=False)
    def today_route(self):
        """Return today's collection orders for the authenticated driver.

        Returns a JSON object with a ``stops`` list, each entry containing
        enough information for the PWA to render the stop card and action
        buttons without a second request.
        """
        # wm.collection.order.driver_id is a res.partner field (computed from
        # the route/vehicle assignment). API key auth gives us a res.users record;
        # bridge the gap via partner_id.
        if not (request.env.user.has_group('wm_base.group_wm_driver') or request.env.is_admin() or request.env.user.has_group('wm_base.group_wm_ops_manager')):
            raise AccessError(request.env._("Driver API access requires driver privileges."))

        driver_partner = request.env.user.partner_id

        # Determine user timezone and compute day boundaries in local time,
        # then convert to naive UTC datetimes for querying scheduled_start.
        user_tz_name = request.env.context.get('tz') or request.env.user.tz or 'UTC'
        try:
            user_tz = pytz.timezone(user_tz_name)
        except Exception:
            user_tz = pytz.utc

        today_date = fields.Date.context_today(request.env.user)
        start_local = datetime.combine(today_date, time.min)
        end_local = datetime.combine(today_date + timedelta(days=1), time.min)

        utc_start = user_tz.localize(start_local).astimezone(pytz.utc).replace(tzinfo=None)
        utc_end = user_tz.localize(end_local).astimezone(pytz.utc).replace(tzinfo=None)

        orders = request.env['wm.collection.order'].search([
            ('driver_id', '=', driver_partner.id),
            ('scheduled_start', '>=', fields.Datetime.to_string(utc_start)),
            ('scheduled_start', '<', fields.Datetime.to_string(utc_end)),
            # 'missed' is included so a stop the driver flagged stays on the
            # list and can still be resumed; it is not a terminal state here.
            ('state', 'in', ('dispatched', 'in_progress', 'missed')),
        ], order='scheduled_start asc')

        stops = []
        for order in orders:
            last_log = order.status_log_ids[-1:] if order.status_log_ids else None

            # Domain specified waste categories for this order
            domain_cats = order.collection_point_category_ids
            if not domain_cats:
                domain_cats = request.env['wm.waste.category'].search([])

            allowed_categories = []
            for cat in domain_cats:
                allowed_categories.append({
                    'category_id': cat.id,
                    'category_name': cat.display_name or cat.name,
                })

            lines_data = []
            for line in order.order_line_ids:
                lines_data.append({
                    'line_id': line.id,
                    'category_id': line.category_id.id if line.category_id else False,
                    'category_name': line.category_id.display_name or line.category_id.name if line.category_id else request.env._('Uncategorized'),
                    'estimated_weight': line.estimated_weight or 0.0,
                    'weight': line.weight or 0.0,
                })

            stops.append({
                'order_id': order.id,
                'name': order.name,
                'customer': order.partner_id.name if order.partner_id else '',
                'address': order.collection_point_id.display_name if order.collection_point_id else '',
                'collection_point_lat': order.collection_point_id.latitude if order.collection_point_id else 0.0,
                'collection_point_lng': order.collection_point_id.longitude if order.collection_point_id else 0.0,
                'scheduled_start': str(order.scheduled_start) if order.scheduled_start else None,
                'state': order.state,
                'last_status': last_log.status if last_log else None,
                'last_status_time': str(last_log.timestamp) if last_log else None,
                'lines': lines_data,
                'allowed_categories': allowed_categories,
            })

        # Reason codes travel with the route payload rather than on their own
        # endpoint: the app caches the route for offline use, so a driver who
        # flags a stop out of signal still has the list to pick from.
        missed_reasons = [
            {'reason_id': reason.id, 'reason_name': reason.display_name or reason.name}
            for reason in request.env['wm.missed.reason'].sudo().search([('active', '=', True)], order='name asc')
        ]
        return {'stops': stops, 'missed_reasons': missed_reasons}

    @staticmethod
    def _duplicate_client_uuid_response():
        """Rejection returned when an offline update's client_uuid is already
        used by a status log the caller does not own: the app drops it."""
        return {
            'error': 'duplicate_client_uuid',
            'message': request.env._("This update was already recorded with the same "
                                     "identifier and has been discarded."),
        }

    # ------------------------------------------------------------------
    # Route: log a stop status
    # ------------------------------------------------------------------

    @http.route('/driver/api/stop/<int:order_id>/status', type='jsonrpc', auth='bearer', bearer_scope='rpc', methods=['POST'], cors='*', csrf=False)
    def log_status(
        self, order_id,
        status=None,
        client_uuid=None,
        latitude=0.0,
        longitude=0.0,
        note='',
        photo=None,
        timestamp=None,
        line_weights=None,
        removed_category_ids=None,
        missed_reason_id=None,
    ):
        """Idempotent stop-status logger.

        Body parameters (JSON):
            status (str, required) – one of en_route / arrived / started /
                lifted / weighed / completed / flagged
            client_uuid (str, optional) – UUID generated on-device at the
                moment of the tap; used to de-duplicate retried syncs after
                a dropped connection.
            latitude / longitude (float) – GPS coordinates captured by the
                browser at the time of the tap.
            note (str) – free-text note; required when status is 'flagged'.
            missed_reason_id (int) – wm.missed.reason the stop is flagged
                under; required when status is 'flagged', since the flag marks
                the order missed.
            photo (str) – base64-encoded JPEG/PNG photo proof.
            timestamp (str) – ISO-8601 datetime from the client clock; server
                time is used if omitted.
            line_weights (list) – list of dicts with category_id and weight

        Returns:
            {log_id: int, duplicate: bool}
        """
        # wm.collection.order.driver_id is res.partner; bridge from res.users.
        if not (request.env.user.has_group('wm_base.group_wm_driver') or request.env.is_admin() or request.env.user.has_group('wm_base.group_wm_ops_manager')):
            raise AccessError(request.env._("Driver API access requires driver privileges."))

        driver_partner = request.env.user.partner_id

        # --- De-duplicate by client_uuid before doing anything else ----------
        # Scoped to this driver's own stops so another driver's log id is
        # never disclosed.
        if client_uuid:
            existing = request.env['wm.collection.order.status.log'].search(
                [('client_uuid', '=', client_uuid),
                 ('order_id.driver_id', '=', driver_partner.id)], limit=1,
            )
            if existing:
                _logger.debug(
                    'Driver app: duplicate submission for client_uuid=%s ignored (log_id=%s)',
                    client_uuid, existing.id,
                )
                return {'log_id': existing.id, 'duplicate': True}

        # --- Validate order ownership ----------------------------------------
        # A missing order and someone else's order give the same answer so the
        # existence of other drivers' orders is not disclosed.
        order = request.env['wm.collection.order'].browse(order_id)
        if not order.exists() or order.driver_id != driver_partner:
            raise AccessError(request.env._("This stop is not assigned to you."))

        # --- Reject a client_uuid already used by another driver -------------
        if client_uuid:
            # The uuid is globally unique on status logs: if another driver's
            # log already carries it, inserting would hit the unique
            # constraint. Reject it with the normal error shape (without
            # disclosing the other log) so the app drops the queued update.
            if request.env['wm.collection.order.status.log'].sudo().search_count(
                    [('client_uuid', '=', client_uuid)], limit=1):
                _logger.warning(
                    'Driver app: client_uuid=%s already used by another driver; '
                    'update from user %s rejected', client_uuid, request.env.user.id,
                )
                return self._duplicate_client_uuid_response()

        # --- Validate status --------------------------------------------------
        valid_statuses = dict(
            request.env['wm.collection.order.status.log']._fields['status'].selection
        ).keys()
        if status not in valid_statuses:
            return {
                'error': 'invalid_status',
                'valid': list(valid_statuses),
            }

        # --- Validate status lifecycle / transitions -------------------------
        last_log = order.status_log_ids[-1:] if order.status_log_ids else None
        current_status = last_log.status if last_log else None

        if order.state in ('completed', 'signed') or current_status == 'completed':
            return {
                'error': 'stop_already_completed',
                'message': request.env._("This stop has already been completed."),
            }
        # 'missed' is workable: the driver flagged this stop, and logging
        # anything other than another flag reopens it (see
        # wm.collection.order._resume_from_missed).
        if order.state not in ('dispatched', 'in_progress', 'missed'):
            return {
                'error': 'stop_not_active',
                'message': request.env._("This stop is not active (status: %s); updates can no longer be logged.", order.state),
            }

        allowed_next = ALLOWED_STATUS_TRANSITIONS.get(current_status)

        if allowed_next is not None and status not in allowed_next:
            return {
                'error': 'invalid_status_transition',
                'message': request.env._(
                    "Invalid status transition from '%(current)s' to '%(new)s'.",
                    current=current_status or 'not_started', new=status,
                ),
                'current_status': current_status,
                'allowed_statuses': sorted(list(allowed_next)),
            }

        # --- 'flagged' always requires a note and a reason -------------------
        # The flag marks the order missed, which feeds the missed-collection
        # reports, so it carries a reason code and not only free text.
        missed_reason = request.env['wm.missed.reason']
        if status == 'flagged':
            if not (note or '').strip():
                return {'error': 'note_required_for_flagged_status'}
            try:
                reason_id_int = int(missed_reason_id)
            except (ValueError, TypeError):
                reason_id_int = 0
            if not reason_id_int:
                return {
                    'error': 'missed_reason_required',
                    'message': request.env._("Choose a reason for flagging this stop."),
                }
            missed_reason = request.env['wm.missed.reason'].sudo().browse(reason_id_int)
            if not missed_reason.exists() or not missed_reason.active:
                return {
                    'error': 'invalid_missed_reason',
                    'message': request.env._("That reason is no longer available; pick another one."),
                }

        # --- Parse timestamp (client sends ISO-8601 string) ------------------
        parsed_ts = None
        if timestamp:
            try:
                parsed_ts = fields.Datetime.from_string(timestamp)
            except Exception:
                _logger.warning('Driver app: unparseable timestamp %r, using server time', timestamp)
        if parsed_ts:
            # A wrong device clock must not freeze or reorder the stop status:
            # future times are clamped to now; absurdly old ones are ignored.
            now_utc = fields.Datetime.now()
            if parsed_ts > now_utc + timedelta(minutes=5):
                _logger.warning('Driver app: timestamp %s is in the future, using server time', parsed_ts)
                parsed_ts = now_utc
            elif parsed_ts < now_utc - timedelta(days=30):
                _logger.warning('Driver app: timestamp %s is more than 30 days old, using server time', parsed_ts)
                parsed_ts = None

        # --- Decode photo if provided ----------------------------------------
        photo_binary = False
        if photo:
            try:
                photo_binary = base64.b64decode(photo) if isinstance(photo, str) else photo
                photo_binary = BinaryBytes(photo_binary)
            except Exception:
                _logger.warning('Driver app: could not decode photo for order %s', order_id)
                photo_binary = False

        # Validate coordinates before any write so a rejected update cannot
        # leave weight changes behind.
        try:
            latitude = float(latitude or 0.0)
            longitude = float(longitude or 0.0)
        except (ValueError, TypeError):
            return {'error': 'invalid_coordinates', 'message': request.env._("Latitude and longitude must be numbers.")}

        # Weight updates and the log insert run in one savepoint: should a
        # concurrent request insert the same client_uuid between the check
        # above and this insert, the unique violation is rolled back (weights
        # included) and the update is rejected instead of a server error.
        try:
            with request.env.cr.savepoint():
                # --- Update order line weights and category selection -----------------
                weighed_summary = []
                if status == 'weighed' and not isinstance(line_weights, list):
                    return {'error': 'weight_required', 'message': request.env._("Enter the weight of at least one waste category.")}
                if line_weights is not None and isinstance(line_weights, list) and status == 'weighed':
                    # Determine allowed categories for the collection point
                    allowed_category_ids = set(order.collection_point_category_ids.ids)
                    if not allowed_category_ids:
                        allowed_category_ids = set(request.env['wm.waste.category'].search([]).ids)

                    submitted_category_map = {}
                    for lw in line_weights:
                        if not isinstance(lw, dict):
                            return {'error': 'invalid_weight', 'message': request.env._("Invalid weight entry.")}
                        cat_id = lw.get('category_id')
                        w_val = lw.get('weight', 0.0)
                        try:
                            cat_id_int = int(cat_id)
                        except (ValueError, TypeError):
                            return {'error': 'invalid_category_id', 'message': request.env._("Invalid category ID: %s", cat_id)}

                        try:
                            w_float = float(w_val)
                        except (ValueError, TypeError):
                            return {'error': 'invalid_weight', 'message': request.env._("Weight must be a valid number, got: %s", w_val)}

                        if not math.isfinite(w_float) or w_float < 0:
                            return {'error': 'invalid_weight', 'message': request.env._("Weight must be a finite, non-negative number, got: %s", w_val)}

                        if cat_id_int not in allowed_category_ids:
                            return {'error': 'disallowed_category', 'message': request.env._("Category %s is not allowed for this collection point.", cat_id_int)}

                        submitted_category_map[cat_id_int] = w_float

                    if not any(w > 0 for w in submitted_category_map.values()):
                        return {'error': 'weight_required', 'message': request.env._("Enter the weight of at least one waste category.")}

                    # Categories the driver explicitly removed in the weighing modal are
                    # deleted (a leftover zero-weight line would block completion).
                    removed_ids = set()
                    if isinstance(removed_category_ids, list):
                        for rid in removed_category_ids:
                            try:
                                removed_ids.add(int(rid))
                            except (ValueError, TypeError):
                                return {'error': 'invalid_category_id', 'message': request.env._("Invalid category ID: %s", rid)}
                    removed_ids -= set(submitted_category_map)
                    if removed_ids and order.state in ('dispatched', 'in_progress', 'missed'):
                        order.order_line_ids.filtered(
                            lambda ln: ln.category_id.id in removed_ids
                        ).sudo().unlink()
                    # Any other category omitted from a (partial) weigh is kept with
                    # its estimate but loses its old confirmed weight.
                    order.order_line_ids.filtered(
                        lambda ln: ln.category_id.id not in submitted_category_map and ln.weight
                    ).write({'weight': 0.0})

                    # Update existing or create new order lines for submitted categories without deleting existing lines
                    for cat_id, w_float in submitted_category_map.items():
                        category = request.env['wm.waste.category'].browse(cat_id)
                        if not category.exists():
                            return {'error': 'category_not_found', 'message': request.env._("Category %s not found.", cat_id)}
                        existing_line = order.order_line_ids.filtered(lambda ln: ln.category_id.id == cat_id)
                        if existing_line:
                            # The driver weighs a category once: book it on one
                            # line, or several product lines would each carry it.
                            existing_line[0].write({'weight': w_float})
                            existing_line[1:].filtered('weight').write({'weight': 0.0})
                        else:
                            request.env['wm.collection.order.line'].create({
                                'order_id': order.id,
                                'category_id': cat_id,
                                'weight': w_float,
                            })
                        weighed_summary.append(f"{category.display_name or category.name}: {w_float} kg")

                if weighed_summary and status == 'weighed':
                    weight_note = "Weighed: " + ", ".join(weighed_summary)
                    note = f"{note}\n{weight_note}" if note else weight_note

                # --- Create the log entry via the shared helper ----------------------
                # Pass the res.users record — log_stop_event uses driver.id for driver_id
                # on wm.collection.order.status.log, which IS res.users (not res.partner).
                # client_uuid is set at creation (via the context default, as the
                # shared helper takes no extra vals) so retries are de-duplicated.
                StatusLog = request.env['wm.collection.order.status.log']
                if client_uuid:
                    StatusLog = StatusLog.with_context(default_client_uuid=client_uuid)
                log = StatusLog.log_stop_event(
                    order=order,
                    status=status,
                    driver=request.env.user,
                    timestamp=parsed_ts,
                    latitude=latitude,
                    longitude=longitude,
                    note=note or '',
                    photo=photo_binary,
                    missed_reason=missed_reason or None,
                    location_source='device',
                )
        except psycopg2.errors.UniqueViolation:
            if not client_uuid:
                raise
            _logger.warning(
                'Driver app: unique violation on client_uuid=%s; update rejected',
                client_uuid,
            )
            return self._duplicate_client_uuid_response()

        return {'log_id': log.id, 'duplicate': False}
