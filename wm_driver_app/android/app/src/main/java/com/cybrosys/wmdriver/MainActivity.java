package com.cybrosys.wmdriver;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.provider.Settings;
import android.view.View;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.ServiceWorkerClient;
import android.webkit.ValueCallback;
import android.webkit.ServiceWorkerController;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * Hosts the driver app. Its screens ship inside the APK ({@link BundledShell}),
 * so it opens with or without the server; only the data (route, status
 * updates) needs the server, and the app queues updates while it is away.
 *
 * <p>The server address, database and API key are all entered on the app's own
 * sign-in screen. When the driver types a server there, the page asks this
 * activity (through {@link Bridge}) to move to that server's address.
 */
public class MainActivity extends AppCompatActivity {

    private static final int REQ_LOCATION = 101;

    private WebView webView;
    private View errorView;
    private TextView errorText;

    private BundledShell shell;

    /** The page's file input waiting for a photo, and where the camera writes it. */
    private ValueCallback<Uri[]> pendingFileCallback;
    private Uri pendingCameraUri;

    private final ActivityResultLauncher<Intent> photoPicker = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(), result -> {
                Uri[] picked = null;
                if (result.getResultCode() == RESULT_OK) {
                    Intent data = result.getData();
                    if (data != null && data.getData() != null) {
                        picked = new Uri[]{data.getData()};      // chosen from the gallery
                    } else if (pendingCameraUri != null) {
                        picked = new Uri[]{pendingCameraUri};    // taken with the camera
                    }
                }
                deliverFiles(picked);
            });

    /** Location requests from the page waiting for the driver's answer to the permission prompt. */
    private final List<PendingGeo> pendingGeo = new ArrayList<>();

    private static final class PendingGeo {
        final String origin;
        final GeolocationPermissions.Callback callback;

        PendingGeo(String origin, GeolocationPermissions.Callback callback) {
            this.origin = origin;
            this.callback = callback;
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setContentView(R.layout.activity_main);
        webView = findViewById(R.id.webview);
        errorView = findViewById(R.id.error_view);
        errorText = findViewById(R.id.error_text);

        findViewById(R.id.btn_retry).setOnClickListener(v -> load());
        findViewById(R.id.btn_change_server).setOnClickListener(v -> changeServer());

        shell = new BundledShell(getAssets());
        configureWebView();
        load();
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setGeolocationEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);

        // A non-browser user agent keeps ngrok's free-tier interstitial away
        // from the API calls; the app itself never looks at it.
        settings.setUserAgentString("WMDriverApp/" + BuildConfig.VERSION_NAME + " (Android "
                + Build.VERSION.RELEASE + ")");

        webView.addJavascriptInterface(new Bridge(), "WMDriverNative");

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            // A service worker left by an earlier version would fetch the app's
            // files past the client below; answer those from the APK too.
            ServiceWorkerController.getInstance().setServiceWorkerClient(new ServiceWorkerClient() {
                @Override
                public WebResourceResponse shouldInterceptRequest(WebResourceRequest request) {
                    return shell.serve(request, ServerPrefs.getServerUrl(MainActivity.this));
                }
            });
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return shell.serve(request, ServerPrefs.getServerUrl(MainActivity.this));
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showError("The app could not open.\n\n" + error.getDescription());
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onGeolocationPermissionsShowPrompt(String origin,
                                                           GeolocationPermissions.Callback callback) {
                if (hasLocationPermission()) {
                    callback.invoke(origin, true, true);
                    return;
                }
                // One system prompt answers every request made while it is open
                pendingGeo.add(new PendingGeo(origin, callback));
                if (pendingGeo.size() == 1) {
                    ActivityCompat.requestPermissions(MainActivity.this, new String[]{
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION,
                    }, REQ_LOCATION);
                }
            }

            /**
             * A WebView ignores {@code <input type="file">} unless the app opens
             * a picker itself: offer the camera first, then the gallery.
             */
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                deliverFiles(null);  // an earlier picker never answered
                pendingFileCallback = callback;
                try {
                    photoPicker.launch(buildPhotoChooser(params));
                } catch (Exception e) {
                    deliverFiles(null);
                    return false;
                }
                return true;
            }
        });
    }

    private Intent buildPhotoChooser(WebChromeClient.FileChooserParams params) {
        Intent gallery = new Intent(Intent.ACTION_GET_CONTENT);
        gallery.addCategory(Intent.CATEGORY_OPENABLE);
        gallery.setType("image/*");

        Intent chooser = Intent.createChooser(gallery, getString(R.string.add_photo));
        pendingCameraUri = null;
        try {
            File dir = new File(getCacheDir(), "photos");
            if (!dir.isDirectory() && !dir.mkdirs()) {
                throw new IOException("cannot create " + dir);
            }
            File photo = File.createTempFile("stop_", ".jpg", dir);
            pendingCameraUri = FileProvider.getUriForFile(this,
                    getPackageName() + ".fileprovider", photo);
            Intent camera = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
            camera.putExtra(MediaStore.EXTRA_OUTPUT, pendingCameraUri);
            camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    | Intent.FLAG_GRANT_READ_URI_PERMISSION);
            chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{camera});
        } catch (IOException | IllegalArgumentException e) {
            pendingCameraUri = null;  // gallery only
        }
        return chooser;
    }

    /** Answers the page's file input; null means the driver cancelled. */
    private void deliverFiles(Uri[] files) {
        if (pendingFileCallback != null) {
            pendingFileCallback.onReceiveValue(files);
            pendingFileCallback = null;
        }
        pendingCameraUri = null;
    }

    /**
     * Precise or approximate location: on Android 12+ the driver may grant only
     * approximate, which still places a stop well enough.
     */
    private boolean hasLocationPermission() {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                == PackageManager.PERMISSION_GRANTED
                || ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION)
                == PackageManager.PERMISSION_GRANTED;
    }

    /** Opens the app on the saved server's address, or the placeholder before there is one. */
    private void load() {
        errorView.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
        String server = ServerPrefs.getServerUrl(this);
        webView.loadUrl((server.isEmpty() ? BundledShell.PLACEHOLDER : server) + BundledShell.APP_PATH);
    }

    /**
     * Forgets the server and returns to the sign-in screen. What the app saved
     * for that server stays with it, should the driver come back to it.
     */
    private void changeServer() {
        ServerPrefs.clear(this);
        load();
    }

    /** Called from the page as {@code window.WMDriverNative}. */
    private final class Bridge {

        /**
         * Moves the app to the server the driver typed (its scheme, host and
         * port) and returns that address, or "" if it is not one. Typing the
         * server the app is already on changes nothing.
         */
        @JavascriptInterface
        public String setServer(String raw) {
            Uri parsed = Uri.parse(ServerPrefs.normalizeUrl(raw));
            if (parsed.getHost() == null || parsed.getHost().isEmpty()) {
                return "";
            }
            String origin = parsed.getScheme().toLowerCase(java.util.Locale.ROOT) + "://" + parsed.getEncodedAuthority();
            if (!origin.equals(ServerPrefs.getServerUrl(MainActivity.this))) {
                ServerPrefs.save(MainActivity.this, origin);
                runOnUiThread(MainActivity.this::load);
            }
            return origin;
        }

        /**
         * Opens this app's system settings, where the driver can turn location
         * back on after refusing it (Android stops asking after two refusals).
         */
        @JavascriptInterface
        public void openAppSettings() {
            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.fromParts("package", getPackageName(), null));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            runOnUiThread(() -> startActivity(intent));
        }
    }

    private void showError(String message) {
        webView.setVisibility(View.GONE);
        errorText.setText(message);
        errorView.setVisibility(View.VISIBLE);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_LOCATION) {
            return;
        }
        boolean granted = hasLocationPermission();
        for (PendingGeo request : pendingGeo) {
            request.callback.invoke(request.origin, granted, granted);
        }
        pendingGeo.clear();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Back from the background (or from the settings screen): the page
        // becomes visible again and resumes following the position.
        webView.onResume();
    }

    @Override
    protected void onPause() {
        // Hides the page, which stops its location tracking while the app is
        // in the background instead of keeping GPS on.
        webView.onPause();
        super.onPause();
    }

    @Override
    public void onBackPressed() {
        // The app is a single page, so back offers to leave or switch server.
        String server = ServerPrefs.getServerUrl(this);
        new AlertDialog.Builder(this)
                .setTitle(R.string.app_name)
                .setMessage(server.isEmpty() ? getString(R.string.no_server) : server)
                .setPositiveButton(R.string.change_server, (dialog, which) -> changeServer())
                .setNegativeButton(R.string.exit, (dialog, which) -> finish())
                .setNeutralButton(R.string.cancel, null)
                .show();
    }
}
