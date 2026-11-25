/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ImportDashBoard extends Component {
    static template = "import_dashboard.ImportDashBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            permissions: {
                bill_of_material: false,
                pos: false,
                import_attendance: false,
                import_payment: false,
                import_task: false,
                import_sale: false,
                import_purchase: false,
                import_product_template: false,
                import_partner: false,
                import_invoice: false,
                import_pricelist: false,
                import_vendor_pricelist: false,
            },
            hasAnyPermission: false,
        });

        onWillStart(async () => {
            // Card visibility is driven by the template (t-if) from this state.
            const result = await this.orm.call("ir.config_parameter", "check_user_group", []);
            Object.assign(this.state.permissions, result);
            this.state.hasAnyPermission = Object.values(result).some(Boolean);
        });
    }

    /**
     * Open an import wizard in a dialog.
     * @param {string} name - Dialog title
     * @param {string} resModel - Wizard model name
     */
    _openWizard(name, resModel) {
        this.action.doAction({
            name,
            type: "ir.actions.act_window",
            res_model: resModel,
            views: [[false, "form"]],
            target: "new",
        });
    }

    import_sale() {
        this._openWizard("Import Sale Order", "import.sale.order");
    }

    import_purchase() {
        this._openWizard("Import Purchase Order", "import.purchase.order");
    }

    import_invoice() {
        this._openWizard("Import Invoice", "import.invoice");
    }

    import_partner() {
        this._openWizard("Import Partner", "import.partner");
    }

    import_product_pricelist() {
        this._openWizard("Import Product Pricelist", "import.product.pricelist");
    }

    import_bill_of_material() {
        this._openWizard("Import Bill of Material", "import.bill.of.material");
    }

    import_product_template() {
        this._openWizard("Import Product", "import.product.template");
    }

    import_vendor_pricelist() {
        this._openWizard("Import Vendor Pricelist", "import.vendor.pricelist");
    }

    import_pos() {
        this._openWizard("Import POS", "import.pos.order");
    }

    import_attendance() {
        this._openWizard("Import Attendance", "import.attendance");
    }

    import_payment() {
        this._openWizard("Import Payment", "import.payment");
    }

    import_task() {
        this._openWizard("Import Task", "import.task");
    }
}

registry.category("actions").add("import_dashboard_tag", ImportDashBoard);
