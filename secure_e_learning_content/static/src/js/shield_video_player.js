/** @odoo-module **/
/**
 * Slide Shield – Protected Video Player
 * ======================================
 * Intercepts video slide rendering when shield protection is active
 * for both Fullscreen view and standard page views.
 *
 * It:
 *   1. Calls /slide_shield/video/init/<slide_id> to get a signed URL
 *   2. Creates/Sets up a <video> element pointing to the signed stream URL
 *   3. Overlays a dynamic watermark (name + email + timestamp)
 *   4. Sends heartbeats and completion events
 *   5. Disables right-click, download, and picture-in-picture
 */

import Fullscreen from "@website_slides/js/slides_course_fullscreen_player";
import publicWidget from "@web/legacy/js/public/public_widget";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";

// ── Device fingerprint (stored in localStorage) ─────────────────────────────

function getDeviceId() {
    const key = "slide_shield_device_id";
    let id = window.localStorage.getItem(key);
    if (!id) {
        id = window.crypto?.randomUUID
            ? window.crypto.randomUUID()
            : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        window.localStorage.setItem(key, id);
    }
    return id;
}

// ── Event tracking ──────────────────────────────────────────────────────────

async function sendHeartbeat(slideId, token, position) {
    try {
        await rpc("/slide_shield/video/heartbeat", {
            slide_id: slideId,
            token,
            position,
        });
    } catch (err) {
        console.warn("[Shield Video] Heartbeat failed", err);
    }
}

async function sendComplete(slideId, token) {
    try {
        await rpc("/slide_shield/video/complete", {
            slide_id: slideId,
            token,
        });
    } catch (err) {
        console.warn("[Shield Video] Complete event failed", err);
    }
}

// ── Check if slide is shield-video-protected (Fullscreen helper) ────────────

function isShieldProtectedVideo(slide) {
    return (
        slide.category === "video" &&
        !slide.isQuiz &&
        ["1", 1, true, "true", "True"].includes(slide.shieldActive) &&
        ["1", 1, true, "true", "True"].includes(slide.shieldVideoProtected)
    );
}

// ── Shared Playback Initialization Logic ────────────────────────────────────

async function initShieldVideo(wrapper, slideId) {
    const videoEl = wrapper.querySelector("video");
    const statusEl = wrapper.querySelector(".o_shield_video_status");

    const setStatus = (msg) => {
        if (statusEl) {
            statusEl.textContent = msg || "";
            statusEl.classList.toggle("d-none", !msg);
        }
    };

    // Prevent right-click
    wrapper.addEventListener("contextmenu", (e) => e.preventDefault());
    videoEl.addEventListener("contextmenu", (e) => e.preventDefault());

    // Fetch signed URL
    let initData;
    try {
        initData = await rpc(
            `/slide_shield/video/init/${slideId}`,
            { device_id: getDeviceId() }
        );
    } catch (err) {
        setStatus("Failed to load protected video.");
        return;
    }

    if (initData.error) {
        setStatus(initData.error);
        return;
    }

    // Set video source
    videoEl.src = initData.url;
    videoEl.addEventListener("loadedmetadata", () => setStatus(""));
    videoEl.addEventListener("error", () =>
        setStatus("Video playback failed. Please reload.")
    );

    // Heartbeat every 60 seconds
    const heartbeatInterval = setInterval(() => {
        if (!videoEl.paused && !videoEl.ended) {
            sendHeartbeat(slideId, initData.token, videoEl.currentTime);
        }
    }, 60000);

    // Completion event
    videoEl.addEventListener("ended", () => {
        sendComplete(slideId, initData.token);
    });

    // Auto-complete after 30s for safety (matches Odoo behavior)
    const completionTimer = setTimeout(() => {
        sendComplete(slideId, initData.token);
    }, 30000);

    // Cleanup on slide change or widget destroy
    wrapper.addEventListener(
        "shield:destroy",
        () => {
            clearInterval(heartbeatInterval);
            clearTimeout(completionTimer);
            videoEl.pause();
            videoEl.removeAttribute("src");
            videoEl.load();
        },
        { once: true }
    );
}

// ── Fullscreen patch ────────────────────────────────────────────────────────

patch(Fullscreen.prototype, {
    async _renderSlide() {
        const slide = this._slideValue;

        if (!isShieldProtectedVideo(slide)) {
            return super._renderSlide(...arguments);
        }

        const $content = this.$(".o_wslides_fs_content");
        // Destroy previous player if any
        const oldWrapper = $content.find(".o_shield_video_wrapper")[0];
        if (oldWrapper) {
            oldWrapper.dispatchEvent(new Event("shield:destroy"));
        }
        $content.empty();
        $content.removeClass("bg-white");

        // Build player container
        const wrapper = document.createElement("div");
        wrapper.className =
            "o_shield_video_wrapper o_shield_video_wrapper_fs w-100 h-100";
        wrapper.innerHTML = `
            <div class="o_shield_video_box h-100" style="position: relative;">
                <video class="o_shield_video w-100 h-100"
                       controls playsinline preload="metadata"
                       controlsList="nodownload noplaybackrate"
                       disablePictureInPicture style="max-height: 100%; object-fit: contain;">
                </video>
                <div class="o_shield_video_status d-flex align-items-center justify-content-center" style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); color: #fff; z-index: 10;">Loading protected video…</div>
            </div>`;
        $content.append(wrapper);

        await initShieldVideo(wrapper, slide.id);
    },
});

// ── Standard page view widget ───────────────────────────────────────────────

publicWidget.registry.SlideShieldVideoPlayer = publicWidget.Widget.extend({
    selector: '.o_shield_video_wrapper[data-shield-protected="1"]',

    async start() {
        await this._super(...arguments);
        const slideId = parseInt(this.el.getAttribute('data-slide-id') || 0);
        if (slideId) {
            await initShieldVideo(this.el, slideId);
        }
    },

    destroy() {
        this.el.dispatchEvent(new Event("shield:destroy"));
        this._super(...arguments);
    },
});

export default {
    initShieldVideo: initShieldVideo,
    SlideShieldVideoPlayer: publicWidget.registry.SlideShieldVideoPlayer,
};
