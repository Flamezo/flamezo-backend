// Support Thread — turns the Desk form into the agent's reply console.
//
// Shows the conversation on the ticket and adds Reply / Claim / Mark resolved.
// Every action goes through the api/support.py agent endpoints rather than
// writing rows directly, so a reply from here behaves exactly like one from any
// other client: status and unread counts update, and the requester is told.

const SUPPORT_API = "flamezo_backend.flamezo.api.support";

frappe.ui.form.on("Support Thread", {
	refresh(frm) {
		if (frm.is_new()) return;

		render_conversation(frm);
		watch_for_new_messages(frm);

		frm.add_custom_button(__("Reply"), () => reply(frm)).addClass("btn-primary");

		if (!frm.doc.assigned_to) {
			frm.add_custom_button(__("Claim"), () =>
				frappe
					.call({ method: `${SUPPORT_API}.agent_assign`, args: { thread_id: frm.doc.name } })
					.then(() => {
						frappe.show_alert({ message: __("You now own {0}", [frm.doc.name]), indicator: "blue" });
						frm.reload_doc();
					})
			);
		}

		if (["open", "awaiting_agent", "awaiting_customer"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Mark resolved"), () =>
				frappe
					.call({
						method: `${SUPPORT_API}.agent_update_thread`,
						args: { thread_id: frm.doc.name, status: "resolved" },
					})
					.then(() => {
						frappe.show_alert({ message: __("Marked resolved"), indicator: "green" });
						frm.reload_doc();
					})
			);
		}
	},
});

function reply(frm) {
	const who = frm.doc.customer_name || frm.doc.name;
	const d = new frappe.ui.Dialog({
		title: __("Reply to {0}", [who]),
		fields: [
			{
				fieldname: "message",
				fieldtype: "Small Text",
				label: __("Your reply"),
				reqd: 1,
				description: __("Name the specific amount or date, say what happens next, and ask one clear question."),
			},
		],
		primary_action_label: __("Send"),
		primary_action(values) {
			d.disable_primary_action();
			frappe
				.call({
					method: `${SUPPORT_API}.agent_send_message`,
					args: { thread_id: frm.doc.name, message: values.message },
				})
				.then(() => {
					d.hide();
					frappe.show_alert({ message: __("Reply sent to {0}", [who]), indicator: "green" });
					frm.reload_doc();
				})
				.always(() => d.enable_primary_action());
		},
	});
	d.show();
}

function render_conversation(frm) {
	frappe
		.call({ method: `${SUPPORT_API}.agent_get_thread`, args: { thread_id: frm.doc.name } })
		.then((r) => {
			const msgs = (r.message && r.message.data && r.message.data.messages) || [];
			const esc = frappe.utils.escape_html;

			const rows = msgs
				.map((m) => {
					if (m.is_automated) {
						return `<div style="text-align:center;color:var(--text-muted);font-size:12px;margin:8px 0">${esc(m.message)}</div>`;
					}
					const staff = m.sender_type === "agent";
					return `
						<div style="display:flex;justify-content:${staff ? "flex-end" : "flex-start"};margin:6px 0">
							<div style="max-width:78%;padding:8px 12px;border-radius:12px;
								background:${staff ? "var(--primary)" : "var(--control-bg)"};
								color:${staff ? "var(--neutral-white, #fff)" : "var(--text-color)"}">
								<div style="font-size:11px;font-weight:600;opacity:.8;margin-bottom:2px">
									${esc(staff ? m.sender_user || m.sender_name : m.sender_name || "")}${staff ? "" : " · " + esc(m.sender_type)}
								</div>
								<div style="white-space:pre-wrap;word-break:break-word">${esc(m.message || "")}</div>
								<div style="font-size:10px;opacity:.65;margin-top:4px;text-align:right">
									${esc(frappe.datetime.comment_when(m.created_at))}
								</div>
							</div>
						</div>`;
				})
				.join("");

			const body = rows || `<div style="color:var(--text-muted)">${__("No messages yet.")}</div>`;
			const html = `<div style="max-height:420px;overflow-y:auto;padding:4px 2px">${body}</div>`;

			// refresh() runs on every save/reload; drop the previous copy first so
			// the conversation doesn't stack up on the form.
			if (frm._support_convo) frm._support_convo.remove();
			frm._support_convo = frm.dashboard.add_section(html, __("Conversation"));
			frm.dashboard.show();
		});
}

// Keep the open ticket current without anyone pressing refresh.
function watch_for_new_messages(frm) {
	const name = frm.doc.name;

	// Instant: the server pushes support_thread_update to this ticket's room
	// whenever anyone writes (support_message._push_live_update). Bound once.
	if (!frm._support_rt) {
		frm._support_rt = (data) => {
			if (data && data.thread === frm.doc.name) sync_ticket(frm);
		};
		frappe.realtime.on("support_thread_update", frm._support_rt);
	}

	// Safety net for when the realtime socket is down: a cheap timestamp check.
	clearInterval(frm._support_poll);
	let last = frm.doc.last_message_at;
	frm._support_poll = setInterval(() => {
		// Stop once the agent has moved to another page or another ticket.
		if (window.cur_frm !== frm || frm.doc.name !== name) {
			clearInterval(frm._support_poll);
			return;
		}
		frappe.db.get_value("Support Thread", name, "last_message_at").then((r) => {
			const v = r && r.message && r.message.last_message_at;
			if (v && v !== last) {
				last = v;
				sync_ticket(frm);
			}
		});
	}, 8000);
}

function sync_ticket(frm) {
	// Mid-edit on the form? Redraw only the conversation, so unsaved changes
	// aren't thrown away. Otherwise reload fully — status and counters change too.
	if (frm.is_dirty()) {
		render_conversation(frm);
	} else {
		frm.reload_doc();
	}
}
