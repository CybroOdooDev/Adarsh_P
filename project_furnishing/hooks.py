# -*- coding: utf-8 -*-


def _post_init_hook(env):
    """Ensure all companies have their Quality Inspection location initialized."""
    companies = env['res.company'].search([])
    for company in companies:
        company._get_furnishing_qc_location()
