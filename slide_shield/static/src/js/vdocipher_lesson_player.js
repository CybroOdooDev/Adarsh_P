/** @odoo-module **/

/**
 * VdoCipher DRM Player – Non-Fullscreen Lesson Page
 * ===================================================
 * The Fullscreen widget patch (slide_shield_fullscreen_player.js) only
 * runs inside the fullscreen player overlay, because that's the only
 * place `Fullscreen.prototype._renderSlide` ever gets called. The normal
 * lesson page is plain server-rendered HTML (slide.embed_code dumped
 * into a `.ratio.ratio-16x9` div by the slide_main QWeb template) - there
 * is no JS widget tree there to patch.
 *
 * This script does the equivalent swap directly on that page: it reads
 * the same <meta name="slide-shield"> config block already emitted by
 * SlideShieldController (now carrying `category`, `vdocipherVideoId`
 * and `slideId` too), and if this slide is a VdoCipher-protected video,
 * empties the embed container and renders the same OTP/playbackInfo
 * iframe used in fullscreen.
 *
 * KNOWN LIMITATIONS (please read):
 *  - Flash of unprotected content: slide.embed_code's default iframe
 *    (YouTube/Vimeo/etc.) is already present in the initial server-
 *    rendered HTML and may start loading before this script runs and
 *    swaps it out. The fullscreen path doesn't have this problem because
 *    it never renders a default iframe in the first place. If that flash
 *    is unacceptable, the proper fix is a small QWeb override that hides
 *    the embed container by default for VdoCipher slides (server-side
 *    template change, not just JS/CSS) - happy to put that together if
 *    you want it.
 *  - Double OTP fetch: if a learner opens fullscreen after this script
 *    has already rendered the player on the normal page, the Fullscreen
 *    widget will independently fetch its *own* OTP/playbackInfo and
 *    render a second player instance. Both work, but it's two API calls
 *    and two iframes (one hidden) instead of one.
 */

import { rpc } from "@web/core/network/rpc";

(function () {
    'use strict';

    function readShieldConfig() {
        const metaEl = document.querySelector('meta[name="slide-shield"]');
        if (!metaEl) return null;
        try {
            return JSON.parse(metaEl.getAttribute('content') || '{}');
        } catch (_) {
            return null;
        }
    }

    function errorHtml(message, icon) {
        return (
            '<div class="d-flex align-items-center justify-content-center h-100 text-white">' +
                '<div class="text-center">' +
                    '<i class="fa ' + icon + ' fa-3x mb-3"></i>' +
                    '<p class="mb-0">' + message + '</p>' +
                '</div>' +
            '</div>'
        );
    }

    async function renderPlayer(embedWrapper, cfg) {
        // Clear immediately to minimise exposure of the default embed
        embedWrapper.innerHTML = '';

        let otpData;
        try {
            otpData = await rpc('/vdocipher/get_video/' + cfg.vdocipherVideoId, {});
        } catch (err) {
            embedWrapper.innerHTML = errorHtml(
                'Unable to load protected video. Please try again later.', 'fa-exclamation-triangle');
            return;
        }

        if (otpData.error || !otpData.otp || !otpData.playbackInfo) {
            embedWrapper.innerHTML = errorHtml(
                otpData.error || 'Video playback is not available.', 'fa-lock');
            return;
        }

        const iframeSrc = 'https://player.vdocipher.com/v2/?otp=' +
            encodeURIComponent(otpData.otp) +
            '&playbackInfo=' +
            encodeURIComponent(otpData.playbackInfo);

        embedWrapper.innerHTML =
            '<iframe id="vdocipher-player-' + cfg.slideId + '" ' +
                'src="' + iframeSrc + '" ' +
                'style="border:0;width:100%;height:100%" ' +
                'allow="encrypted-media" ' +
                'allowfullscreen="true" ' +
                'frameborder="0"></iframe>';
    }

    function boot() {
        const lessonContainer = document.querySelector('.o_wslides_lesson_content');
        if (!lessonContainer) return; // not the normal lesson page

        const cfg = readShieldConfig();
        if (!cfg || !cfg.active) return;

        const isVdoProtected = cfg.category === 'video' && !!cfg.vdocipherVideoId;
        if (!isVdoProtected) return;

        const embedWrapper = lessonContainer.querySelector('.ratio-16x9');
        if (!embedWrapper) return;

        renderPlayer(embedWrapper, cfg);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
