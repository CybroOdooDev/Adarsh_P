# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is under the terms of the Odoo Proprietary License v1.0
#    (OPL-1) It is forbidden to publish, distribute, sublicense, or
#    sell copies of the Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
#    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
#    OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
#    THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#############################################################################
import json
import logging

from werkzeug.exceptions import InternalServerError, NotFound

from odoo.http import Controller, request, route
from odoo.http.dispatcher import serialize_exception
from odoo.http.stream import content_disposition
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class XLSXReportController(Controller):
    """Download of the XLSX route report."""

    @route('/xlsx_report', type='http', auth='user', methods=['POST'])
    def get_report_xlsx(self, model, options, output_format, report_name, **_kwargs):
        """Return the XLSX report built by the route report wizard."""
        if model != 'route.report' or output_format != 'xlsx':
            raise NotFound()
        try:
            response = request.make_response(None, headers=[
                ('Content-Type', XLSX_MIMETYPE),
                ('Content-Disposition', content_disposition(f'{report_name}.xlsx')),
            ])
            request.env[model].get_xlsx_report(json.loads(options), response)
            return response
        except Exception as error:
            _logger.warning("Error while generating report %s", report_name, exc_info=True)
            res = request.make_response(html_escape(json.dumps({
                'code': 0,
                'message': "Odoo Server Error",
                'data': serialize_exception(error),
            })))
            raise InternalServerError(response=res) from error
