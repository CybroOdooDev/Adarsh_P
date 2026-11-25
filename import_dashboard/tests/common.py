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
import base64
import io

from openpyxl import Workbook

from odoo.tests.common import TransactionCase
from odoo.tools import file_open


class TestImportCommon(TransactionCase):
    """Shared records and file helpers for the import wizard tests."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test Partner'})
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'consu',
            'default_code': 'TEST_PROD'
        })
        self.project = self.env['project.project'].create(
            {'name': 'Test Project'})
        self.journal = self.env['account.journal'].search(
            [('type', '=', 'bank')], limit=1)
        if not self.journal:
            self.journal = self.env['account.journal'].create({
                'name': 'Test Bank',
                'type': 'bank',
                'code': 'TBNK'
            })
        self.pos_payment_method = self.env['pos.payment.method'].create({
            'name': 'Cash',
            'journal_id': self.journal.id,
        })
        self.pos_config = self.env['pos.config'].create({
            'name': 'Test POS',
            'payment_method_ids': [(4, self.pos_payment_method.id)],
        })
        self.pos_session = self.env['pos.session'].create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id
        })
        self.pos_session.action_pos_session_open()

    def encode_file(self, content):
        """Return ``content`` as a base64 encoded CSV upload."""
        return base64.b64encode(content.encode('utf-8'))

    def encode_xlsx(self, rows):
        """Return a base64 encoded .xlsx upload whose sheet holds ``rows``."""
        workbook = Workbook()
        sheet = workbook.active
        for row in rows:
            sheet.append(row)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return base64.b64encode(buffer.getvalue())

    def encode_sample(self, file_name):
        """Return a base64 encoded sample template shipped with the module."""
        path = 'import_dashboard/static/sample_templates/%s' % file_name
        with file_open(path, 'rb') as sample:
            return base64.b64encode(sample.read())
