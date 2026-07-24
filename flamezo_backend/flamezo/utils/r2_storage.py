import frappe
import boto3
from botocore.config import Config


def _conf(key):
    val = frappe.conf.get(key)
    if not val:
        frappe.throw(f"Missing site_config key: {key}")
    return val


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=_conf("cloudflare_r2_endpoint"),
        aws_access_key_id=_conf("cloudflare_r2_access_key"),
        aws_secret_access_key=_conf("cloudflare_r2_secret_key"),
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def generate_presigned_put(object_key: str, content_type: str, expires: int = 3600) -> str:
    client = get_r2_client()
    bucket = _conf("cloudflare_r2_bucket")
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": object_key, "ContentType": content_type},
        ExpiresIn=expires,
        HttpMethod="PUT",
    )


def object_exists(object_key: str) -> bool:
    client = get_r2_client()
    bucket = _conf("cloudflare_r2_bucket")
    try:
        client.head_object(Bucket=bucket, Key=object_key)
        return True
    except client.exceptions.ClientError:
        return False
    except Exception:
        return False


def public_url(object_key: str) -> str:
    base = frappe.conf.get("cloudflare_r2_public_url", "").rstrip("/")
    return f"{base}/{object_key}"
