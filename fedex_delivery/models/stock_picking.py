from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    number_of_packages = fields.Integer(
        string="Number of Packages",
        default=1,
        help="Specify the number of packages for FedEx shipping label generation."
    )
