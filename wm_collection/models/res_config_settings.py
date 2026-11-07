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
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """Extends Settings with waste collection workflow, dispatch, sorting and inventory parameters."""
    _inherit = 'res.config.settings'

    wm_auto_dispatch_enabled = fields.Boolean(
        string="Enable Auto-Dispatch of Ready Routes",
        config_parameter='wm_collection.auto_dispatch_enabled',
        default=False,
        help=(
            "When enabled, the hourly cron will automatically dispatch any "
            "route that is fully staffed (vehicle, driver, pre-trip checklist) "
            "and whose linked collection orders are all complete.\n\n"
            "When disabled the cron still evaluates readiness and sets the "
            "'Ready to Dispatch' flag on the route, but a human dispatcher "
            "must press Dispatch Route manually."
        ),
    )
    use_missed_collection = fields.Boolean(
        string="Enable Missed Collections",
        config_parameter='wm_collection.use_missed_collection',
        help="Enable missed collection tracking, reason management, and retry workflows."
    )
    use_route_zones = fields.Boolean(
        string="Route Service Zones & Auto-Assignment",
        config_parameter='wm_collection.use_route_zones',
        help="Enable geographic service zones and daily automated assignment of collection orders to zoned routes."
    )
    use_facility_gate_entry = fields.Boolean(
        string="Facility Gate Entries & Intake Scales",
        config_parameter='wm_collection.use_facility_gate_entry',
        help="Enable facility scale gate entries, scale weights reconciliation, and intake management."
    )
    wm_map_tile_url = fields.Char(
        string="Map Tile Server URL",
        config_parameter='wm_collection.map_tile_url',
        default='https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        help="Custom tile server URL template for route maps. Defaults to OpenStreetMap."
    )
    wm_osrm_router_url = fields.Char(
        string="OSRM Routing Server URL",
        config_parameter='wm_collection.osrm_router_url',
        default='https://router.project-osrm.org/route/v1/driving',
        help="Custom OSRM routing server endpoint for street path calculations. Defaults to the public OSRM server."
    )
    use_batch_inspection = fields.Boolean(
        string="Batch Inspection",
        config_parameter='wm_collection.use_batch_inspection',
        help="Enable batch inspection functionality."
    )
    use_quality_grading = fields.Boolean(
        string="Quality Grading",
        config_parameter='wm_collection.use_quality_grading',
        help="Enable quality grading for waste batches."
    )
    use_hazardous_waste = fields.Boolean(
        string="Hazardous Waste Management",
        config_parameter='wm_collection.use_hazardous_waste',
        help="Enable hazardous waste tracking."
    )
    use_batch_labels = fields.Boolean(
        string="Batch Labels",
        config_parameter='wm_collection.use_batch_labels',
        default=False,
        help="Enable batch label printing."
    )
    use_batch_approval = fields.Boolean(
        string="Batch Approval Workflow",
        config_parameter='wm_collection.use_batch_approval',
        help="Require batch inspection approval before receiving into stock."
    )

    wm_sort_based_on = fields.Selection([
        ('material', 'Waste Material'),
        ('category_and_material', 'Waste Category and Material')
    ], string="Sort Based On", config_parameter='wm_collection.wm_sort_based_on', default='material')

    group_sort_by_material = fields.Boolean(
        "Sort by Material Group",
        implied_group='wm_collection.group_sort_by_material'
    )
    group_sort_by_category = fields.Boolean(
        "Sort by Category Group",
        implied_group='wm_collection.group_sort_by_category'
    )

    @api.onchange('wm_sort_based_on')
    def _onchange_wm_sort_based_on(self):
        """
        React to changes in the waste sorting basis setting (by category vs. by
        material) and clear conflicting sort configurations to maintain
        settings consistency.
        """
        if self.wm_sort_based_on == 'material':
            self.group_sort_by_material = True
            self.group_sort_by_category = False
        elif self.wm_sort_based_on == 'category_and_material':
            self.group_sort_by_material = False
            self.group_sort_by_category = True


    def get_values(self):
        """
        Load all collection module configuration parameters from
        ir.config_parameter into the settings form, ensuring operators see the
        currently active collection workflow options.
        """
        res = super().get_values()
        val_missed = self.env['ir.config_parameter'].sudo().get_bool('wm_collection.use_missed_collection')
        val_zones = self.env['ir.config_parameter'].sudo().get_bool('wm_collection.use_route_zones')
        val_gate = self.env['ir.config_parameter'].sudo().get_bool('wm_collection.use_facility_gate_entry', True)
        tile_url = self.env['ir.config_parameter'].sudo().get_str('wm_collection.map_tile_url', 'https://tile.openstreetmap.org/{z}/{x}/{y}.png')
        osrm_url = self.env['ir.config_parameter'].sudo().get_str('wm_collection.osrm_router_url', 'https://router.project-osrm.org/route/v1/driving')
        res.update(
            use_missed_collection=val_missed,
            use_route_zones=val_zones,
            use_facility_gate_entry=val_gate,
            wm_map_tile_url=tile_url,
            wm_osrm_router_url=osrm_url,
        )
        sort_mode = self.env['ir.config_parameter'].sudo().get_str('wm_collection.wm_sort_based_on', 'material')
        res.update(
            wm_sort_based_on=sort_mode,
            group_sort_by_material=(sort_mode == 'material'),
            group_sort_by_category=(sort_mode == 'category_and_material'),
        )
        return res

    def set_values(self):
        """
        Persist all collection module settings (batch defaults, zone
        restrictions, driver signature requirements) to ir.config_parameter
        when the user saves the settings form.
        """
        res = super().set_values()
        self.env['ir.config_parameter'].sudo().set_bool('wm_collection.use_missed_collection', self.use_missed_collection)
        self.env['ir.config_parameter'].sudo().set_bool('wm_collection.use_route_zones', self.use_route_zones)
        self.env['ir.config_parameter'].sudo().set_bool('wm_collection.use_facility_gate_entry', self.use_facility_gate_entry)
        self.env['ir.config_parameter'].sudo().set_str('wm_collection.map_tile_url',
            self.wm_map_tile_url or 'https://tile.openstreetmap.org/{z}/{x}/{y}.png')
        self.env['ir.config_parameter'].sudo().set_str('wm_collection.osrm_router_url',
            self.wm_osrm_router_url or 'https://router.project-osrm.org/route/v1/driving')
        menu_missed = self.env.ref('wm_collection.menu_wm_missed_collection', raise_if_not_found=False)
        if menu_missed:
            menu_missed.active = self.use_missed_collection

        menu_reason = self.env.ref('wm_collection.menu_wm_missed_reason', raise_if_not_found=False)
        if menu_reason:
            menu_reason.active = self.use_missed_collection

        menu_zone = self.env.ref('wm_collection.menu_wm_service_zone', raise_if_not_found=False)
        if menu_zone:
            menu_zone.active = self.use_route_zones

        menu_gate = self.env.ref('wm_collection.menu_wm_facility_gate_entry', raise_if_not_found=False)
        if menu_gate:
            menu_gate.active = self.use_facility_gate_entry

        # Sync scheduled action active status with settings
        cron_assign = self.env.ref('wm_collection.ir_cron_auto_assign_orders_to_routes', raise_if_not_found=False)
        if cron_assign:
            cron_assign.active = self.use_route_zones

        cron_dispatch = self.env.ref('wm_collection.ir_cron_auto_dispatch_ready_routes', raise_if_not_found=False)
        if cron_dispatch:
            cron_dispatch.active = self.wm_auto_dispatch_enabled

        cron_missed = self.env.ref('wm_collection.ir_cron_wm_missed_collection_weekly_review', raise_if_not_found=False)
        if cron_missed:
            cron_missed.active = self.use_missed_collection

        group_material = self.env.ref('wm_collection.group_sort_by_material', raise_if_not_found=False)
        group_category = self.env.ref('wm_collection.group_sort_by_category', raise_if_not_found=False)
        group_operator = self.env.ref('wm_base.group_wm_inventory_operator', raise_if_not_found=False)

        if group_operator and group_material and group_category:
            if self.wm_sort_based_on == 'category_and_material':
                group_operator.sudo().write({'implied_ids': [(4, group_category.id), (3, group_material.id)]})
            else:
                group_operator.sudo().write({'implied_ids': [(4, group_material.id), (3, group_category.id)]})

        # Sync menu visibility
        menu_inspection = self.env.ref('wm_collection.menu_wm_batch_inspection', raise_if_not_found=False)
        if menu_inspection:
            menu_inspection.active = self.use_batch_inspection

        report_label = self.env.ref('wm_collection.action_waste_batch_label', raise_if_not_found=False)
        if report_label:
            # Show or hide the label report in the batch Print menu
            report_label.binding_model_id = self.env['ir.model']._get('waste.batch').id if self.use_batch_labels else False
        return res
