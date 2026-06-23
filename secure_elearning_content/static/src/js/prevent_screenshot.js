(function() {
    'use strict';

    function isSlidePage() {
        return document.querySelector('.o_wslides_lesson_main') !== null ||
               document.querySelector('.o_wslides_course_main') !== null ||
               document.querySelector('.o_wslides_slide_viewer') !== null ||
               document.querySelector('.o_wslides_fs_main') !== null;
    }

    function initSecurity() {
        if (!isSlidePage()) {
            return;
        }

        // 1. Create and inject security overlay
        let overlay = document.querySelector('.wslides-security-overlay');
        const fsContainer = document.querySelector('.o_wslides_fs_main');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'wslides-security-overlay';
            overlay.innerHTML = `
                <i class="fa fa-lock" aria-hidden="true" title="Protected Content"></i>
                <h2>Protected Content</h2>
                <p>Screenshots, screen recording, and copying are disabled to protect course intellectual property.</p>
            `;
            if (fsContainer) {
                fsContainer.appendChild(overlay);
            } else {
                document.body.appendChild(overlay);
            }
        } else {
            // Move existing overlay if fsContainer is present and is not its current parent
            if (fsContainer && overlay.parentElement !== fsContainer) {
                fsContainer.appendChild(overlay);
            }
        }
        // 3. Prevent dragging images/elements
        document.addEventListener('dragstart', function(e) {
            if (isSlidePage()) {
                e.preventDefault();
            }
        });

        // 4. Intercept hotkeys
        document.addEventListener('keydown', function(e) {
            if (!isSlidePage()) return;

            // Block F10
            if (e.key === 'F10' || e.keyCode === 123) {
                e.preventDefault();
                return false;
            }

            // Block PrintScreen key
            if (e.key === 'PrintScreen' || e.keyCode === 44) {
                e.preventDefault();
                if (navigator.clipboard) {
                    navigator.clipboard.writeText("Protected Content");
                }
                document.body.classList.add('wslides-security-blurred');
                overlay.classList.add('active');
                setTimeout(() => {
                    document.body.classList.remove('wslides-security-blurred');
                    overlay.classList.remove('active');
                }, 3000);
                return false;
            }

            // Block Ctrl+U / Cmd+U (View Source)
            if ((e.ctrlKey || e.metaKey) && (e.key === 'u' || e.key === 'U' || e.keyCode === 85)) {
                e.preventDefault();
                return false;
            }

            // Block Ctrl+P / Cmd+P (Print)
            if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P' || e.keyCode === 80)) {
                e.preventDefault();
                alert("Printing is disabled.");
                return false;
            }

            // Block Ctrl+S / Cmd+S (Save)
            if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S' || e.keyCode === 83)) {
                e.preventDefault();
                return false;
            }

            // Block Ctrl+Shift+I / Cmd+Opt+I (Developer Tools)
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'i' || e.key === 'I' || e.keyCode === 73)) {
                e.preventDefault();
                return false;
            }

            // Block Ctrl+Shift+J / Cmd+Opt+J (Console)
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'j' || e.key === 'J' || e.keyCode === 74)) {
                e.preventDefault();
                return false;
            }

            // Block Ctrl+C / Cmd+C (Copy)
            if ((e.ctrlKey || e.metaKey) && (e.key === 'c' || e.key === 'C' || e.keyCode === 67)) {
                e.preventDefault();
                alert("Copying text is disabled on this course.");
                return false;
            }

            // Block Ctrl+Shift+Alt+R / Cmd+Shift+Alt+R
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.altKey && (e.key === 'r' || e.key === 'R' || e.keyCode === 82)) {
                e.preventDefault();
                return false;
            }
        });

        function blurContent() {
            if (isSlidePage()) {
                document.body.classList.add('wslides-security-blurred');
                const fsElement = document.querySelector('.o_wslides_fs_main');
                if (fsElement) {
                    fsElement.classList.add('wslides-security-blurred');
                }
                if (overlay) {
                    overlay.classList.add('active');
                }
            }
        }

        function focusContent() {
            if (isSlidePage()) {
                document.body.classList.remove('wslides-security-blurred');
                const fsElement = document.querySelector('.o_wslides_fs_main');
                if (fsElement) {
                    fsElement.classList.remove('wslides-security-blurred');
                }
                if (overlay) {
                    overlay.classList.remove('active');
                }
            }
        }

        // 5. Blur content and display overlay when window/tab loses focus
        window.addEventListener('blur', blurContent);
        window.addEventListener('focus', focusContent);

        // 6. Blur content when cursor leaves the window bounds
        document.addEventListener('mouseleave', blurContent);
        document.addEventListener('mouseenter', focusContent);
    }

    function handleFullscreenChange() {
        const fsElement = document.fullscreenElement ||
                          document.webkitFullscreenElement ||
                          document.mozFullScreenElement ||
                          document.msFullscreenElement;

        const overlay = document.querySelector('.wslides-security-overlay');
        if (!overlay) return;

        if (fsElement) {
            // Move overlay inside the fullscreen element so it renders on top of the content in fullscreen mode
            fsElement.appendChild(overlay);
        } else {
            // Move back to body
            document.body.appendChild(overlay);
            // Clear any lingering blur on fullscreen elements
            const fsMains = document.querySelectorAll('.o_wslides_fs_main');
            fsMains.forEach(el => el.classList.remove('wslides-security-blurred'));
        }
    }

    // Register fullscreen change event listeners
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);

    // Initialize on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSecurity);
    } else {
        initSecurity();
    }

    // Monitor dynamic URL navigation changes (for single page transitions in slides)
    let lastUrl = location.href;
    new MutationObserver(() => {
        const url = location.href;
        if (url !== lastUrl) {
            lastUrl = url;
            // Delay slightly to allow DOM to render
            setTimeout(initSecurity, 500);
        }
    }).observe(document, {subtree: true, childList: true});

})();