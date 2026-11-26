## Module <odoo_jira_connector>

#### 25.11.2026
#### Version 19.0.1.0.0
#### ADD
- Initial commit for Odoo Jira Connector
- Webhook secret enforcement and HMAC authentication for incoming webhooks

#### 26.11.2026
#### Version 20.0.1.0.0
#### UPDT
- Migrated to Odoo 20.0.
- Access rights moved to the Odoo 20 ir.access.csv format.
- Updated ir.config_parameter calls to get_str/get_bool/set_bool and
  PG_CONCURRENCY_EXCEPTIONS_TO_RETRY import to odoo.sql_db.
- Converted ir.attachment.raw BinaryValue to bytes when uploading attachments.
- Updated smart button icons to Material Symbols.
