# -*- coding: utf-8 -*-
{
    'name': 'Project Furnishing & Fit-Out Extension',
    'version': '20.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Extends standard Project with Property Types, Customer Address, Budget & Warranty Management',
    'description': """
Project Furnishing & Fit-Out Extension
======================================
Inherits Odoo's standard Project model (project.project) to support interior fit-out operations:
- Customer Site Address auto-populated from customer details
- Property Type Many2one with customizable presets (Villa, Penthouse, Commercial, Hospitality, Retail)
- Scheduled Date and Completion Date tracking
- Budget & Financials Tab (Estimated Budget, Total Quoted Revenue, Total Actual Cost, Profit Margin)
- Warranty & DLP Tab (Warranty toggle, start/expiry dates, retention money, retention release date, terms)
- Property Types Configuration menu under Project > Configuration
    """,
    'author': 'Surfaces Furnishing LLC',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'sale_management',
        'purchase',
        'mrp',
    ],
    'data': [
        'security/project_furnishing_security.xml',
        'security/ir.access.csv',
        'data/project_sequence_data.xml',
        'data/project_property_type_data.xml',
        'data/project_measurement_type_data.xml',
        'data/project_installation_team_data.xml',
        'views/project_property_type_views.xml',
        'views/project_measurement_type_views.xml',
        'views/project_installation_team_views.xml',
        'views/project_site_survey_views.xml',
        'views/project_installation_views.xml',
        'views/project_service_request_views.xml',
        'views/project_project_views.xml',
        'views/project_report_views.xml',
        'views/res_config_settings_views.xml',
        'views/project_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'web_icon': 'project_furnishing,static/description/icon.png',
}
