# -*- coding: utf-8 -*-
################################################################################
#
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the
#    Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#    OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
################################################################################
{
    'name': 'Enterprise Open HRMS Company Transfer',
    'version': '18.0.1.0.1',
    'category': 'Human Resources',
    'summary': 'This module is used to transfer employee between companies',
    'description': 'Transferring employees between company is a basic thing in an '
                   'organization. Odoo lacks a provision for employee transfer. '
                   'This module gives a basic structure for employee transfer.'
                   'Make sure that your multi company is enabled.',
    'author': 'Cybrosys Techno solutions,Open HRMS',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.openhrms.com',
    'depends': ['hr_contract', 'ent_hr_employee_updation'],
    'data': [
        'security/ent_hr_employee_transfer_security.xml',
        'security/ir.model.access.csv',
        'views/employee_transfer_views.xml',
    ],
    'images': ['static/description/banner.jpg'],
    'live_test_url': 'https://youtu.be/Qva8kW6xn4c',
    'license': 'OPL-1',
    'installable': True,
    'auto_install': False,
    'application': True,
}
