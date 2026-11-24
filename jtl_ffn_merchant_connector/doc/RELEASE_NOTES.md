## Module <jtl_ffn_merchant_connector>

#### 08.07.2026
#### Version 19.0.1.0.0
#### ADD
- Initial commit for jtl ffn connector

#### 05.11.2026
#### Version 19.0.1.0.0
#### FIX
- Added JTL FFN User / Manager security groups.
- Credentials (client secret, refresh token, access token) are readable only by Managers.
- Connection profiles and warehouse mappings are Manager-only for editing; Users get read access and can work sync records.
- Kept OCA in manifest author (required by pylint-odoo).
- Upgrade note: existing non-admin users must be added to a JTL FFN group to keep access.

#### 09.11.2026
#### Version 19.0.1.0.0
#### ADD
- One-click **Connect to JTL** button with an authenticated OAuth callback; the state is bound to the user's session.
- Editable **Redirect URI** on the connection profile (default: `<base URL>/jtl_ffn/oauth_callback`).
- Refreshed tokens (including a rotated refresh token) are saved in a separate transaction so they survive a rollback.
- Upgrade note: register the Redirect URI shown on each profile in the JTL Developer Portal, or edit the field to the URI you registered earlier.

#### 10.11.2026
#### Version 19.0.1.0.0
#### CHANGE
- Connection profile and configuration aligned with the Odoo 18 version: the profile is switched on or off with the **Active** checkbox (`is_active`), the Redirect URI defaults to the base URL, and the OAuth callback exchanges the code with the profile in the `state` parameter.
- The form view, the token refresh scheduled action (`cron_refresh_expiring_tokens`) and the OAuth tests follow the Odoo 18 module.


#### 24.11.2026
#### Version 20.0.1.0.0
#### UPDT
- Migrated to Odoo 20.
- Access rights moved to `security/ir.access.csv` (`ir.model.access` no longer exists in Odoo 20).
- System parameters are read with `get_str` (`get_param` was removed).
- Order push: the phone no longer falls back to the removed `mobile` field, and the company name comes from the customer's company (`company_name` was removed). Orders could not be pushed without these fixes.
- Return pickings use the Odoo 20 return API (the `stock.return.picking` wizard was removed), with the returned quantity of each product, at most the delivered quantity.
- Depends on `stock_delivery`, which provides the carrier and tracking number of deliveries.
- OAuth redirects use the Odoo 20 `/odoo` URLs.
- Shipment tracking: the ISO 8601 ship date sent by JTL FFN is now parsed; before, every shipment with a ship date failed to import.
- Shipment tracking validates the delivery without the SMS warning wizard, and a shipment is marked Applied to Delivery only once its delivery is done.
- Exchange Code Manually sends the profile's Redirect URI, the one the authorization code was issued for.
- Connection profile fields keep their labels (Client ID, Redirect URI, Active) under the Odoo 20 label rules.
- New description page, Odoo 20 screenshots and README.
