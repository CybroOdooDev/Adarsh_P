# -*- coding: utf-8 -*-
"""Reason for Transport changed from a selection to free text: replace the
stored selection keys with the labels printed on the challan."""

LABELS = {
    'supply': 'Supply to Customer',
    'branch_transfer': 'Stock Transfer to Own Branch',
    'job_work': 'Job Work',
    'approval': 'Supply on Approval / Sample',
    'return': 'Return',
    'other': 'Other (not a supply)',
}


def migrate(cr, version):
    for key, label in LABELS.items():
        cr.execute("UPDATE pharma_shipment SET transport_reason = %s WHERE transport_reason = %s",
                   [label, key])
