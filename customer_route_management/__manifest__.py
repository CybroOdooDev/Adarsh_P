# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is under the terms of the Odoo Proprietary License v1.0
#    (OPL-1) It is forbidden to publish, distribute, sublicense, or
#    sell copies of the Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
#    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
#    OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
#    THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#############################################################################
{
    'name': 'Customer Route Management',
    'version': '20.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Group customers into delivery routes and print route reports with their dues.',
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'support': 'odoo@cybrosys.com',
    'live_test_url': 'https://www.youtube.com/watch?v=tdu6iBP2N6Y',
    'depends': ['account'],
    'data': [
        'security/delivery_route_groups.xml',
        'security/ir.access.csv',
        'views/res_partner_views.xml',
        'views/delivery_route_views.xml',
        'views/route_line_views.xml',
        'report/delivery_route_reports.xml',
        'report/delivery_route_templates.xml',
        'wizard/route_report_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'customer_route_management/static/src/js/action_manager.js',
        ],
        'web.assets_tests': [
            'customer_route_management/static/tests/tours/customer_route_tour.js',
        ],
    },
    'images': ['static/description/banner.jpg'],
    'license': 'OPL-1',
    'price': 19.99,
    'currency': 'EUR',
    'application': True,
}
