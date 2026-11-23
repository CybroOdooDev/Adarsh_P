# -*- coding: utf-8 -*-
"""Expired transport contracts are now archived: archive the contracts that
expired before this version."""


def migrate(cr, version):
    cr.execute("UPDATE pharma_transport_contract SET active = FALSE WHERE state = 'expired'")
