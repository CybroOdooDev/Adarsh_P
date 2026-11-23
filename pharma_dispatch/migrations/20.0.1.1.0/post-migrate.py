# -*- coding: utf-8 -*-
"""Drop the quality agreement columns of the transport contract, which are
no longer used."""

OLD_COLUMNS = (
    'qa_temperature_control', 'qa_trained_drivers', 'qa_vehicle_cleaning',
    'qa_no_subcontracting', 'qa_incident_reporting', 'qa_right_to_audit',
)


def migrate(cr, version):
    for column in OLD_COLUMNS:
        cr.execute('ALTER TABLE pharma_transport_contract DROP COLUMN IF EXISTS %s' % column)
