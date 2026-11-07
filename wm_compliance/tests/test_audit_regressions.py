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
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'wm_compliance')
class TestAuditComplianceRegressions(TransactionCase):
    """Regression tests for compliance defects confirmed by the 2026-10 ERP audit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.generator = cls.env['res.partner'].create({'name': 'Audit Generator', 'is_generator': True})
        cls.transporter = cls.env['res.partner'].create({'name': 'Audit Transporter', 'is_transporter': True})
        cls.facility = cls.env['wm.disposal.facility'].create({'name': 'Audit Plant', 'facility_type': 'landfill'})
        cls.category = cls.env['wm.waste.category'].create({'name': 'Audit Waste', 'code': 'AUD-CW'})
        cls.officer = new_test_user(cls.env, login='audit_compliance_officer', groups='wm_base.group_wm_compliance_officer')

    def _manifest(self, state='draft'):
        manifest = self.env['wm.compliance.manifest'].create({
            'generator_id': self.generator.id,
            'transporter_id': self.transporter.id,
            'disposal_facility_id': self.facility.id,
            'transport_mode': 'road',
            'line_ids': [(0, 0, {'waste_category_id': self.category.id, 'quantity': 10.0})],
        })
        if state != 'draft':
            manifest.write({'state': state})
        return manifest

    # AUD-040: duplicating a disposed manifest produced an undeletable disposed copy
    def test_duplicated_manifest_starts_in_draft(self):
        copy = self._manifest('disposed').copy()
        self.assertEqual(copy.state, 'draft')
        copy.unlink()

    # AUD-041: a draft manifest could be signed and emailed to stakeholders
    def test_draft_manifest_cannot_be_exported_and_notified(self):
        manifest = self._manifest()
        with self.assertRaises(UserError):
            manifest.action_export_and_notify()
        self.assertFalse(manifest.signature_id)
        self.assertFalse(manifest.notified_at)

    # AUD-042: context key wm_manifest_creating bypassed edit locks on disposed manifests
    def test_manifest_creating_context_flag_does_not_unlock_disposed_manifest(self):
        manifest = self._manifest('disposed')
        with self.assertRaises(UserError):
            self.env['wm.compliance.manifest.line'].with_user(self.officer).with_context(
                wm_manifest_creating=True).create({
                    'manifest_id': manifest.id,
                    'waste_category_id': self.category.id,
                    'quantity': 900.0,
                })

    # AUD-043: total_quantity was writable after submission via RPC
    def test_total_quantity_cannot_be_written_on_submitted_manifest(self):
        manifest = self._manifest()
        manifest.action_submit()
        self.assertEqual(manifest.state, 'submitted')
        with self.assertRaises(UserError):
            manifest.with_user(self.officer).write({'total_quantity': 5000.0})

    # AUD-045: negative manifest line quantities allowed
    def test_negative_manifest_line_quantity_is_rejected(self):
        manifest = self._manifest()
        with self.assertRaises(ValidationError):
            self.env['wm.compliance.manifest.line'].create({
                'manifest_id': manifest.id,
                'waste_category_id': self.category.id,
                'quantity': -400.0,
            })
