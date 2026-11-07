package com.cybrosys.wmdriver;

import android.content.Context;
import android.content.SharedPreferences;

/** Stores the Odoo server address typed on the app's sign-in screen. */
final class ServerPrefs {

    private static final String FILE = "wm_driver_prefs";
    private static final String KEY_SERVER = "server_url";

    private ServerPrefs() {
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    static String getServerUrl(Context context) {
        return prefs(context).getString(KEY_SERVER, "");
    }

    static void save(Context context, String serverUrl) {
        prefs(context).edit().putString(KEY_SERVER, serverUrl).apply();
    }

    static void clear(Context context) {
        prefs(context).edit().clear().apply();
    }

    /**
     * Turns what the driver typed into a usable base URL.
     *
     * <p>A bare host keeps http for anything that looks local (an IP address,
     * localhost, a .local name or an explicit port) and https otherwise, which
     * is what public tunnels such as ngrok always serve.
     */
    static String normalizeUrl(String raw) {
        String url = raw == null ? "" : raw.trim();
        if (url.isEmpty()) {
            return "";
        }
        if (!url.matches("(?i)^https?://.*")) {
            url = (looksLocal(url) ? "http://" : "https://") + url;
        }
        while (url.endsWith("/")) {
            url = url.substring(0, url.length() - 1);
        }
        return url;
    }

    private static boolean looksLocal(String hostPart) {
        String host = hostPart.split("/")[0];
        return host.matches("^\\d{1,3}(\\.\\d{1,3}){3}(:\\d+)?$")
                || host.startsWith("localhost")
                || host.endsWith(".local")
                || host.matches("^[^.:]+:\\d+$");
    }
}
