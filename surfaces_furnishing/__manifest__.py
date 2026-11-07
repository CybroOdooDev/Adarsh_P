# -*- coding: utf-8 -*-
{
    'name': 'Surfaces Furnishing Management',
    'version': '20.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Interior Fit-Out, Furnishing, Site Surveys, Material Submittals & Snagging Management',
    'description': """
Surfaces Furnishing Management
==============================
A unified single-module solution tailored for interior furnishing and fit-out operations:
- End-to-end Project Management & Profitability Tracking
- Site Surveys & Dimensional Room Measurements (Flooring m², Skirting lm, Window drops)
- Material & Sample Submittals with Consultant Sign-Off
- Quotations with Room-by-Room BOQ Breakdown & Variation Orders
- Subcontractor and Supplier Procurement Management
- Pre-Installation Site Readiness Gates
- On-Site Snagging / Defect Punch-Lists with Photo Proof
- Warranty, DLP Retention Tracking & Maintenance Tickets
    """,
    'author': 'Surfaces Furnishing LLC',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'sale_management',
        'purchase',
        'stock',
    ],
    'data': [
        'security/surfaces_furnishing_security.xml',
        'security/ir.access.csv',
        'data/furnishing_sequence_data.xml',
        'data/furnishing_stage_data.xml',
        'data/furnishing_room_type_data.xml',
        'data/furnishing_snag_type_data.xml',
        'views/furnishing_stage_views.xml',
        'views/furnishing_room_type_views.xml',
        'views/furnishing_snag_type_views.xml',
        'views/furnishing_project_views.xml',
        'views/furnishing_site_survey_views.xml',
        'views/furnishing_material_submittal_views.xml',
        'views/furnishing_snag_views.xml',
        'views/furnishing_maintenance_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/product_template_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
