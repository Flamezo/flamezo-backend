import frappe
from frappe.model.document import Document
from flamezo_backend.flamezo.media.storage import delete_object


class UGCStorySubmission(Document):
	def before_save(self):
		if self.status in ("rejected", "expired") and self.proof_video:
			self._proof_video_to_delete = self.proof_video
			self.proof_video = None

	def on_update(self):
		to_delete = getattr(self, "_proof_video_to_delete", None)
		if to_delete:
			self._proof_video_to_delete = None
			_delete_media_asset(to_delete)

	def on_trash(self):
		if self.proof_video:
			asset_name = self.proof_video
			# Clear DB reference first to bypass foreign key / link validation on deletion
			frappe.db.set_value("UGC Story Submission", self.name, "proof_video", None)
			_delete_media_asset(asset_name)


def _delete_media_asset(asset_name):
	asset = frappe.db.get_value("Media Asset", asset_name, ["name", "raw_object_key"], as_dict=True)
	if asset and asset.get("raw_object_key"):
		try:
			delete_object(asset.get("raw_object_key"))
		except Exception as e:
			frappe.log_error(f"Failed to delete R2 object {asset.get('raw_object_key')}: {e}", "UGC Cleanup")

		try:
			frappe.delete_doc("Media Asset", asset.get("name"), ignore_permissions=True)
		except Exception as e:
			frappe.log_error(f"Failed to delete Media Asset doc {asset.get('name')}: {e}", "UGC Cleanup")
