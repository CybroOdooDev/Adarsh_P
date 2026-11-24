import { registry } from "@web/core/registry";

// Create a route with an area, then download its XLSX report from the wizard.
registry.category("web_tour.tours").add("customer_route_management_tour", {
    steps: () => [
        { content: "New route", trigger: ".o_list_button_add", run: "click" },
        {
            content: "Route name",
            trigger: ".o_field_widget[name='name'] input",
            run: "edit Tour Route",
        },
        {
            content: "Add an area",
            trigger: ".o_field_x2many_list_row_add button",
            run: "click",
        },
        {
            content: "Area name",
            trigger: ".modal .o_field_widget[name='route'] input",
            run: "edit Tour Area",
        },
        { content: "Save the area", trigger: ".modal .o_form_button_save", run: "click" },
        { content: "Area listed", trigger: ".o_data_row:contains(Tour Area)" },
        { content: "Save the route", trigger: ".o_form_button_save", run: "click" },
        { content: "Route saved", trigger: ".o_form_button_save:not(:visible)" },
        { content: "Open the Report menu", trigger: ".o_menu_sections a:contains(Report)", run: "click" },
        {
            content: "Choose the route",
            trigger: ".modal .o_field_widget[name='route_ids'] input",
            run: "edit Tour Route",
        },
        {
            content: "Select it",
            trigger: ".ui-menu-item > a:contains(Tour Route)",
            run: "click",
        },
        {
            content: "Show due amounts",
            trigger: ".modal .o_field_widget[name='payment'] input",
            run: "click",
        },
        {
            content: "Total due only is offered",
            trigger: ".modal .o_field_widget[name='consolidated'] input",
        },
        {
            content: "Print Excel",
            trigger: ".modal button[name='print_xlsx_report_route']",
            run: "click",
        },
        {
            content: "Download done without error",
            trigger: "body:not(:has(.o_error_dialog)):not(:has(.o_blockUI))",
        },
        {
            content: "Close the wizard",
            trigger: ".modal button[special='cancel']",
            run: "click",
        },
        { content: "Wizard closed", trigger: "body:not(:has(.modal))" },
    ],
});
