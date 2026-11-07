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
from odoo.tools import SQL


class WmDriverPerformanceReport(models.Model):
    """Reporting model for Driver Performance (_auto = False)."""
    _name = 'wm.driver.performance.report'
    _description = 'Driver Performance'
    _auto = False
    _order = 'date desc, driver_id'

    driver_id = fields.Many2one('res.partner', readonly=True)
    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    route_count = fields.Integer(readonly=True)
    total_orders = fields.Integer(readonly=True)
    completed_orders = fields.Integer(readonly=True)
    missed_orders = fields.Integer(readonly=True)

    completion_rate = fields.Float(string='Completion Rate (%)', readonly=True, aggregator='avg')
    missed_rate = fields.Float(string='Missed Rate (%)', readonly=True, aggregator='avg')

    def _read_group_select(self, table, aggregate_spec):
        """Grouped rates are total completed (or missed) / total orders, not a
        plain average of the per-day percentages."""
        rates = {'completion_rate:avg': 'completed_orders', 'missed_rate:avg': 'missed_orders'}
        if aggregate_spec in rates:
            return SQL(
                'COALESCE(SUM(%(part)s)::float / NULLIF(SUM(%(total)s), 0) * 100.0, 0.0)',
                part=table[rates[aggregate_spec]],
                total=table['total_orders'],
            )
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        """
        Create or replace SQL view for driver performance analysis.
        """
        self.env.cr.execute("""
            DROP VIEW IF EXISTS wm_driver_performance_report;
            CREATE OR REPLACE VIEW wm_driver_performance_report AS (
                SELECT
                    row_number() OVER () AS id,
                    driver_id,
                    CAST(COALESCE(scheduled_start, create_date) AS DATE) AS date,
                    company_id,
                    COUNT(DISTINCT route_id) AS route_count,
                    COUNT(id) AS total_orders,
                    COUNT(CASE WHEN state IN ('completed', 'signed', 'invoiced') THEN 1 END) AS completed_orders,
                    COUNT(CASE WHEN is_missed = TRUE OR state = 'missed' THEN 1 END) AS missed_orders,
                    CASE
                        WHEN COUNT(id) > 0 THEN
                            (COUNT(CASE WHEN state IN ('completed', 'signed', 'invoiced') THEN 1 END)::float / COUNT(id)::float) * 100.0
                        ELSE 0.0
                    END AS completion_rate,
                    CASE
                        WHEN COUNT(id) > 0 THEN
                            (COUNT(CASE WHEN is_missed = TRUE OR state = 'missed' THEN 1 END)::float / COUNT(id)::float) * 100.0
                        ELSE 0.0
                    END AS missed_rate
                FROM wm_collection_order
                WHERE driver_id IS NOT NULL
                GROUP BY
                    driver_id,
                    company_id,
                    CAST(COALESCE(scheduled_start, create_date) AS DATE)
            )
        """)
