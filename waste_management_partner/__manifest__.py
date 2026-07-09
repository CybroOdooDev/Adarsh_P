# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################

{
    'name': 'Waste Management ERP',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'GMP-compliant pharmaceutical manufacturing — merged full module',
    'description': """
        A comprehensive, GMP-compliant Pharmaceutical ERP solution tailored for modern manufacturing and quality control.
        Key Features:
        - Manufacturing Execution: Automated Batch Manufacturing Records (BMR) and In-Process Quality Control (IPQC).
        - Quality Management (QMS): End-to-end tracking of Deviations, CAPAs, and Out of Specification (OOS) investigations.
        - Supply Chain & Quality: Vendor Qualification portal, Approved Vendor Lists (AVL), and QC Test Orders.
        - Compliance & Training: Standard Operating Procedure (SOP) lifecycle management and 
        automated employee training records.
    """,
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'depends': [
        'contacts',
        'mail',
        'product',
        'account'
    ],
    'sequence': -1,
    'data': [
        'security/ir.model.access.csv',
        'report/partner_contract_report.xml',
        'report/partner_contract_report_template.xml',
        'data/prodcut_category_waste.xml',
        'views/contract_line_views.xml',
        'views/res_partner_views.xml',
        'views/partner_contract_views.xml',
        'views/partner_contract_menu.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': True,
}
