from datetime import timedelta
from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

from .fedex_client import FedExClient


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('fedex_custom', 'FedEx (Custom)')],
        ondelete={'fedex_custom': 'set default'}
    )

    fedex_client_id = fields.Char(string='FedEx Client ID')
    fedex_client_secret = fields.Char(string='FedEx Client Secret', groups='base.group_system')
    fedex_account_number = fields.Char(string='FedEx Account Number')
    fedex_environment = fields.Selection(
        [('sandbox', 'Sandbox'), ('production', 'Production')],
        string='Environment',
        default='sandbox'
    )

    fedex_access_token = fields.Char(string='FedEx Access Token', copy=False)
    fedex_token_expiry = fields.Datetime(string='FedEx Token Expiry', copy=False)

    def _fedex_get_packages(self, picking):
        self.ensure_one()
        count = max(1, picking.number_of_packages or 1)
        total_weight = picking.weight or 1.0
        weight_per_pkg = max(0.1, round(total_weight / count, 2))

        packages = []
        for i in range(count):
            packages.append({
                'weight': weight_per_pkg,
                'name': f"Package_{i + 1}",
            })

        return packages

    def _fedex_build_address(self, partner):
        return {
            "contact": {
                "personName": partner.name or '',
                "phoneNumber": partner.phone or partner.mobile or '',
                "companyName": partner.commercial_company_name or partner.parent_id.name or '',
            },
            "address": {
                "streetLines": [partner.street or ''] + ([partner.street2] if partner.street2 else []),
                "city": partner.city or '',
                "stateOrProvinceCode": partner.state_id.code or '',
                "postalCode": partner.zip or '',
                "countryCode": partner.country_id.code or '',
            }
        }

    def _fedex_get_token(self):
        self.ensure_one()
        now = fields.Datetime.now()
        if self.fedex_access_token and self.fedex_token_expiry and self.fedex_token_expiry > now:
            return self.fedex_access_token

        if not self.fedex_client_id or not self.fedex_client_secret:
            raise UserError(_("FedEx Client ID and Client Secret must be configured on delivery carrier '%s'.") % self.name)

        client = FedExClient(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            account_number=self.fedex_account_number,
            environment=self.fedex_environment or 'sandbox'
        )

        try:
            token, expires_in = client.get_access_token()
        except Exception as e:
            raise UserError(_("FedEx Authentication Error: %s") % str(e)) from e

        expiry_time = now + timedelta(seconds=max(0, expires_in - 60))
        self.sudo().write({
            'fedex_access_token': token,
            'fedex_token_expiry': expiry_time,
        })
        return token

    def _fedex_build_payload(self, shipper, recipient, packages):
        self.ensure_one()
        requested_packages = []
        for idx, pkg in enumerate(packages, start=1):
            requested_packages.append({
                "sequenceNumber": idx,
                "weight": {
                    "units": "LB",
                    "value": float(pkg.get('weight', 1.0))
                }
            })

        payload = {
            "labelResponseOptions": "LABEL",
            "requestedShipment": {
                "totalPackageCount": len(packages),
                "shipper": shipper,
                "recipients": [recipient],
                "shipDatestamp": fields.Date.today().strftime('%Y-%m-%d'),
                "serviceType": "FEDEX_GROUND",
                "packagingType": "YOUR_PACKAGING",
                "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
                "shippingChargesPayment": {
                    "paymentType": "SENDER",
                    "payor": {
                        "responsibleParty": {
                            "accountNumber": {
                                "value": self.fedex_account_number or ''
                            }
                        }
                    }
                },
                "labelSpecification": {
                    "imageType": "PDF",
                    "labelStockType": "PAPER_85X11_TOP_HALF_LABEL"
                },
                "requestedPackageLineItems": requested_packages
            },
            "accountNumber": {
                "value": self.fedex_account_number or ''
            }
        }
        return payload

    def _fedex_call_api(self, token, payload):
        self.ensure_one()
        client = FedExClient(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            account_number=self.fedex_account_number,
            environment=self.fedex_environment or 'sandbox'
        )
        try:
            return client.create_shipment(token, payload)
        except Exception as e:
            raise UserError(_("FedEx Shipment Creation Failed: %s") % str(e)) from e

    def fedex_send_shipping(self, pickings):
        results = []
        for picking in pickings:
            token = self._fedex_get_token()
            packages = self._fedex_get_packages(picking)

            payload = self._fedex_build_payload(
                shipper=self._fedex_build_address(self.env.company.partner_id),
                recipient=self._fedex_build_address(picking.partner_id),
                packages=packages,
            )

            response = self._fedex_call_api(token, payload)

            try:
                shipment = response["output"]["transactionShipments"][0]
                master_tracking = shipment["masterTrackingNumber"]
            except (KeyError, IndexError, TypeError) as e:
                raise UserError(_("Unexpected response structure from FedEx: %s") % str(response)) from e

            attachments = []
            chatter_lines = []

            piece_responses = shipment.get("pieceResponses", [])
            for idx, piece in enumerate(piece_responses):
                package_info = packages[idx] if idx < len(packages) else {}
                package_name = package_info.get('name', f"Package_{idx + 1}")

                package_docs = piece.get("packageDocuments", [])
                encoded_label = package_docs[0]["encodedLabel"] if package_docs else False
                tracking_num = piece.get('trackingNumber', master_tracking)

                label_filename = f"FedEx_Label_{package_name}_{tracking_num}.pdf"

                if encoded_label:
                    att = self.env['ir.attachment'].create({
                        'name': label_filename,
                        'type': 'binary',
                        'datas': encoded_label,          # base64 string
                        'res_model': 'stock.picking',
                        'res_id': picking.id,
                        'mimetype': 'application/pdf',
                    })
                    attachments.append(att.id)

                chatter_lines.append(Markup("<li><b>%s</b>: Tracking # <code>%s</code></li>") % (package_name, tracking_num))

            if attachments:
                chatter_body = Markup(
                    "<b>FedEx Shipping Labels Generated</b> (Master Tracking #: <code>%s</code>):<br/><ul>%s</ul>"
                ) % (master_tracking, Markup("").join(chatter_lines))
                picking.message_post(
                    body=chatter_body,
                    attachment_ids=attachments,
                )

            results.append({
                'exact_price': 0.0,   # wire up Rate API later if real cost is needed
                'tracking_number': master_tracking,
            })
        return results

    def fedex_custom_send_shipping(self, pickings):
        return self.fedex_send_shipping(pickings)

    def fedex_custom_get_tracking_link(self, picking):
        return f"https://www.fedex.com/fedextrack/?trknbr={picking.carrier_tracking_ref}"

    def fedex_custom_cancel_shipment(self, pickings):
        for picking in pickings:
            picking.message_post(body=_("Shipment canceled in Odoo for FedEx tracking: %s") % picking.carrier_tracking_ref)
        return True

    def fedex_custom_rate_shipment(self, order):
        return {
            'success': True,
            'price': 0.0,
            'error_message': False,
            'warning_message': False,
        }
