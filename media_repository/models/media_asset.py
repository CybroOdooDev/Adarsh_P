# -*- coding: utf-8 -*-
import base64
from odoo import api, fields, models

class MediaAsset(models.Model):
    _name = 'media.asset'
    _description = 'Media Assets store'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, string="Name", tracking=True)
    description = fields.Text(string="Description", tracking=True)
    media_type = fields.Selection(
        [('image', 'Image'), ('video', 'Video'), ('document', 'Document'),
         ('audio', 'Audio'), ('url', 'Url')],
        string="Media Type", tracking=True ,required = True
    )
    file = fields.Binary(string="File", attachment=True)
    file_name = fields.Char(
        string="Original File Name",
        tracking=True,
        readonly=True,
        help="Auto-filled from the uploaded file name. Clear the file to reset.",
    )
    file_size = fields.Float(
        string="File Size (MB)",
        compute='_compute_file_size',
        store=True,
        readonly=True,
        digits=(16, 3),
        tracking=True,
        help="File size in megabytes. Automatically computed when a file is uploaded.",
    )
    source_url = fields.Char(string="Source URL", tracking=True)
    category_id = fields.Many2one(
        comodel_name='media.category',
        string="Media Category",
        ondelete='set null',
        tracking=True,
    )
    source_type = fields.Selection(
        [('file', 'File'), ('url', 'Url')],
        string="Source Type", tracking=True,default="file"
    )
    create_uid = fields.Many2one(comodel_name='res.users', string="Uploaded By", readonly=True, tracking=True,default=lambda self: self.env.uid)
    create_date = fields.Datetime(string="Upload Date", readonly=True,default=fields.Date.today)
    favorite=fields.Boolean(string="Favorite", tracking=True,default=False)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed')],default='draft',tracking=True)

    @api.model
    def get_media_type_data(self):
        """Get all records from this model and groups based on media type and return to the orm call"""
        assets = self.search([])
        image = len(assets.filtered(lambda rec: rec.media_type=='image'))
        video = len(assets.filtered(lambda rec: rec.media_type=='video'))
        document = len(assets.filtered(lambda rec: rec.media_type=='document'))
        url = len(assets.filtered(lambda rec: rec.media_type=='url'))
        audio = len(assets.filtered(lambda rec: rec.media_type=='audio'))

        return {
            'count': [image, video, document, url, audio],
            'name':['Image', 'Video', 'Document', 'Url', 'Audio']
        }


    @api.depends('file', 'source_type')
    def _compute_file_size(self):
        """Compute file size in KB from the binary field.
        Applies only when source_type is file/image/document.
        Binary fields are stored as base64 strings; the actual byte size
        is len(base64.b64decode(data)).
        """
        applicable_types = ('file', 'image', 'document')
        for rec in self:
            if rec.file and rec.source_type in applicable_types:
                try:
                    raw_bytes = base64.b64decode(rec.file)
                    rec.file_size = len(raw_bytes) / (1024.0 * 1024.0)
                except Exception:
                    rec.file_size = 0.0
            else:
                rec.file_size = 0.0

    @api.onchange('file')
    def _onchange_file(self):
        """Clear file_name and reset file_size when the binary file is removed.
        When a file IS selected in the browser, Odoo's Binary widget
        automatically writes the original filename into file_name via the
        'filename' attribute declared on the widget in the view.
        """
        if not self.file:
            self.file_name = False
            self.file_size = 0.0

    def confirm(self):
        if self.state == 'draft':
            self.state = 'confirmed'