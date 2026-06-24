/** @odoo-module **/

/**
 * VdoCipher DRM Player – Slide Shield Integration
 * =================================================
 * Extends the Fullscreen player to replace the default YouTube/Vimeo
 * video player with VdoCipher's DRM-protected player when:
 *   1. The slide has shield_active = true
 *   2. The slide category is 'video'
 *   3. A VdoCipher video ID is configured
 *
 * The VdoCipher player uses OTP + playbackInfo tokens fetched from the
 * backend (which proxies the VdoCipher API) to render an encrypted
 * iframe that prevents screen recording and screenshots at the
 * browser/OS level via Widevine/FairPlay DRM.
 */

import Fullscreen from '@website_slides/js/slides_course_fullscreen_player';
import { rpc } from "@web/core/network/rpc";

const OriginalRenderSlide = Fullscreen.prototype._renderSlide;

/**
 * Override _renderSlide to intercept video slides that should use VdoCipher.
 * For all other slides, delegate to the original implementation.
 */
Fullscreen.prototype._renderSlide = async function () {
    const slide = this._slideValue;

    // Check: is this a VdoCipher-protected video?
    const isVdoProtected = (
        slide.category === 'video' &&
        slide.shieldActive &&
        slide.vdocipherVideoId
    );

    if (!isVdoProtected) {
        // Normal rendering path (YouTube, Vimeo, Google Drive, etc.)
        return OriginalRenderSlide.apply(this, arguments);
    }

    // ── VdoCipher rendering path ────────────────────────────────────────

    // Avoid concurrent execution
    if (this._renderSlideRunning) { return; }
    this._renderSlideRunning = true;

    try {
        const $content = this.$('.o_wslides_fs_content');
        $content.empty();

        // Fetch OTP + playbackInfo from our backend proxy
        let otpData;
        try {
            otpData = await rpc('/vdocipher/get_video/' + slide.vdocipherVideoId, {});
        } catch (err) {
            $content.html(
                '<div class="d-flex align-items-center justify-content-center h-100 text-white">' +
                    '<div class="text-center">' +
                        '<i class="fa fa-exclamation-triangle fa-3x mb-3 text-warning"></i>' +
                        '<p class="mb-0">Unable to load protected video. Please try again later.</p>' +
                    '</div>' +
                '</div>'
            );
            return;
        }

        if (otpData.error || !otpData.otp || !otpData.playbackInfo) {
            $content.html(
                '<div class="d-flex align-items-center justify-content-center h-100 text-white">' +
                    '<div class="text-center">' +
                        '<i class="fa fa-lock fa-3x mb-3 text-danger"></i>' +
                        '<p class="mb-0">' + (otpData.error || 'Video playback is not available.') + '</p>' +
                    '</div>' +
                '</div>'
            );
            return;
        }

        // Build VdoCipher iframe URL
        const iframeSrc = 'https://player.vdocipher.com/v2/?otp=' +
            encodeURIComponent(otpData.otp) +
            '&playbackInfo=' +
            encodeURIComponent(otpData.playbackInfo);

        // Render the DRM-protected player
        const $player = $(
            '<div class="player ratio ratio-16x9 embed-responsive-item h-100">' +
                '<iframe ' +
                    'id="vdocipher-player-' + slide.id + '" ' +
                    'src="' + iframeSrc + '" ' +
                    'style="border:0;width:100%;height:100%" ' +
                    'allow="encrypted-media" ' +
                    'allowfullscreen="true" ' +
                    'frameborder="0">' +
                '</iframe>' +
            '</div>'
        );
        $content.append($player);

        // Mark as completed after a reasonable viewing time (similar
        // to the Google Drive approach where auto-set-done is used)
        if (slide.isMember && !slide.hasQuestion && !slide.completed) {
            // Set a timer to mark completed after 30 seconds of viewing
            this._vdoCompletionTimer = setTimeout(() => {
                this.trigger_up('slide_mark_completed', slide);
            }, 30000);
        }

    } finally {
        this._renderSlideRunning = false;
    }
};

// Clean up completion timer when slide changes
const OriginalUpdateSlideValue = Fullscreen.prototype._updateSlideValue;
Fullscreen.prototype._updateSlideValue = function (slide) {
    if (this._vdoCompletionTimer) {
        clearTimeout(this._vdoCompletionTimer);
        this._vdoCompletionTimer = null;
    }
    return OriginalUpdateSlideValue.apply(this, arguments);
};
