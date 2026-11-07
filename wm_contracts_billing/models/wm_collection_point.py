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


class WmCollectionPoint(models.Model):
    """Billing actions on collection points (the billable-event model lives here)."""
    _inherit = 'wm.collection.point'

    def action_log_emergency_callout(self):
        """Ops-triggered action to quickly log an Emergency Callout billable event."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Log Emergency Callout'),
            'res_model': 'wm.billable.event',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_collection_point_id': self.id,
                'default_event_type': 'emergency_callout',
                'default_event_date': fields.Date.context_today(self),
                'default_quantity': 1.0,
            },
        }
