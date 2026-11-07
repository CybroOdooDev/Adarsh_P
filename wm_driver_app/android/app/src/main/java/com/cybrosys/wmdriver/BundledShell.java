package com.cybrosys.wmdriver;

import android.content.res.AssetManager;
import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Serves the driver app's screens (page, CSS, JS, icons) from inside the APK,
 * so the app opens whether or not the server can be reached.
 *
 * <p>The files are answered under the server's own address, so the page's API
 * calls stay same-origin and its saved data (key, route, offline queue) stays
 * where earlier versions left it. Before a server is chosen they are answered
 * under {@link #PLACEHOLDER}, a host reserved for exactly this, which never
 * reaches the network. Only GETs for the app's own paths are taken; API calls
 * go to the server as usual.
 *
 * <p>The files come from {@code assets/web}, filled by
 * {@code tools/sync_web_assets.py} from the Odoo module. Changing the screens
 * means a new APK.
 */
final class BundledShell {

    static final String PLACEHOLDER = "https://appassets.androidplatform.net";
    static final String APP_PATH = "/driver/app";

    private static final String STATIC_PREFIX = "/wm_driver_app/static/src/";
    private static final Map<String, String> MIME = new HashMap<>();

    static {
        MIME.put("html", "text/html");
        MIME.put("css", "text/css");
        MIME.put("js", "application/javascript");
        MIME.put("png", "image/png");
        MIME.put("jpg", "image/jpeg");
        MIME.put("svg", "image/svg+xml");
        MIME.put("json", "application/json");
    }

    private final AssetManager assets;

    BundledShell(AssetManager assets) {
        this.assets = assets;
    }

    /**
     * The bundled answer for {@code request}, or null to let it go to the
     * network. Anything on the placeholder host is answered here, if only with
     * a 404, since that host does not exist.
     */
    WebResourceResponse serve(WebResourceRequest request, String server) {
        Uri url = request.getUrl();
        boolean placeholder = sameOrigin(url, PLACEHOLDER);
        if (!placeholder && (server.isEmpty() || !sameOrigin(url, server))) {
            return null;
        }
        String asset = "GET".equalsIgnoreCase(request.getMethod()) ? assetFor(url.getPath()) : null;
        if (asset == null) {
            return placeholder ? notFound() : null;
        }
        try {
            InputStream body = assets.open(asset);
            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-store");
            return new WebResourceResponse(mimeOf(asset), "utf-8", 200, "OK", headers, body);
        } catch (IOException e) {
            return notFound();
        }
    }

    /** Asset path for one of the app's own URL paths, or null for anything else. */
    private static String assetFor(String path) {
        if (path == null) {
            return null;
        }
        if (path.equals(APP_PATH) || path.equals(APP_PATH + "/")) {
            return "web/driver_app.html";
        }
        if (path.startsWith(STATIC_PREFIX) && !path.contains("..")) {
            return "web" + path;
        }
        return null;
    }

    static boolean sameOrigin(Uri a, String b) {
        Uri other = Uri.parse(b);
        return a.getScheme() != null && a.getScheme().equalsIgnoreCase(other.getScheme())
                && a.getHost() != null && a.getHost().equalsIgnoreCase(other.getHost())
                && port(a) == port(other);
    }

    private static int port(Uri uri) {
        if (uri.getPort() != -1) {
            return uri.getPort();
        }
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private static String mimeOf(String asset) {
        int dot = asset.lastIndexOf('.');
        String ext = dot < 0 ? "" : asset.substring(dot + 1).toLowerCase(Locale.ROOT);
        String mime = MIME.get(ext);
        return mime == null ? "application/octet-stream" : mime;
    }

    private static WebResourceResponse notFound() {
        return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found",
                new HashMap<>(), new ByteArrayInputStream(new byte[0]));
    }
}
