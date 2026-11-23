# -*- coding: utf-8 -*-
"""GDP training of transport personnel is no longer recorded: drop its
columns from the contacts."""


def migrate(cr, version):
    cr.execute('ALTER TABLE res_partner DROP COLUMN IF EXISTS gdp_training_date')
    cr.execute('ALTER TABLE res_partner DROP COLUMN IF EXISTS gdp_training_valid_until')
