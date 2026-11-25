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
from odoo import models


class IrModuleModule(models.Model):
    """ Inherit 'ir.module.module' to disable import options on uninstall """
    _inherit = 'ir.module.module'

    # Module name -> import_dashboard settings that depend on it
    _IMPORT_DASHBOARD_PARAMS = {
        'mrp': ['import_bom'],
        'point_of_sale': ['import_pos'],
        'hr_attendance': ['import_attendance'],
        'sale': ['import_sale'],
        'purchase': ['import_purchase_order', 'import_vendor_pricelist'],
        'account': ['import_invoice', 'import_payment'],
        'project': ['import_task'],
        'product': ['import_product_template'],
    }

    def button_uninstall(self):
        """When a module is uninstalled, disable the corresponding
        import option of the dashboard"""
        icp = self.env['ir.config_parameter'].sudo()
        for module in self:
            for param in self._IMPORT_DASHBOARD_PARAMS.get(module.name, []):
                icp.set_param('import_dashboard.%s' % param, False)
        return super().button_uninstall()
