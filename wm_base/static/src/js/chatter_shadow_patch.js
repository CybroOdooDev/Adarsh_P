import { patch } from "@web/core/utils/patch";
import { Message } from "@mail/core/common/message";
import { useEffect } from "@odoo/owl";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        useEffect(
            () => {
                const shadow = typeof this.shadowRoot === "function" ? this.shadowRoot() : this.shadowRoot;
                if (shadow && typeof shadow.appendChild === "function") {
                    const shadowFixStyle = document.createElement("style");
                    shadowFixStyle.textContent = `
                        * {
                            color: #1F2937 !important;
                            background-color: transparent !important;
                        }
                        a, a * {
                            color: #1976D2 !important;
                        }
                    `;
                    shadow.appendChild(shadowFixStyle);
                }
            },
            () => [
                typeof this.shadowRoot === "function" ? this.shadowRoot() : this.shadowRoot,
                this.props.message?.body,
                this.props.message?.richBody,
            ]
        );
    }
});
