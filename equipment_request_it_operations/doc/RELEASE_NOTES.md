## Module <equipment_request_it_operations>

#### 25.11.2026
#### Version 19.0.1.0.0
##### ADD
- Initial commit for Equipment Request & IT Operation

#### 26.11.2026
#### Version 20.0.1.0.0
##### UPDT
- Migrated to Odoo 20.0.
- Access rights moved from ir.model.access.csv to the Odoo 20 ir.access.csv format.
- Internal transfer moves use the Odoo 20 stock move unit field (uom_id).
- Removed the report_file field from the report action (dropped in Odoo 20).
- Fixed: Create Internal Transfer used the first operation type with the
  'internal' code (e.g. Quality Control); it now uses the Internal Transfers
  type of the source location's warehouse (or of the company's warehouse).
- Fixed: the Expense smart button now lists the expenses linked to the request
  even after the employee or the request type is changed.
- Expense smart button icon updated to the Odoo 20 icon set.
- Request name uses the request type label (e.g. "Hardware").
- Readable model descriptions (shown in the chatter, e.g. "Equipment Request created").
- Equipment Report: quantities, amounts and dates are formatted.
- Manifest cleaned up; README, index page and screenshots updated for Odoo 20.
