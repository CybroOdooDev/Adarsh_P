# -*- coding: utf-8 -*-
"""The quality agreement of transport contracts was removed: drop the tables
of its standard points and contract lines."""


def migrate(cr, version):
    cr.execute('DROP TABLE IF EXISTS pharma_transport_contract_quality_line')
    cr.execute('DROP TABLE IF EXISTS pharma_transport_quality_point')
