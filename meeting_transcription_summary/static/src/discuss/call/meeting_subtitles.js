import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class MeetingSubtitles extends Component {
    static template = "meeting_transcription_summary.MeetingSubtitles";

    props = useProps({ channel: t.object().optional() });

    setup() {
        this.speechService = useService("discuss_meeting_ai.speech");
        // the service state is reactive, so new captions re-render this component
        this.state = this.speechService.state;
    }
}
