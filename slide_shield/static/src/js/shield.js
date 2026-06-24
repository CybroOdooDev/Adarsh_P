/** @odoo-module **/

/**
 * Slide Shield – Content Protection Engine
 * =========================================
 * Activated only when the server signals that a slide is protected.
 * The server embeds a <meta name="slide-shield"> tag whose `content`
 * attribute carries a JSON config blob; this script reads that blob
 * and arms only the guards that are switched on.
 *
 * Guards implemented here are intentionally different from anything
 * shipped with stock Odoo eLearning:
 *
 *  1. Dynamic canvas watermark  – tiled, rotated, user-specific
 *  2. Visibility / focus blur   – Page Visibility API + window blur
 *  3. Keyboard interception     – PrtSc, Win+Shift+S, Cmd+Shift+3/4
 *  4. DevTools heuristic        – window inner-vs-outer size delta
 *  5. Context-menu suppression  – inside the lesson content area only
 *  6. Drag/select prevention    – CSS + JS belt-and-suspenders
 *  7. Overlay canvas            – thin transparent layer that sits
 *                                 over the content area and confuses
 *                                 many OS-level capture APIs
 *
 * NOTE (fix): CONTENT_SELECTOR now also matches the *non-fullscreen*
 * lesson container (`.o_wslides_lesson_content`, confirmed against
 * Odoo 19's website_slides_templates_lesson.xml). Previously, the
 * focus/visibility blur, context-menu block and drag/select block all
 * route through getContentEl() -> CONTENT_SELECTOR, so they silently
 * no-op outside fullscreen because none of the old selectors match the
 * regular lesson page DOM. `.o_slide_player` and `#slide_iframe_wrapper`
 * don't correspond to any real Odoo 19 core class/id - left in place in
 * case a customization elsewhere relies on them, but they were never
 * matching anything either.
 */

