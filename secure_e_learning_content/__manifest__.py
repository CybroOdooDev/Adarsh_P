# -*- coding: utf-8 -*-
{
    'name': 'E-Learning Content Protection',
    'version': '19.0.1.0.0',
    'category': 'eLearning',
    'summary': 'Prevent screenshots and screen recordings on eLearning course content',
    'description': """
        Slide Shield adds a configurable content-protection layer to Odoo eLearning.
        It overlays a dynamic invisible watermark + CSS/JS guards that make screen
        capture impractical.  Each course and individual slide can opt in or out.

        Protection techniques:
        - CSS pointer-events & user-select blocking
        - Visibility API + Page Lifecycle detection (tab-switch / screen-capture pause)
        - Canvas-fingerprint watermark injected over video/PDF viewers
        - Keyboard shortcut interception (PrtSc / Win+Shift+S / Cmd+Shift+3/4)
        - Fullscreen-API restriction on slide iframes
        - DevTools open detection (size heuristic)
        - Transparent overlay canvas that breaks most OS-level capture tools
        - Local Secure Streaming with dynamic HMAC-signed URLs, session binding, and range-request video chunking
    """,
    'author': 'Custom',
    'depends': ['website_slides'],
    'data': [
        'security/ir.model.access.csv',
        'security/shield_security.xml',
        'data/ir_cron.xml',
        'views/slide_channel_views.xml',
        'views/slide_slide_views.xml',
        'views/shield_video_session_views.xml',
        'views/shield_video_access_log_views.xml',
        'views/shield_menu_views.xml',
        'views/templates/shield_meta.xml',
        'views/templates/slide_fullscreen_shield.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'secure_e_learning_content/static/src/css/shield.css',
            'secure_e_learning_content/static/src/css/shield_video.css',
            'secure_e_learning_content/static/src/js/shield.js',
            'secure_e_learning_content/static/src/js/shield_video_player.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
