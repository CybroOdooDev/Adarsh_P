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
import logging
import subprocess
from collections import OrderedDict
from functools import lru_cache

from odoo import models

_logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _detect_unpatched_wkhtmltopdf():
    """Detect whether the host wkhtmltopdf is unpatched QT."""
    try:
        from odoo.addons.base.models.ir_actions_report import _get_wkhtmltopdf_state
        return _get_wkhtmltopdf_state() == 'unpatched'
    except Exception:
        _logger.debug("_get_wkhtmltopdf_state is not available", exc_info=True)
    try:
        from odoo.addons.base.models.ir_actions_report import _wkhtmltopdf_state
        return _wkhtmltopdf_state() == 'unpatched'
    except Exception:
        _logger.debug("_wkhtmltopdf_state is not available", exc_info=True)
    try:
        out = subprocess.check_output(['wkhtmltopdf', '--version'], stderr=subprocess.STDOUT, text=True, timeout=3)
        return 'with patched qt' not in out.lower()
    except Exception:
        _logger.debug("Could not read the wkhtmltopdf version", exc_info=True)
    return True


class IrActionsReport(models.Model):
    """Extend report actions to support multi-document batch PDF rendering with unpatched wkhtmltopdf."""
    _inherit = 'ir.actions.report'

    def _is_unpatched_wkhtmltopdf(self):
        """Safely determine if wkhtmltopdf is using unpatched QT across different Odoo versions."""
        return _detect_unpatched_wkhtmltopdf()

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        """
        When wkhtmltopdf uses unpatched QT, converting multiple HTML documents at once
        raises a UserError. For wm_compliance reports (such as Compliance Manifests and
        Compliance Certificates), render each document stream individually and collect
        them so they can be merged cleanly by Odoo's PDF merger.
        """
        report_sudo = self._get_report(report_ref)
        if (
            res_ids
            and len(res_ids) > 1
            and report_sudo.report_name in (
                'wm_compliance.report_compliance_manifest_template',
                'wm_compliance.report_compliance_certificate_template',
            )
            and self._is_unpatched_wkhtmltopdf()
        ):
            collected_streams = OrderedDict()
            for res_id in res_ids:
                stream_dict = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=[res_id])
                collected_streams.update(stream_dict)
            return collected_streams

        return super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=res_ids)
