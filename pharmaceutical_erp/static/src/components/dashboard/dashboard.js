/** @odoo-module **/

import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class PharmaDashboard extends Component {
    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.chartRef = useRef("chartCanvas");

        const today = luxon.DateTime.local();
        this.state = useState({
            startDate: today.startOf("month").toFormat("yyyy-MM-dd"),
            endDate: today.endOf("month").toFormat("yyyy-MM-dd"),

            totalBatches: 0,
            openQcTests: 0,
            openDeviations: 0,
            openCapas: 0,
            openOos: 0,

            releasedBatches: 0,
            quarantineBatches: 0,
            rejectedBatches: 0,
            pendingReleaseBatches: 0,

            expiringToday: 0,
            expiring30: 0,
            expiring60: 0,
            expiring90: 0,

            chartLabels: ["Dec", "Jan", "Feb", "Mar", "Apr", "May"],
            chartData: [82, 96, 108, 95, 125, 148],

            trendBatches: { value: 0, up: true },
            trendQc: { value: 0, up: true },
            trendDev: { value: 0, up: true },
            trendCapa: { value: 0, up: true },
            trendOos: { value: 0, up: true },

            chartFilter: "daily",
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.fetchData();
        });

        useEffect(() => {
            this.renderChart();
        }, () => [this.state.chartData]);
    }

    async fetchData() {
        const startStr = this.state.startDate + " 00:00:00";
        const endStr = this.state.endDate + " 23:59:59";

        let groupBy = "date_finished:month";
        if (this.state.chartFilter === "yearly") groupBy = "date_finished:year";
        else if (this.state.chartFilter === "weekly") groupBy = "date_finished:week";
        else if (this.state.chartFilter === "daily") groupBy = "date_finished:day";

        const startDT = luxon.DateTime.fromISO(this.state.startDate);
        const endDT = luxon.DateTime.fromISO(this.state.endDate);
        const diffDays = endDT.diff(startDT, 'days').days;

        const prevStartStr = startDT.minus({ days: diffDays + 1 }).toFormat("yyyy-MM-dd") + " 00:00:00";
        const prevEndStr = startDT.minus({ days: 1 }).toFormat("yyyy-MM-dd") + " 23:59:59";

        const today = luxon.DateTime.local();
        const todayStr = today.toFormat("yyyy-MM-dd HH:mm:ss");
        const todayEndStr = today.endOf("day").toFormat("yyyy-MM-dd HH:mm:ss");
        const todayStartStr = today.startOf("day").toFormat("yyyy-MM-dd HH:mm:ss");
        const in30 = today.plus({ days: 30 }).toFormat("yyyy-MM-dd HH:mm:ss");
        const in60 = today.plus({ days: 60 }).toFormat("yyyy-MM-dd HH:mm:ss");
        const in90 = today.plus({ days: 90 }).toFormat("yyyy-MM-dd HH:mm:ss");

        const dateDomain = [["create_date", ">=", startStr], ["create_date", "<=", endStr]];
        const prevDateDomain = [["create_date", ">=", prevStartStr], ["create_date", "<=", prevEndStr]];

        const [
            totalBatches, openQcTests, openDeviations, openCapas, openOos,
            releasedBatches, quarantineBatches, rejectedBatches, pendingReleaseBatches,
            expiringToday, expiring30, expiring60, expiring90,
            productionData,

            tmBatches, tmQc, tmDev, tmCapa, tmOos,
            lmBatches, lmQc, lmDev, lmCapa, lmOos
        ] = await Promise.all([
            // Current Period
            this.orm.searchCount("stock.lot", dateDomain),
            this.orm.searchCount("pharma.qc.test.order", [["status", "in", ["draft", "in_progress",
             "under_investigation"]], ...dateDomain]),
            this.orm.searchCount("pharma.deviation", [["status", "in", ["open", "under_investigation"]], ...dateDomain]),
            this.orm.searchCount("pharma.capa", [["status", "in", ["open", "under_investigation"]], ...dateDomain]),
            this.orm.searchCount("pharma.oos.investigation", [["closed_on", "=", false], ...dateDomain]),

            // Statuses
            this.orm.searchCount("stock.lot", [["lot_status", "=", "released"], ...dateDomain]),
            this.orm.searchCount("stock.lot", [["lot_status", "=", "quarantine"], ...dateDomain]),
            this.orm.searchCount("stock.lot", [["lot_status", "=", "rejected"], ...dateDomain]),
            this.orm.searchCount("stock.lot", [["lot_status", "=", "approved"], ...dateDomain]),

            // Expiring
            this.orm.searchCount("stock.lot", [["expiration_date", "<=", todayEndStr], ["expiration_date", ">=", todayStartStr]]),
            this.orm.searchCount("stock.lot", [["expiration_date", "<=", in30], ["expiration_date", ">=", todayStr]]),
            this.orm.searchCount("stock.lot", [["expiration_date", "<=", in60], ["expiration_date", ">=", todayStr]]),
            this.orm.searchCount("stock.lot", [["expiration_date", "<=", in90], ["expiration_date", ">=", todayStr]]),

            // Chart
            this.orm.call("mrp.production", "read_group", [[["state", "=", "done"], ["date_finished", ">=",
            startStr], ["date_finished", "<=", endStr]], ["id"], [groupBy]]),

            // This period creations for trend
            this.orm.searchCount("stock.lot", dateDomain),
            this.orm.searchCount("pharma.qc.test.order", dateDomain),
            this.orm.searchCount("pharma.deviation", dateDomain),
            this.orm.searchCount("pharma.capa", dateDomain),
            this.orm.searchCount("pharma.oos.investigation", dateDomain),

            // Previous period creations for trend
            this.orm.searchCount("stock.lot", prevDateDomain),
            this.orm.searchCount("pharma.qc.test.order", prevDateDomain),
            this.orm.searchCount("pharma.deviation", prevDateDomain),
            this.orm.searchCount("pharma.capa", prevDateDomain),
            this.orm.searchCount("pharma.oos.investigation", prevDateDomain),
        ]);

        const calcTrend = (tm, lm) => {
            if (lm === 0) return tm > 0 ? { value: 100, up: true } : { value: 0, up: true };
            const diff = ((tm - lm) / lm) * 100;
            return { value: Math.abs(Math.round(diff)), up: diff >= 0 };
        };

        this.state.trendBatches = calcTrend(tmBatches, lmBatches);
        this.state.trendQc = calcTrend(tmQc, lmQc);
        this.state.trendDev = calcTrend(tmDev, lmDev);
        this.state.trendCapa = calcTrend(tmCapa, lmCapa);
        this.state.trendOos = calcTrend(tmOos, lmOos);

        this.state.totalBatches = totalBatches;
        this.state.openQcTests = openQcTests;
        this.state.openDeviations = openDeviations;
        this.state.openCapas = openCapas;
        this.state.openOos = openOos;

        this.state.releasedBatches = releasedBatches;
        this.state.quarantineBatches = quarantineBatches;
        this.state.rejectedBatches = rejectedBatches;
        this.state.pendingReleaseBatches = pendingReleaseBatches;

        this.state.expiringToday = expiringToday;
        this.state.expiring30 = expiring30;
        this.state.expiring60 = expiring60;
        this.state.expiring90 = expiring90;

        if (productionData && productionData.length > 0) {
            const labels = [];
            const data = [];
            for (const item of productionData) {
                const labelStr = item[groupBy] || item.date_finished;
                if (labelStr) {
                    labels.push(labelStr.split(" ")[0]);
                    data.push(item.date_finished_count);
                }
            }
            if (labels.length > 0) {
                // Show up to 30 data points
                this.state.chartLabels = labels.slice(-30);
                this.state.chartData = data.slice(-30);
            }
        } else {
            this.state.chartLabels = ["No Data"];
            this.state.chartData = [0];
        }
    }

    renderChart() {
        if (!this.chartRef.el) return;
        const ctx = this.chartRef.el.getContext("2d");

        if (this.chartInstance) {
            this.chartInstance.destroy();
        }

        this.chartInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: this.state.chartLabels,
                datasets: [{
                    label: "Batches",
                    data: this.state.chartData,
                    borderColor: "#006D6F",
                    backgroundColor: "rgba(0, 160, 157, 0.1)",
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: "#006D6F",
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 40 }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // --- Action Handlers for Clicks ---

    openLots() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Batches",
            res_model: "stock.lot",
            views: [[false, "list"], [false, "form"]],
        });
    }

    openQcTests() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Open QC Tests",
            res_model: "pharma.qc.test.order",
            domain: [["status", "in", ["draft", "in_progress", "under_investigation"]]],
            views: [[false, "list"], [false, "form"]],
        });
    }

    openDeviations() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Open Deviations",
            res_model: "pharma.deviation",
            domain: [["status", "in", ["open", "under_investigation"]]],
            views: [[false, "list"], [false, "form"]],
        });
    }

    openCapas() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Open CAPAs",
            res_model: "pharma.capa",
            domain: [["status", "in", ["open", "under_investigation"]]],
            views: [[false, "list"], [false, "form"]],
        });
    }

    openOos() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Open OOS",
            res_model: "pharma.oos.investigation",
            domain: [["closed_on", "=", false]],
            views: [[false, "list"], [false, "form"]],
        });
    }

    openLotsByStatus(status) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: `Batches - ${status}`,
            res_model: "stock.lot",
            domain: [["lot_status", "=", status]],
            views: [[false, "list"], [false, "form"]],
        });
    }

    openExpiringLots(days) {
        const today = luxon.DateTime.local();
        const todayStr = today.toFormat("yyyy-MM-dd HH:mm:ss");
        let start, end;
        if (days === 0) {
            end = today.endOf("day").toFormat("yyyy-MM-dd HH:mm:ss");
            start = today.startOf("day").toFormat("yyyy-MM-dd HH:mm:ss");
        } else if (days === 30) {
            end = today.plus({ days: 30 }).toFormat("yyyy-MM-dd HH:mm:ss");
            start = todayStr;
        } else if (days === 60) {
            end = today.plus({ days: 60 }).toFormat("yyyy-MM-dd HH:mm:ss");
            start = todayStr;
        } else if (days === 90) {
            end = today.plus({ days: 90 }).toFormat("yyyy-MM-dd HH:mm:ss");
            start = todayStr;
        }

        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: `Expiring within ${days} days`,
            res_model: "stock.lot",
            domain: [["expiration_date", "<=", end], ["expiration_date", ">", start]],
            views: [[false, "list"], [false, "form"]],
        });
    }
}

PharmaDashboard.template = "pharmaceutical_erp.PharmaDashboard";

registry.category("actions").add("pharma_dashboard_action", PharmaDashboard);