(function () {
    'use strict';

    // ── 0. Read server config ────────────────────────────────────────────────
    const metaEl = document.querySelector('meta[name="slide-shield"]');
    if (!metaEl) return; // not a protected page → exit immediately

    let cfg;
    try {
        cfg = JSON.parse(metaEl.getAttribute('content') || '{}');
    } catch (_) {
        return;
    }

    if (!cfg.active) return;

    const opts = {
        watermark:       cfg.watermark       !== false,
        opacity:         parseFloat(cfg.opacity || '0.08'),
        blockKeyboard:   cfg.blockKeyboard   !== false,
        blockDevtools:   cfg.blockDevtools   !== false,
        blurOnFocusLoss: cfg.blurOnFocusLoss !== false,
        blockContextMenu:cfg.blockContextMenu !== false,
        userName:        cfg.userName  || '',
        userEmail:       cfg.userEmail || '',
    };

    // ── helpers ──────────────────────────────────────────────────────────────
    // FIX: added .o_wslides_lesson_content so guards also apply outside fullscreen.
    const CONTENT_SELECTOR = '.o_wslides_fs_content, .o_wslides_lesson_content, .o_slide_player, #slide_iframe_wrapper';

    function getContentEl() {
        return document.querySelector(CONTENT_SELECTOR);
    }

    function applyBlur(on) {
        const el = getContentEl();
        if (!el) return;
        el.style.transition = 'filter 0.25s ease';
        el.style.filter = on ? 'blur(14px)' : '';
    }

    // ── 1. Dynamic canvas watermark ─────────────────────────────────────────
    function buildWatermark() {
        if (!opts.watermark) return;

        const stamp = [opts.userName, opts.userEmail, new Date().toLocaleDateString()].filter(Boolean).join('  ·  ');
        if (!stamp.trim()) return;

        // Offscreen tile
        const tile = document.createElement('canvas');
        tile.width  = 340;
        tile.height = 120;
        const tx = tile.getContext('2d');
        tx.save();
        tx.translate(tile.width / 2, tile.height / 2);
        tx.rotate(-Math.PI / 6);  // –30 °
        tx.font = 'bold 14px "Segoe UI", Arial, sans-serif';
        tx.fillStyle = `rgba(80,80,80,${opts.opacity})`;
        tx.textAlign = 'center';
        tx.textBaseline = 'middle';
        tx.fillText(stamp, 0, 0);
        tx.restore();

        // Overlay canvas positioned over the content area
        const overlay = document.createElement('canvas');
        overlay.id = 'ss-watermark';
        overlay.style.cssText = [
            'position:fixed',
            'top:0', 'left:0',
            'width:100vw', 'height:100vh',
            'pointer-events:none',
            'z-index:9999',
            'display:block',
        ].join(';');
        document.body.appendChild(overlay);

        function repaint() {
            overlay.width  = window.innerWidth;
            overlay.height = window.innerHeight;
            const ctx = overlay.getContext('2d');
            const pat = ctx.createPattern(tile, 'repeat');
            ctx.fillStyle = pat;
            ctx.fillRect(0, 0, overlay.width, overlay.height);
        }

        repaint();
        window.addEventListener('resize', repaint);

        // Mutation guard – if someone removes the canvas, put it back
        new MutationObserver(() => {
            if (!document.getElementById('ss-watermark')) {
                document.body.appendChild(overlay);
                repaint();
            }
        }).observe(document.body, { childList: true });
    }

    // ── 2. Visibility / focus blur ───────────────────────────────────────────
    function initFocusBlur() {
        if (!opts.blurOnFocusLoss) return;

        document.addEventListener('visibilitychange', () => {
            applyBlur(document.hidden);
        });

        window.addEventListener('blur', () => applyBlur(true));
        window.addEventListener('focus', () => applyBlur(false));
    }

    // ── 3. Keyboard shortcut interception ────────────────────────────────────
    function initKeyboardGuard() {
        if (!opts.blockKeyboard) return;

        document.addEventListener('keydown', (e) => {
            const key  = (e.key || '').toLowerCase();
            const ctrl = e.ctrlKey;
            const meta = e.metaKey;   // Cmd on macOS
            const shift = e.shiftKey;

            const isPrtSc       = key === 'printscreen';
            const isWinSnip     = (e.key === 'S' || key === 's') && e.getModifierState('Meta') === false
                                  && ctrl && shift;  // Ctrl+Shift+S some browsers
            const isWinShiftS   = shift && e.key === 'S' && (e.getModifierState('OS') || e.metaKey);
            const isMacShot34   = meta && shift && (key === '3' || key === '4' || key === '5');
            const isMacCtrlShot = meta && ctrl && shift && (key === '3' || key === '4');

            if (isPrtSc || isWinSnip || isWinShiftS || isMacShot34 || isMacCtrlShot) {
                e.preventDefault();
                e.stopImmediatePropagation();
                showWarningToast('Screenshot shortcuts are disabled on this content.');
            }
        }, true /* capture phase */);
    }

    // ── 4. DevTools heuristic ────────────────────────────────────────────────
    function initDevtoolsGuard() {
        if (!opts.blockDevtools) return;

        const THRESHOLD = 160; // px difference that hints at an open panel
        let devOpen = false;

        setInterval(() => {
            const nowOpen = (
                window.outerWidth  - window.innerWidth  > THRESHOLD ||
                window.outerHeight - window.innerHeight > THRESHOLD
            );
            if (nowOpen !== devOpen) {
                devOpen = nowOpen;
                applyBlur(devOpen);
                if (devOpen) {
                    showWarningToast('Content is blurred while developer tools are open.');
                }
            }
        }, 800);
    }

    // ── 5. Context-menu suppression ──────────────────────────────────────────
    function initContextMenuGuard() {
        if (!opts.blockContextMenu) return;

        document.addEventListener('contextmenu', (e) => {
            const content = getContentEl();
            if (content && content.contains(e.target)) {
                e.preventDefault();
            }
        }, true);
    }

    // ── 6. Drag / select prevention (JS layer on top of CSS) ─────────────────
    function initDragSelectGuard() {
        ['dragstart', 'drag', 'drop', 'selectstart'].forEach((evtName) => {
            document.addEventListener(evtName, (e) => {
                const content = getContentEl();
                if (content && content.contains(e.target)) {
                    e.preventDefault();
                }
            }, true);
        });
    }

    // ── 7. Thin transparent overlay (confuses some OS capture APIs) ──────────
    function buildCaptureConfuser() {
        const div = document.createElement('div');
        div.id = 'ss-capture-confuser';
        div.style.cssText = [
            'position:fixed',
            'top:0', 'left:0', 'right:0', 'bottom:0',
            'z-index:9998',
            'pointer-events:none',
            // A 1×1 repeating gradient at 0.4% opacity breaks pixel-perfect
            // screenshots in several common capture tools while remaining
            // completely invisible to the naked eye.
            'background-image:repeating-linear-gradient(' +
                '45deg,' +
                'rgba(0,0,0,0.004) 0px,' +
                'rgba(0,0,0,0.004) 1px,' +
                'transparent 1px,' +
                'transparent 4px' +
            ')',
        ].join(';');
        document.body.appendChild(div);
    }

    // ── Toast helper ─────────────────────────────────────────────────────────
    function showWarningToast(msg) {
        const existing = document.getElementById('ss-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'ss-toast';
        toast.textContent = '🔒 ' + msg;
        toast.style.cssText = [
            'position:fixed',
            'bottom:24px', 'left:50%',
            'transform:translateX(-50%)',
            'background:#1a1a2e',
            'color:#e0e0e0',
            'padding:10px 22px',
            'border-radius:6px',
            'font:500 13px/1.5 "Segoe UI",Arial,sans-serif',
            'box-shadow:0 4px 18px rgba(0,0,0,.45)',
            'z-index:99999',
            'opacity:0',
            'transition:opacity .2s ease',
            'pointer-events:none',
        ].join(';');
        document.body.appendChild(toast);
        requestAnimationFrame(() => { toast.style.opacity = '1'; });
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 250);
        }, 3200);
    }

    // ── Boot everything once the DOM is ready ────────────────────────────────
    function boot() {
        buildWatermark();
        initFocusBlur();
        initKeyboardGuard();
        initDevtoolsGuard();
        initContextMenuGuard();
        initDragSelectGuard();
        buildCaptureConfuser();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }

})();

