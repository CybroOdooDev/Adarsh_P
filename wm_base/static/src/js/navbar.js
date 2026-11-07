import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { onMounted, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Remove duplicate mobile burger menu from systray
registry.category("systray").remove("burger_menu");

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.ui = useService("ui");
        const initialHidden = localStorage.getItem("ef_sidebar_hidden") === "true";
        const initialCollapsed = localStorage.getItem("ef_sidebar_collapsed") === "true";
        this.state = this.state || proxy({});
        Object.assign(this.state, {
            isAppsDashboardOpen: false,
            appsSearchQuery: "",
            isSidebarCollapsed: initialCollapsed,
            isSidebarHidden: initialHidden,
            isMobileSidebarOpen: false,
        });
        onMounted(() => {
            // Enterprise has its own home menu (web_enterprise sets `hm` on
            // the navbar): the theme's apps dashboard is not used there.
            document.body.classList.toggle("ef-enterprise", this.hasEnterpriseHomeMenu);
            if (this.state.isSidebarHidden) {
                document.body.classList.add("ef-sidebar-hidden");
            }
            if (this.state.isSidebarCollapsed) {
                document.body.classList.add("ef-sidebar-collapsed");
            }
        });
    },
    get hasEnterpriseHomeMenu() {
        return Boolean(this.hm);
    },
    get isSmallScreen() {
        return this.ui.isSmall || window.innerWidth < 1025;
    },
    toggleSidebarCollapse() {
        this.state.isSidebarCollapsed = !this.state.isSidebarCollapsed;
        document.body.classList.toggle("ef-sidebar-collapsed", this.state.isSidebarCollapsed);
        localStorage.setItem("ef_sidebar_collapsed", this.state.isSidebarCollapsed ? "true" : "false");
    },
    toggleSidebarVisibility() {
        this.state.isSidebarHidden = !this.state.isSidebarHidden;
        document.body.classList.toggle("ef-sidebar-hidden", this.state.isSidebarHidden);
        localStorage.setItem("ef_sidebar_hidden", this.state.isSidebarHidden ? "true" : "false");
    },
    toggleMobileSidebar() {
        this.state.isMobileSidebarOpen = !this.state.isMobileSidebarOpen;
        document.body.classList.toggle("ef-mobile-sidebar-open", this.state.isMobileSidebarOpen);
    },
    onSidebarAppClick(app) {
        this.onNavBarDropdownItemSelection(app);
        if (this.state.isMobileSidebarOpen) {
            this.toggleMobileSidebar();
        }
    },
    onSidebarMenuClick(menuItem) {
        this.onNavBarDropdownItemSelection(menuItem);
        if (this.state.isMobileSidebarOpen) {
            this.toggleMobileSidebar();
        }
    },
    toggleAppsDashboard() {
        if (this.hasEnterpriseHomeMenu) {
            this.hm.toggle();
            return;
        }
        this.state.isAppsDashboardOpen = !this.state.isAppsDashboardOpen;
        if (this.state.isAppsDashboardOpen) {
            document.body.classList.add("ef-apps-dashboard-active");
            this.state.appsSearchQuery = "";
        } else {
            document.body.classList.remove("ef-apps-dashboard-active");
        }
    },
    onOverlayClick(ev) {
        if (!ev.target.closest(".ef-apps-search-container, .ef-app-card")) {
            this.toggleAppsDashboard();
        }
    },
    onDashboardAppClick(app) {
        this.onNavBarDropdownItemSelection(app);
        this.toggleAppsDashboard();
    },
    get filteredApps() {
        const apps = this.menuService.getApps() || [];
        const query = (this.state.appsSearchQuery || "").toLowerCase().trim();
        if (!query) {
            return apps;
        }
        return apps.filter((app) => (app.name || "").toLowerCase().includes(query));
    },
});
