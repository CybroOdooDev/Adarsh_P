/** @odoo-module */
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.protect_course_content_window = publicWidget.Widget.extend({
    selector: '.o_wslides_lesson_main',

    async start() {
        await this._super(...arguments);

        // Create overlay element with a lock icon and secure message
        this.overlayEl = document.createElement('div');
        this.overlayEl.className = 'wslides-security-overlay';
        this.overlayEl.innerHTML = `
            <div class="wslides-security-card">
                <div class="wslides-security-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                        <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
                    </svg>
                </div>
                <div class="wslides-security-title">Content Protected</div>
                <div class="wslides-security-desc">
                    Screenshots and screen recording are restricted on this page to protect intellectual property.
                </div>
            </div>
        `;
        this.el.appendChild(this.overlayEl);

        // Bind event handlers to this context
        this._onWindowBlur = this._onWindowBlur.bind(this);
        this._onWindowFocus = this._onWindowFocus.bind(this);
        this._onVisibilityChange = this._onVisibilityChange.bind(this);
        this._onMouseLeave = this._onMouseLeave.bind(this);
        this._onMouseEnter = this._onMouseEnter.bind(this);
        this._onKeyDown = this._onKeyDown.bind(this);
        this._onKeyUp = this._onKeyUp.bind(this);
        this._onContextMenu = this._onContextMenu.bind(this);
        this._onSelectStart = this._onSelectStart.bind(this);
        this._onDragStart = this._onDragStart.bind(this);
        this._onCopy = this._onCopy.bind(this);

        // Attach event listeners
        window.addEventListener('blur', this._onWindowBlur);
        window.addEventListener('focus', this._onWindowFocus);
        document.addEventListener('visibilitychange', this._onVisibilityChange);
        document.addEventListener('mouseleave', this._onMouseLeave);
        document.addEventListener('mouseenter', this._onMouseEnter);
        document.addEventListener('keydown', this._onKeyDown, true);
        document.addEventListener('keyup', this._onKeyUp, true);
        document.addEventListener('contextmenu', this._onContextMenu);
        document.addEventListener('selectstart', this._onSelectStart);
        document.addEventListener('dragstart', this._onDragStart);
        document.addEventListener('copy', this._onCopy);
    },

    // Functions to obscure/restore content
    _obscureContent() {
        this.el.classList.add('wslides-security-obscured');
    },

    _restoreContent() {
        this.el.classList.remove('wslides-security-obscured');
    },

    // Window Focus / Blur handlers
    _onWindowBlur() {
        this._obscureContent();
    },

    _onWindowFocus() {
        this._restoreContent();
    },

    _onVisibilityChange() {
        if (document.hidden) {
            this._obscureContent();
        } else {
            this._restoreContent();
        }
    },

    // Mouse boundaries
    _onMouseLeave() {
        this._obscureContent();
    },

    _onMouseEnter() {
        this._restoreContent();
    },

    // Key event blocking and screenshot detection
    _onKeyDown(e) {
        const isPrintScreen = e.key === 'PrintScreen' || e.keyCode === 44;
        if (isPrintScreen) {
            this._obscureContent();
            this._attemptClipboardClear();
        }

        // Block printing (Ctrl+P / Cmd+P)
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p') {
            e.preventDefault();
            e.stopPropagation();
        }

        // Block saving (Ctrl+S / Cmd+S)
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            e.stopPropagation();
        }

        // Block DevTools F12
        if (e.key === 'F12') {
            e.preventDefault();
            e.stopPropagation();
        }

        // Block DevTools key combos (Ctrl+Shift+I / J / C)
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && ['i', 'j', 'c'].includes(e.key.toLowerCase())) {
            e.preventDefault();
            e.stopPropagation();
        }
    },

    _onKeyUp(e) {
        const isPrintScreen = e.key === 'PrintScreen' || e.keyCode === 44;
        if (isPrintScreen) {
            this._attemptClipboardClear();
            // Hold the obscured state briefly to cover the screenshot process
            setTimeout(() => {
                this._restoreContent();
            }, 1000);
        }
    },

    // Clipboard manipulation
    _attemptClipboardClear() {
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText('Content Protected');
            }
        } catch (err) {
            // Silence clipboard access errors
        }
    },

    // Prevent default copying & dragging behaviors
    _onContextMenu(e) {
        e.preventDefault();
    },

    _onSelectStart(e) {
        e.preventDefault();
    },

    _onDragStart(e) {
        e.preventDefault();
    },

    _onCopy(e) {
        e.preventDefault();
    },

    // Clean up event listeners on destroy
    destroy() {
        window.removeEventListener('blur', this._onWindowBlur);
        window.removeEventListener('focus', this._onWindowFocus);
        document.removeEventListener('visibilitychange', this._onVisibilityChange);
        document.removeEventListener('mouseleave', this._onMouseLeave);
        document.removeEventListener('mouseenter', this._onMouseEnter);
        document.removeEventListener('keydown', this._onKeyDown, true);
        document.removeEventListener('keyup', this._onKeyUp, true);
        document.removeEventListener('contextmenu', this._onContextMenu);
        document.removeEventListener('selectstart', this._onSelectStart);
        document.removeEventListener('dragstart', this._onDragStart);
        document.removeEventListener('copy', this._onCopy);

        if (this.overlayEl) {
            this.overlayEl.remove();
        }
        this._super(...arguments);
    }
});
