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
    'name': 'Pharmaceutical ERP',
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
        'theme_diwy',
        'mail',
        'mrp',
        'purchase',
        'stock',
        'purchase_stock',
        'account',
        'hr',
        'base_setup',
        'website',
        'product_expiry'
    ],
    'sequence': 50,
    'data': [
        'security/pharma_groups.xml',
        'security/ir.model.access.csv',
        'data/pharma_sequences_data.xml',
        'data/mail_template_data.xml',
        'data/pharma_cron_data.xml',
        'views/product_template_views.xml',
        'views/pharma_avl_views.xml',
        'views/pharma_qc_spec_line_views.xml',
        'views/pharma_qc_spec_views.xml',
        'views/mrp_bom_views.xml',
        'views/mrp_routing_views.xml',
        'views/pharma_vendor_qualification_response_views.xml',
        'views/pharma_vendor_qualification_views.xml',
        'views/pharma_questionnaire_question_views.xml',
        'views/pharma_questionnaire_views.xml',
        'views/pharma_portal_templates.xml',
        'views/pharma_sop_views.xml',
        'views/pharma_training_view.xml',
        'views/stock_lot_views.xml',
        'views/purchase_order_views.xml',
        'views/pharma_stock_picking_views.xml',
        'views/pharma_bmr_step_views.xml',
        'views/pharma_ipqc_result_views.xml',
        'views/pharma_bmr_views.xml',
        'views/mrp_production_views.xml',
        'views/pharma_qc_result_line_views.xml',
        'views/pharma_qc_test_order_views.xml',
        'views/pharma_oos_investigation_views.xml',
        'views/pharma_capa_views.xml',
        'views/pharma_deviation_views.xml',
        'reports/pharma_coa_report.xml',
        'views/pharma_coa_views.xml',
        'views/pharma_qa_release_views.xml',
        'views/audit_trail_views.xml',
        'views/res_config_settings_views.xml',
        'views/pharma_menus.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'pharmaceutical_erp/static/src/scss/primary_variables.scss',
        ],
        'web.assets_backend': [
            'pharmaceutical_erp/static/src/scss/backend_theme.scss',
            'pharmaceutical_erp/static/src/components/dashboard/dashboard.scss',
            'pharmaceutical_erp/static/src/components/dashboard/dashboard.js',
            'pharmaceutical_erp/static/src/components/dashboard/dashboard.xml',
        ],
    },
    'images': [''],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': True,
}
