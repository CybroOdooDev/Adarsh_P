# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
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

from odoo import fields, models

def _sync_group(env, enabled, group_xmlid):
    """Toggle a feature group on/off for all internal users."""
    group = env.ref(group_xmlid, raise_if_not_found=False)
    if not group:
        return
    if enabled:
        env.ref('base.group_user').sudo().write({'implied_ids': [(4, group.id)]})
    else:
        group.sudo().implied_by_ids.write({'implied_ids': [(3, group.id)]})
        group.sudo().write({'user_ids': [(5, 0, 0)]})


def sync_capa_menu_group(env, enabled):
    """Sync CAPA menu group and toggle menu active state."""
    _sync_group(env, enabled, 'pharmaceutical_erp.group_pharma_capa_management')
    capa_menu = env.ref('pharmaceutical_erp.menu_pharma_capas', raise_if_not_found=False)
    if capa_menu:
        capa_menu.sudo().write({'active': enabled})


class ResConfigSettings(models.TransientModel):
    """Configuration settings for the Pharmaceutical ERP module, allowing toggling of major features."""
    _inherit = 'res.config.settings'
    vendor_qualification = fields.Boolean(
        string='Enable Vendor Qualification',
        config_parameter='pharmaceutical_erp.vendor_qualification',
        help='Show Vendor Qualification menu and portal questionnaire workflow.',
    )
    enable_capa = fields.Boolean(
        string='Enable CAPA Management',
        config_parameter='pharmaceutical_erp.enable_capa',
        help='When enabled, a CAPA is auto-raised when a Deviation moves to '
             'Under Investigation. The CAPA menu becomes visible.',
    )
    enable_sop_training = fields.Boolean(
        string='Enable SOP &amp; Training Management',
        config_parameter='pharmaceutical_erp.enable_sop_training',
        help='Show SOP lifecycle and Training Records menus. '
             'When enabled, operators must have passed training to sign BMR steps.',
    )

    def set_values(self):
        """Overrides set_values to apply security group and menu visibility changes based on toggled features."""
        super().set_values()

        # Vendor Qualification group
        _sync_group(self.env, self.vendor_qualification,
                    'pharmaceutical_erp.group_vendor_qualification')

        # CAPA group
        sync_capa_menu_group(self.env, self.enable_capa)

        # SOP & Training group
        _sync_group(self.env, self.enable_sop_training,
                    'pharmaceutical_erp.group_pharma_sop_training_feature')
