## Module <customer_route_management>

#### 31.08.2026
#### Version 19.0.1.0.0
##### ADD
- Initial commit for Customer Route Management

#### 26.11.2026
#### Version 20.0.1.0.0
##### UPDT
- Migrated to Odoo 20.0.
- Access rights and multi-company record rules moved to the Odoo 20
  ir.access.csv format.
- Depends on Invoicing (account) only; Sales is no longer required.
- Customer dues are the open items of the receivable account of the customer
  and its contacts (vendor bills are no longer counted), read through the ORM
  instead of an SQL query.
- The delivery order of customers applies within their route area only; the
  default order of all contacts is no longer changed.
- Excel report: columns fit their text and sheet names are valid and unique.
- New banner and icon; README and index page updated for Odoo 20.
- Tests, including a browser tour of the route and Excel report.
