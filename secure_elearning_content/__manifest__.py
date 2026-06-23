# -*- coding: utf-8 -*-
{
    'name': 'eLearning Security (Anti-Screenshot)',
    'version': '19.0.1.0.0',
    'category': 'Website/eLearning',
    'summary': 'Deter screenshots, screen recording, and copying of elearning contents.',
    'description': """
        This module adds client-side security measures to website elearning to prevent
        unauthorized copying, right-clicking, and common screenshot techniques.
    """,
    'author': 'Cybrosys Technologies',
    'website': 'https://www.cybrosys.com',
    'license': 'LGPL-3',
    'depends': ['website_slides'],
    'data': [],
    'assets': {
        'web.assets_frontend': [
            'website_slides_security/static/src/css/website_slides_protection.css',
            'website_slides_security/static/src/js/website_slides_protection.js',
            'website_slides_security/static/src/js/website_slides_protection_window.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
