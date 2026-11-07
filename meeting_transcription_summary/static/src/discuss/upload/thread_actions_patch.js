import { registerThreadAction } from "@mail/core/common/thread_actions";
import { UploadRecordingDialog } from "./upload_recording_dialog";
import { _t } from "@web/core/l10n/translation";

registerThreadAction("upload-meeting-recording", {
    // internal users only, like the upload route and the summary's access rights
    condition: ({ channel, store }) => Boolean(channel) && store?.self_user?.share === false,
    icon: "video_file",
    iconClass: "oi-fw",
    name: _t("Upload Meeting Recording"),
    onSelected({ store, thread }) {
        store.env.services.dialog.add(UploadRecordingDialog, {
            thread,
            close: () => {},
        });
    },
    sequence: 35,
});
