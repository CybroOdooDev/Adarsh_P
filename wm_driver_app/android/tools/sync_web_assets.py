#!/usr/bin/env python3
"""Copy the driver app's screens from the Odoo module into the APK's assets.

The APK serves these files itself, so the app opens without the server.
Run it whenever the module's driver app (template, app.js, app.css, icons)
changes, then build a new APK:

    python3 tools/sync_web_assets.py [path/to/wm_driver_app]

Writes app/src/main/assets/web/:
    driver_app.html                     <- views/driver_app_template.xml
    wm_driver_app/static/src/css|js|img <- the module's static files
"""
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODULE = ROOT.parent  # this project lives in wm_driver_app/android
OUT = ROOT / 'app' / 'src' / 'main' / 'assets' / 'web'
STATIC = ('css', 'js', 'img')


def render_shell(template_xml):
    """The template's <html>, as Odoo serves it (it has no QWeb directives).

    The markup is copied as written rather than re-serialized, which would
    rename the inline SVG namespace; entities like &#x2192; are valid HTML.
    """
    text = template_xml.read_text(encoding='utf-8')
    root = ET.fromstring(text)
    if root.find(".//template[@id='driver_app_page']/html") is None:
        sys.exit(f'{template_xml}: template driver_app_page has no <html> element')
    if any(k.startswith('t-') for el in root.iter() for k in el.attrib):
        sys.exit(f'{template_xml}: QWeb directives found; render the page instead of copying it')
    start, end = text.index('<html'), text.rindex('</html>') + len('</html>')
    page = text[start:end]
    # The web manifest only matters for installing the PWA from a browser.
    page = re.sub(r'\s*<link rel="manifest"[^>]*>', '', page)
    return '<!DOCTYPE html>\n' + page + '\n'


def main():
    module = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_MODULE
    template = module / 'views' / 'driver_app_template.xml'
    if not template.is_file():
        sys.exit(f'Not the wm_driver_app module: {module}')

    if OUT.exists():
        shutil.rmtree(OUT)
    static_out = OUT / 'wm_driver_app' / 'static' / 'src'
    for sub in STATIC:
        shutil.copytree(module / 'static' / 'src' / sub, static_out / sub)
    # The service worker is for browsers; the APK serves the files itself.
    (static_out / 'js' / 'sw.js').unlink(missing_ok=True)
    sys.stdout.write(f'Synced driver app screens from {module} into {OUT.relative_to(ROOT)}\n')


if __name__ == '__main__':
    main()
