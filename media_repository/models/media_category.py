# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MediaCategory(models.Model):
    _name = "media.category"
    _description = "Media Category"

    name = fields.Char(string="Name")
    