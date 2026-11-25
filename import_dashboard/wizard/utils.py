# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################
"""Helpers shared by the order import wizards."""


def changed_values(record, vals):
    """Return the items of ``vals`` that differ from the values ``record``
    already has.

    Writing a field triggers Odoo's recomputations even when the value is
    unchanged: writing the same vendor on a purchase order again makes Odoo
    recompute the prices of its existing lines from the vendor pricelist.
    Writing only what changed avoids that.
    """
    changed = {}
    for name, value in vals.items():
        field = record._fields[name]
        new_value = field.convert_to_record(
            field.convert_to_cache(value, record), record)
        if new_value != record[name]:
            changed[name] = value
    return changed
