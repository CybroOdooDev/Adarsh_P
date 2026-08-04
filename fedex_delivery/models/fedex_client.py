import json
import logging
import requests

_logger = logging.getLogger(__name__)


class FedExClient:
    """
    Plain client class handling direct communication with the FedEx REST API.
    Does not depend on Odoo models.
    """

    SANDBOX_URL = "https://apis-sandbox.fedex.com"
    PRODUCTION_URL = "https://apis.fedex.com"

    def __init__(self, client_id, client_secret, account_number, environment='sandbox'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_number = account_number
        self.environment = environment
        self.base_url = self.PRODUCTION_URL if environment == 'production' else self.SANDBOX_URL

    def get_access_token(self):
        """
        Request OAuth 2.0 access token from FedEx.
        Returns tuple: (access_token, expires_in_seconds)
        """
        endpoint = f"{self.base_url}/oauth/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }

        try:
            response = requests.post(endpoint, headers=headers, data=data, timeout=30)
            response.raise_for_status()
            res_data = response.json()
            access_token = res_data.get('access_token')
            expires_in = res_data.get('expires_in', 3600)
            return access_token, expires_in
        except requests.exceptions.RequestException as e:
            error_detail = ""
            if getattr(e, 'response', None) is not None and e.response is not None:
                try:
                    error_detail = e.response.text
                except Exception:
                    error_detail = str(e)
            else:
                error_detail = str(e)
            _logger.error("FedEx Authentication Error: %s", error_detail)
            raise RuntimeError(f"FedEx Authentication Failed: {error_detail}") from e

    def create_shipment(self, token, payload):
        """
        Call FedEx Ship API to create a shipment.
        Returns the parsed JSON response.
        """
        endpoint = f"{self.base_url}/ship/v1/shipments"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }

        try:
            response = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=60)
            if not response.ok:
                _logger.error("FedEx Ship API Error HTTP %s: %s", response.status_code, response.text)
                raise RuntimeError(f"FedEx API Error ({response.status_code}): {response.text}")
            return response.json()
        except requests.exceptions.RequestException as e:
            error_detail = ""
            if getattr(e, 'response', None) is not None and e.response is not None:
                try:
                    error_detail = e.response.text
                except Exception:
                    error_detail = str(e)
            else:
                error_detail = str(e)
            _logger.error("FedEx Request Error: %s", error_detail)
            raise RuntimeError(f"FedEx Communication Failed: {error_detail}") from e
