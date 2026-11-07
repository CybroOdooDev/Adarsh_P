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

from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class WmSubscriptionPortal(CustomerPortal):
    """Customer portal pages for recurring subscriptions."""

    def _subscription_domain(self):
        """Subscriptions of the logged-in customer and of the contacts of their company."""
        return [('partner_id', 'child_of', request.env.user.commercial_partner_id.id)]

    def _get_own_subscription(self, sub_id):
        """
        Return the subscription (as superuser) when it belongs to the current
        customer, else an empty recordset. The portal pages read plans, sites
        and invoices that the customer has no direct access to, so the
        ownership check is done here before any sudo record is handed out.
        """
        sub = request.env['wm.subscription'].sudo().search(
            self._subscription_domain() + [('id', '=', sub_id)], limit=1)
        return sub

    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        values['has_subscription_module'] = True
        return values

    def _prepare_portal_counter_values(self, counter):
        if counter == 'subscription_count':
            return 'wm.subscription', self._subscription_domain(), 'sudo'
        return super()._prepare_portal_counter_values(counter)

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_subscriptions(self, page=1, **kw):
        """Render the customer's recurring subscriptions list."""
        Subscription = request.env['wm.subscription'].sudo()
        domain = self._subscription_domain()
        pager = portal_pager(
            url='/my/subscriptions',
            total=Subscription.search_count(domain),
            page=page,
            step=10,
        )
        subscriptions = Subscription.search(
            domain, order='create_date desc', limit=10, offset=pager['offset'])
        return request.render('wm_subscription.portal_my_subscriptions', {
            'subscriptions': subscriptions,
            'page_name': 'subscription',
            'pager': pager,
            'default_url': '/my/subscriptions',
        })

    @http.route(['/my/subscriptions/<int:sub_id>'], type='http', auth='user', website=True)
    def portal_my_subscription_detail(self, sub_id, **kw):
        """Render the detail page of one of the customer's subscriptions."""
        sub = self._get_own_subscription(sub_id)
        if not sub:
            return request.redirect('/my/subscriptions')
        return request.render('wm_subscription.portal_my_subscription_detail', {
            'subscription': sub,
            'page_name': 'subscription_detail',
        })

    @http.route(['/my/subscriptions/<int:sub_id>/cancel'], type='http', auth='user',
                website=True, methods=['POST'])
    def portal_my_subscription_cancel(self, sub_id, **kw):
        """
        Self-service cancellation. Cancelling cancels draft invoices, which is
        reserved to contract managers, so the customer's request is carried out
        as superuser once ownership is verified.
        """
        sub = self._get_own_subscription(sub_id)
        # Only a live subscription can be cancelled: a request on one that is
        # already cancelled/expired (or still a draft) is ignored, not an error page.
        if sub and sub.state in ('active', 'paused'):
            sub.action_cancel(reason=kw.get('reason') or request.env._("Cancelled via Customer Portal"))
        return request.redirect('/my/subscriptions/%s' % sub_id)

    @http.route(['/my/subscriptions/<int:sub_id>/pdf'], type='http', auth='user', website=True)
    def portal_my_subscription_pdf(self, sub_id, **kw):
        """Download the PDF summary of one of the customer's subscriptions."""
        sub = self._get_own_subscription(sub_id)
        if not sub:
            return request.redirect('/my/subscriptions')
        pdf_content, _report_format = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'wm_subscription.action_report_wm_subscription', [sub.id])
        return request.make_response(pdf_content, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf_content)),
            ('Content-Disposition', 'attachment; filename="Subscription_%s.pdf"' % sub.name),
        ])
