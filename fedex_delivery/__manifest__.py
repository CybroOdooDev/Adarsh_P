{
    'name': 'FedEx Shipping Integration',
    'version': '19.0.1.0.0',
    'category': 'Operations/Inventory/Delivery',
    'summary': 'Custom FedEx Delivery Carrier Integration',
    'description': """
Custom FedEx Delivery Carrier Integration for Odoo 19.
Allows sending shipments to FedEx REST API, generating labels, and tracking packages.
    """,
    'author': 'Custom',
    'website': 'https://www.example.com',
    'depends': ['stock', 'delivery', 'stock_delivery'],
    'data': [
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
