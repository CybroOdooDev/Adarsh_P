/** @odoo-module */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useChart } from "@web/core/utils/chart_hook";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class FleetDashboard extends Component {
    static template = "FleetDashboard";
    props = useProps(standardActionServiceProps);

    invoiceChart = useChart(() => this.getInvoiceChartConfig());
    durationChart = useChart(() => this.getDurationChartConfig());

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            data: {},
            monthlyInvoices: {},
        });

        onWillStart(async () => {
            await this.fetchData();
        });
    }

    async fetchData() {
        try {
            this.state.data = await this.orm.call("fleet.dashboard", "get_datas");
            this.state.monthlyInvoices = await this.orm.call("fleet.dashboard", "get_monthly_contract_invoices");
        } catch (error) {
            console.error("Failed to fetch dashboard data:", error);
        }
    }

    getInvoiceChartConfig() {
        const labels = this.state.monthlyInvoices?.labels || [];
        const data = this.state.monthlyInvoices?.data || [];
        const colors = [
            'rgba(75, 192, 192, 0.8)',
            'rgba(54, 162, 235, 0.8)',
            'rgba(255, 206, 86, 0.8)'
        ];
        const borders = [
            'rgba(75, 192, 192, 1)',
            'rgba(54, 162, 235, 1)',
            'rgba(255, 206, 86, 1)'
        ];
        const backgroundColors = data.map((_, index) => colors[index % colors.length]);
        const borderColors = data.map((_, index) => borders[index % borders.length]);

        return {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Monthly Contract Invoices',
                        data: data,
                        backgroundColor: backgroundColors,
                        borderColor: borderColors,
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    title: {
                        display: true,
                        text: 'Monthly Contract Invoices'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        };
    }

    getDurationChartConfig() {
        const labels = ['Operational', 'Under Maintenance'];
        const data = [this.state.data?.operational || 0, this.state.data?.under_maintenance || 0];
        const backgroundColors = ['rgba(46, 204, 113, 0.8)', 'rgba(231, 76, 60, 0.8)'];
        const borderColors = ['rgba(39, 174, 96, 1)', 'rgba(192, 57, 43, 1)'];

        return {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Travel',
                        data: data,
                        backgroundColor: backgroundColors,
                        borderColor: borderColors,
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    title: {
                        display: true,
                        text: 'Travel'
                    }
                }
            }
        };
    }

    onClickVehicles() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Operational Vehicles',
            res_model: 'fleet.vehicle',
            view_mode: 'list,form',
            context: {
                'tree_view_ref': 'advanced_fleet_rental.fleet_vehicle_view_tree',
                'form_view_ref': 'advanced_fleet_rental.fleet_vehicle_view_form',
                'create': false
            },
            views: [[false, 'list'], [false, 'form']],
        });
    }

    onClickAvailableVehicles() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Total Vehicles',
            res_model: 'fleet.vehicle',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            context: {
                'tree_view_ref': 'advanced_fleet_rental.fleet_vehicle_view_tree',
                'form_view_ref': 'advanced_fleet_rental.fleet_vehicle_view_form',
                'create': false
            },
            target: 'current',
            domain: [['status', '=', 'operational']],
        });
    }

    onClickUnderMaintenanceVehicles() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Under Maintenance Vehicles',
            res_model: 'fleet.vehicle',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            context: {
                'tree_view_ref': 'advanced_fleet_rental.fleet_vehicle_view_tree',
                'form_view_ref': 'advanced_fleet_rental.fleet_vehicle_view_form',
                'create': false
            },
            target: 'current',
            domain: [['status', '=', 'undermaintenance']],
        });
    }

    onClickAllCustomers() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Customers',
            res_model: 'res.partner',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            context: { create: false },
        });
    }

    onClickInvoices() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Invoices',
            res_model: 'account.move',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            context: { create: false },
            domain: [["vehicle_rental_id", "!=", false]],
        });
    }

    onPendingInvoices() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Pending Invoices',
            res_model: 'account.move',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            context: { create: false },
            domain: [
                ['vehicle_rental_id', '!=', false],
                ['state', '=', 'posted'],
                ['payment_state', '!=', 'paid']
            ],
        });
    }

    onAllContract() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'All Contracts',
            res_model: 'fleet.rental.contract',
            view_mode: 'list,form',
            context: { create: false },
            views: [[false, 'kanban'], [false, 'list'], [false, 'form']],
        });
    }

    onInProgressContract() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'In Progress Contracts',
            res_model: 'fleet.rental.contract',
            view_mode: 'list,form',
            context: { create: false },
            views: [[false, 'kanban'], [false, 'list'], [false, 'form']],
            domain: [['state', '=', 'in_progress']],
        });
    }

    onReturnContract() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Return Contracts',
            res_model: 'fleet.rental.contract',
            view_mode: 'list,form',
            context: { create: false },
            views: [[false, 'kanban'], [false, 'list'], [false, 'form']],
            domain: [['state', '=', 'return']],
        });
    }

    onCancelContract() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Cancelled Contracts',
            res_model: 'fleet.rental.contract',
            view_mode: 'list,form',
            context: { create: false },
            views: [[false, 'kanban'], [false, 'list'], [false, 'form']],
            domain: [['state', '=', 'cancel']],
        });
    }
}

registry.category("actions").add('fleet_dashboard_tag', FleetDashboard);