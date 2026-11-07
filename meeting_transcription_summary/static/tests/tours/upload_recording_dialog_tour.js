import { registry } from "@web/core/registry";
import { UploadRecordingDialog } from "@meeting_transcription_summary/discuss/upload/upload_recording_dialog";

registry.category("web_tour.tours").add("meeting_transcription_summary.upload_recording", {
    steps: () => [
        {
            content: "Open the upload dialog of the channel shown in Discuss",
            trigger: ".o-mail-Thread",
            run() {
                const env = odoo.__WOWL_DEBUG__.root.env;
                const thread = env.services["mail.store"].discuss.thread;
                env.services.dialog.add(UploadRecordingDialog, { thread, close: () => {} });
            },
        },
        {
            content: "Name the meeting",
            trigger: ".modal input[type='text']",
            run: "edit Board meeting",
        },
        {
            content: "Set how long it lasted",
            trigger: ".modal input[type='number']",
            run: "edit 45",
        },
        {
            content: "Pick the recording",
            trigger: ".modal input[type='file']",
            run() {
                const files = new DataTransfer();
                files.items.add(new File(["ID3 fake audio"], "board.mp3", { type: "audio/mpeg" }));
                this.anchor.files = files.files;
                this.anchor.dispatchEvent(new Event("change", { bubbles: true }));
            },
        },
        {
            content: "Upload it",
            trigger: ".modal button.btn-primary:contains('Transcribe'):enabled",
            run: "click",
        },
        {
            content: "The upload is confirmed",
            trigger: ".modal .alert-success:contains('Done!')",
        },
    ],
});
