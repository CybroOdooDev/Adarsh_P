# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#############################################################################
{
    'name': 'JTL FFN Merchant Connector',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Logistics',
    'summary': 'Full integration with JTL Fulfillment Network (FFN): products, stock, orders, tracking, returns, multi-warehouse',
    'author': 'Cybrosys Techno Solutions,Odoo Community Association (OCA)',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': "https://www.cybrosys.com",
    'depends': [
        'stock',
        'sale_stock',
        'delivery',
        'stock_delivery',
        'mail',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/jtl_ffn_security.xml',
        'security/ir.access.csv',
        'data/jtl_ffn_sequence.xml',
        'data/jtl_ffn_cron.xml',
        'views/jtl_ffn_config_views.xml',
        'views/jtl_ffn_warehouse_views.xml',
        'views/jtl_ffn_product_views.xml',
        'views/jtl_ffn_order_views.xml',
        'views/jtl_ffn_return_views.xml',
        'views/jtl_ffn_menu.xml',
    ],
    'images': ['static/description/banner.jpg'],
    'license': 'AGPL-3',
}
