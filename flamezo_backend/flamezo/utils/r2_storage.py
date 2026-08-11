import frappe
import boto3
from botocore.config import Config


def _r2_settings():
	"""Resolve R2 credentials + public base URL.

	Prefers the flat ``cloudflare_r2_*`` site_config keys (legacy Chills config)
	when they are all present; otherwise falls back to the shared ``media_config``
	block that Media/UGC uploads already use. This means Chills / Crowd / Clubs
	uploads work anywhere media uploads already work — no extra site_config keys
	to add per environment.
	"""
	endpoint = frappe.conf.get("cloudflare_r2_endpoint")
	access_key = frappe.conf.get("cloudflare_r2_access_key")
	secret_key = frappe.conf.get("cloudflare_r2_secret_key")
	bucket = frappe.conf.get("cloudflare_r2_bucket")
	public_base = frappe.conf.get("cloudflare_r2_public_url")

	if not (endpoint and access_key and secret_key and bucket):
		# Fall back to the shared media_config credentials (same R2 setup UGC uses).
		from flamezo_backend.flamezo.media.config import get_r2_config, get_cdn_config

		r2 = get_r2_config()
		endpoint = endpoint or r2["endpoint_url"]
		access_key = access_key or r2["access_key_id"]
		secret_key = secret_key or r2["secret_access_key"]
		bucket = bucket or r2["bucket_name"]
		if not public_base:
			try:
				public_base = get_cdn_config()["base_url"]
			except Exception:
				public_base = ""

	return {
		"endpoint": endpoint,
		"access_key": access_key,
		"secret_key": secret_key,
		"bucket": bucket,
		"public_base": (public_base or "").rstrip("/"),
	}


def _make_client(s):
	return boto3.client(
		"s3",
		endpoint_url=s["endpoint"],
		aws_access_key_id=s["access_key"],
		aws_secret_access_key=s["secret_key"],
		config=Config(signature_version="s3v4"),
		region_name="auto",
	)


def get_r2_client():
	return _make_client(_r2_settings())


def generate_presigned_put(object_key: str, content_type: str, expires: int = 3600) -> str:
	s = _r2_settings()
	return _make_client(s).generate_presigned_url(
		"put_object",
		Params={"Bucket": s["bucket"], "Key": object_key, "ContentType": content_type},
		ExpiresIn=expires,
		HttpMethod="PUT",
	)


def object_exists(object_key: str) -> bool:
	s = _r2_settings()
	client = _make_client(s)
	try:
		client.head_object(Bucket=s["bucket"], Key=object_key)
		return True
	except client.exceptions.ClientError:
		return False
	except Exception:
		return False


def public_url(object_key: str) -> str:
	return f"{_r2_settings()['public_base']}/{object_key}"
