import { patch } from "@web/core/utils/patch";
import { GraphRenderer } from "@web/views/graph/graph_renderer";

patch(GraphRenderer.prototype, {
    getScaleOptions() {
        const options = super.getScaleOptions(...arguments);
        const darkTextColor = "#1F2937"; // Dark slate for maximum legibility on light graph canvas
        if (options.x && options.x.ticks) {
            options.x.ticks.color = darkTextColor;
            options.x.ticks.font = { weight: "600", size: 12 };
        }
        if (options.y && options.y.ticks) {
            options.y.ticks.color = darkTextColor;
            options.y.ticks.font = { weight: "600", size: 12 };
        }
        return options;
    },
    getLegendOptions() {
        const options = super.getLegendOptions(...arguments);
        const darkTextColor = "#1F2937";
        if (options) {
            // Only the pie mode defines legend labels in core, so create them
            // for the other modes and fall back to Chart.js' own generator.
            options.labels = options.labels || {};
            options.labels.color = darkTextColor;
            options.labels.font = { weight: "600", size: 12 };
            const originalGenerateLabels = options.labels.generateLabels
                || ((chart) => window.Chart.defaults.plugins.legend.labels.generateLabels(chart));
            options.labels.generateLabels = (chart) =>
                originalGenerateLabels(chart).map((label) => ({
                    ...label,
                    fontColor: darkTextColor,
                    color: darkTextColor,
                }));
        }
        return options;
    }
});
