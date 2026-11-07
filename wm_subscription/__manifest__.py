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
{
    'name': 'Waste Management Subscriptions',
    'version': '20.0.1.0.0',
    'category': 'Industries',
    'summary': 'Customer recurring subscription plans, weight quota allowances, and automatic billing runs',
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Technologies Pvt. Ltd.',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'support': 'odoo@cybrosys.com',
    'depends': [
        'account',
        'portal',
        'wm_base',
        'wm_contracts_billing',
    ],
    'data': [
        'security/ir.access.csv',
        'data/subscription_sequence.xml',
        'data/ir_cron.xml',
        'views/wm_subscription_plan_views.xml',
        'views/wm_subscription_views.xml',
        'views/wm_partner_contract_views.xml',
        'views/wm_portal_service_request_views.xml',
        'data/premium_menu_data.xml',
        'data/portal_entry_data.xml',
        'views/portal_subscription_templates.xml',
        'reports/subscription_report.xml',
        'reports/subscription_report_template.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'images': ['static/description/banner.jpg'],
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
    'price': 0.0,
    'currency': 'EUR',
}
