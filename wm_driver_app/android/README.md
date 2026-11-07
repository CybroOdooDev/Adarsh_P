    # WM Driver — Android shell

The WM Driver app for Odoo 20, as an Android app. It lives in the
`wm_driver_app` module's `android/` folder. It started as a copy of the Odoo 19
app (`wm-driver-android-v2`) pointed at the v20 module, and is installed as a separate app: package id
`com.cybrosys.wmdriver.v20`, named *WM Driver 20*, so it sits next to the v19
*WM Driver* on the same phone.

**It opens on its own.** The screens (page, CSS, JS, icons) are built into the
APK under `app/src/main/assets/web`, so the app starts whether or not the server
is reachable, even on first launch. Only the data needs the server: today's
route is loaded from it, and status updates made offline are queued on the
phone and sent when it is back.

**Sign-in happens in the app.** On first launch the driver enters the server
address, picks the database and pastes the API key on the app's own screen.
When the server address is entered, the app moves to that server's address (the
screens still come from the APK), so every API call is same-origin and the
database list loads. *Change server* (back button, then *Change server*)
returns to an empty sign-in screen.

**Screen changes need a new APK.** The app never loads the screens from the
server. After changing the module's `driver_app_template.xml`, `app.js`,
`app.css` or icons, build a new APK: every build first copies them in with
`tools/sync_web_assets.py`, from the module this folder is in (`..`), or from
`-PWM_MODULE_DIR=/path/to/wm_driver_app`. `assets/web` is generated, so it is
not kept in the module.

Server side, the module only needs to be installed: the app uses
`/driver/app/dbs` (with `/web/database/list` as a fallback) and `/driver/api/*`.

## Build

```bash
export JAVA_HOME=$HOME/.bubblewrap/jdk/jdk-17.0.11+9
export ANDROID_HOME=$HOME/.bubblewrap/android_sdk
$(ls -d ~/.gradle/wrapper/dists/gradle-8.11.1-bin/*/gradle-8.11.1)/bin/gradle --no-daemon assembleRelease
```

Output: `app/build/outputs/apk/release/app-release.apk`.

### Signing

Releases are signed with `~/.wm-driver-keystore/wm-driver-2026.jks` (alias
`wmdriver`, `CN=WM Driver App, O=Cybrosys Technologies, C=IN`, created
2026-11-02, valid to 2054). Certificate SHA-256:
`C1:1C:44:0E:F1:2D:0F:90:48:E0:BC:FA:2B:6F:9D:BF:74:B7:92:27:50:0E:37:09:72:F5:80:64:EA:4A:85:B8`.

Its password is in `~/.wm-driver-keystore/keystore.properties`, which the build
reads from there. A `keystore.properties` in this folder takes precedence (or pass `-PWM_KEYSTORE=... -PWM_KEYSTORE_PASSWORD=...
-PWM_KEY_ALIAS=... -PWM_KEY_PASSWORD=...`, which win over the file). Neither
the `.jks` nor its password belongs in the repo.

**Keep both backed up somewhere safe.** Every future update must be signed with
this key; without it, phones have to uninstall the app before installing a new
one. Earlier APKs (the TWA app signed with `android.keystore`, and the 29 Oct
build) used other keys, so phones with those must uninstall them once.

## Installing

`com.cybrosys.wmdriver.v20` is a new package id, so the first install never
conflicts with anything; later builds update it as long as they are signed with
the same key (above). The v19 app (`com.cybrosys.wmdriver`) is not affected.

Check which key an APK carries before shipping it:

```bash
$ANDROID_HOME/build-tools/34.0.0/apksigner verify --print-certs app.apk | grep DN
```

## Server requirements

* `wm_driver_app` installed in the database being served.
* No `dbfilter` is needed: the app never loads `/driver/app` from the server,
  and every API call names its database (`X-Odoo-Database`).
* Behind a tunnel or reverse proxy, set `proxy_mode = True`.
* GPS is requested at runtime; the status log sends coordinates with each update.
* Plain HTTP is permitted so LAN addresses work. The service worker only
  registers on HTTPS (or localhost), so offline caching of the shell needs a
  tunnel — the IndexedDB status queue works either way.
