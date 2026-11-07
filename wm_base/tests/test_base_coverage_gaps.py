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
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'wm_base')
class TestBaseCoverageGaps(TransactionCase):
    """wm_base behaviour that runs without the other waste management
    modules: signature request locks and access checks, signer creation
    rules, immutable audit records and audit value formatting."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.role = cls.env['wm.signature.role'].create({'name': 'Gap Signer'})
        cls.template = cls.env['wm.signature.template'].create({
            'name': 'Gap Template',
            'role_ids': [(6, 0, cls.role.ids)],
        })
        cls.other_template = cls.env['wm.signature.template'].create({
            'name': 'Gap Template 2',
            'role_ids': [(6, 0, cls.role.ids)],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Gap Partner', 'email': 'gap@example.com'})
        cls.manager = new_test_user(
            cls.env, login='wm_gap_sig_manager',
            groups='base.group_user,base.group_partner_manager,wm_base.group_signature_manager')
        cls.sig_user = new_test_user(
            cls.env, login='wm_gap_sig_user', groups='base.group_user,wm_base.group_signature_user')

    def _request(self):
        return self.env['wm.signature.request'].create({
            'template_id': self.template.id,
            'signer_ids': [(0, 0, {'partner_id': self.partner.id, 'role_id': self.role.id})],
        })

    # ---- signature request -------------------------------------------------
    def test_cancelled_request_is_locked(self):
        req = self._request()
        req.action_cancel()
        self.assertEqual(req.state, 'cancel')
        with self.assertRaises(UserError):
            req.with_user(self.manager).write({'template_id': self.other_template.id})

    def test_reference_doc_access_check(self):
        Request = self.env['wm.signature.request'].with_user(self.manager)
        # A record the user may modify passes.
        Request._check_reference_doc_access(self.partner)
        with self.assertRaises(UserError):
            Request._check_reference_doc_access('no.such.model,1')
        with self.assertRaises(UserError):
            Request._check_reference_doc_access('res.partner,999999999')

    def test_no_reference_doc(self):
        req = self._request()
        self.assertFalse(req.action_view_reference_doc())
        self.assertFalse(req._render_reference_pdf())

    # ---- signer creation ---------------------------------------------------
    def _signer_vals(self, req, **extra):
        vals = {'request_id': req.id, 'partner_id': self.partner.id, 'role_id': self.role.id}
        vals.update(extra)
        return vals

    def test_signer_cannot_be_added_to_cancelled_request(self):
        req = self._request()
        req.action_cancel()
        with self.assertRaises(UserError):
            self.env['wm.signature.request.signer'].with_user(self.manager).create(self._signer_vals(req))

    def test_signer_cannot_be_created_as_signed(self):
        req = self._request()
        Signer = self.env['wm.signature.request.signer'].with_user(self.manager)
        with self.assertRaises(AccessError):
            Signer.create(self._signer_vals(req, state='signed'))

    def test_signer_only_on_own_request(self):
        req = self._request().with_user(self.manager)
        req.sudo().create_uid = self.manager
        req_other = self._request()
        req_other.sudo().create_uid = self.manager
        signer = self.env['wm.signature.request.signer'].with_user(self.manager).create(self._signer_vals(req))
        self.assertEqual(signer.request_id, req)
        # A plain signature user cannot add signers to someone else's request.
        with self.assertRaises(AccessError):
            self.env['wm.signature.request.signer'].with_user(self.sig_user).create(self._signer_vals(req_other))

    # ---- signature template ------------------------------------------------
    def test_design_template_adds_default_role(self):
        template = self.env['wm.signature.template'].create({
            'name': 'Gap No Role',
            'role_ids': [(6, 0, self.role.ids)],
        })
        template.role_ids = [(5, 0, 0)]
        template.action_design_template()
        self.assertTrue(template.role_ids)

    # ---- waste category ----------------------------------------------------
    def test_duplicate_category_code(self):
        Category = self.env['wm.waste.category']
        Category.create({'name': 'Gap Code A', 'code': 'GAPDUP'})
        with self.assertRaises(ValidationError):
            Category.create({'name': 'Gap Code B', 'code': 'gapdup '})

    # ---- immutable audit records -------------------------------------------
    def test_audit_records_cannot_be_edited(self):
        self.env['ir.config_parameter'].sudo().set_bool('wm_base.group_wm_audit_trail', True)
        category = self.env['wm.waste.category'].create({'name': 'Gap Audit', 'code': 'GAPAUD'})
        category.write({'name': 'Gap Audit Renamed'})
        log = self.env['wm.audit.log'].search(
            [('res_id', '=', category.id), ('model_id.model', '=', 'wm.waste.category')], limit=1)
        self.assertTrue(log)
        with self.assertRaises(UserError):
            log.write({'action': 'create'})

        category.log_status_transition('draft', 'done', reason='Gap test')
        transition = self.env['wm.status.transition.log'].search(
            [('res_id', '=', category.id), ('model_id.model', '=', 'wm.waste.category')], limit=1)
        self.assertTrue(transition)
        with self.assertRaises(UserError):
            transition.write({'new_state': 'draft'})

    # ---- audit value formatting --------------------------------------------
    def test_audit_value_many2one(self):
        category = self.env['wm.waste.category'].create({'name': 'Gap Format', 'code': 'GAPFMT'})
        product = self.env['product.product'].create({'name': 'Gap Service', 'type': 'service'})
        self.assertEqual(category._get_audit_value('service_product_id', product), product.display_name)
        self.assertEqual(category._get_audit_value('service_product_id', product.id), product.display_name)
        self.assertEqual(category._get_audit_value('service_product_id', 999999999), 'Deleted (999999999)')
        self.assertEqual(category._get_audit_value('service_product_id', False), '')
        long_value = 'x' * 300
        self.assertEqual(len(category._get_audit_value('no_such_field', long_value)), 200)
