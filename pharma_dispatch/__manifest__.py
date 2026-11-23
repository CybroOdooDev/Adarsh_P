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
    'name': 'Pharmaceutical ERP — Dispatch & Transportation',
    'version': '20.0.1.5.0',
    'category': 'Inventory/Inventory',
    'summary': 'Shipments from delivery orders of QA-released batches: '
               'transporter, drivers, pre-loading checklist, temperature log, '
               'packing list, delivery challan and proof of delivery.',
    'description': """Dispatch and transportation of finished goods.""",
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'depends': [
        'mail',
        'stock',
        'product_expiry',
        'account',
        'pharmaceutical_base',
    ],
    'data': [
        'security/ir.access.csv',
        'data/pharma_shipment_data.xml',
        'views/pharma_dispatch_checklist_views.xml',
        'views/pharma_transport_contract_views.xml',
        'views/pharma_shipment_views.xml',
        'views/stock_picking_views.xml',
        'views/res_partner_views.xml',
        'views/menus.xml',
        'report/pharma_shipment_reports.xml',
        'report/report_packing_list.xml',
        'report/report_delivery_challan.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pharma_dispatch/static/src/scss/dispatch_checklist.scss',
        ],
    },
    'demo': [
        'demo/pharma_dispatch_checklist_demo.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
