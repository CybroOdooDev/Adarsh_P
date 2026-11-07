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
import base64
import re
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.misc import file_open

from ..controllers import portal
from ..controllers.portal import WmSignaturePortal


@tagged('post_install', '-at_install', 'wm_base')
class TestAuditBaseRegressions(TransactionCase):
    """Regression tests for wm_base defects confirmed by the 2026-10 ERP audit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.role = cls.env['wm.signature.role'].create({'name': 'Audit Signer'})
        cls.template = cls.env['wm.signature.template'].create({
            'name': 'Audit Template',
            'document': base64.b64encode(b'%PDF-1.4 audit').decode(),
            'document_filename': 'audit.pdf',
            'role_ids': [(6, 0, cls.role.ids)],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Audit Signer Partner', 'email': 'audit@example.com'})
        cls.sig_user = new_test_user(cls.env, login='audit_sig_user', groups='wm_base.group_signature_user')
        cls.other_user = new_test_user(cls.env, login='audit_other_user', groups='wm_base.group_signature_user')

    # AUD-020: escapeHtml left < and > unescaped (stored XSS on the signing page)
    def test_signing_page_escapes_angle_brackets(self):
        with file_open('wm_base/static/src/js/signature_portal_sign.js') as js:
            source = js.read()
        mapping = re.search(r"function escapeHtml\(value\) \{(.*?)\n\s*\}", source, re.S).group(1)
        self.assertIn("'<': '&lt;'", mapping)
        self.assertIn("'>': '&gt;'", mapping)
        self.assertIn("'&': '&amp;'", mapping)

    # AUD-021: the public PDF link kept serving cancelled requests
    def _pdf_response_for(self, state):
        request = self.env['wm.signature.request'].create({
            'template_id': self.template.id,
            'signer_ids': [(0, 0, {'partner_id': self.partner.id, 'role_id': self.role.id,
                                   'email': 'audit@example.com'})],
        })
        request.sudo().write({'state': state})
        mock_req = MagicMock()
        mock_req.env = self.env
        with patch.object(portal, 'request', mock_req):
            # Call the undecorated endpoint: the route wrapper rejects mock responses.
            WmSignaturePortal.get_request_pdf.original_endpoint(
                WmSignaturePortal(), request.signer_ids.access_token)
        return mock_req

    def test_cancelled_request_pdf_is_not_served(self):
        for state in ('cancel', 'draft'):
            mock_req = self._pdf_response_for(state)
            self.assertTrue(mock_req.not_found.called, state)
            self.assertFalse(mock_req.make_response.called, state)

    def test_open_request_pdf_is_served(self):
        mock_req = self._pdf_response_for('sent')
        self.assertTrue(mock_req.make_response.called)

    # AUD-022: signature request state forgery via write()
    def test_signature_request_state_cannot_be_forged(self):
        req = self.env['wm.signature.request'].with_user(self.sig_user).create({
            'template_id': self.template.id,
            'signer_ids': [(0, 0, {'partner_id': self.partner.id, 'role_id': self.role.id,
                                   'email': 'audit@example.com'})],
        })
        with self.assertRaises(AccessError):
            req.with_user(self.sig_user).write({'state': 'signed'})
        with self.assertRaises(AccessError):
            req.with_user(self.sig_user).write({'signed_document': base64.b64encode(b'forged').decode()})
        with self.assertRaises(AccessError):
            req.with_user(self.sig_user).write({'signed_document_hash': 'deadbeef'})
        with self.assertRaises(AccessError):
            req.with_user(self.sig_user).write({'date_signed': fields.Datetime.now()})

    # AUD-023: signature user adding themselves as signer to another user's request
    def test_signer_cannot_be_added_to_other_users_request(self):
        req_a = self.env['wm.signature.request'].with_user(self.sig_user).create({
            'template_id': self.template.id,
            'signer_ids': [(0, 0, {'partner_id': self.partner.id, 'role_id': self.role.id,
                                   'email': 'audit@example.com'})],
        })
        with self.assertRaises(AccessError):
            self.env['wm.signature.request.signer'].with_user(self.other_user).create({
                'request_id': req_a.id,
                'partner_id': self.other_user.partner_id.id,
                'role_id': self.role.id,
                'email': 'other@example.com',
            })

    # AUD-022 (create path): a request cannot be created already signed
    def test_signature_request_cannot_be_created_signed(self):
        Request = self.env['wm.signature.request'].with_user(self.sig_user)
        for vals in ({'state': 'signed'}, {'state': 'sent'},
                     {'signed_document': base64.b64encode(b'%PDF-1.4 forged').decode()},
                     {'signed_document_hash': 'deadbeef'}):
            with self.subTest(vals=list(vals)), self.assertRaises(AccessError):
                Request.create(dict({'template_id': self.template.id}, **vals))
        draft = Request.create({'template_id': self.template.id})
        self.assertEqual(draft.state, 'draft')

    # Send / Cancel write the status as superuser: they still require write access
    def test_send_and_cancel_require_write_access(self):
        req = self.env['wm.signature.request'].with_user(self.sig_user).create({
            'template_id': self.template.id,
            'signer_ids': [(0, 0, {'partner_id': self.partner.id, 'role_id': self.role.id,
                                   'email': 'audit@example.com'})],
        })
        with self.assertRaises(AccessError):
            req.with_user(self.other_user).action_cancel()
        self.assertEqual(req.state, 'draft')
        req.with_user(self.sig_user).action_cancel()
        self.assertEqual(req.state, 'cancel')
