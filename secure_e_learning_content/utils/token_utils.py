# -*- coding: utf-8 -*-
"""
Slide Shield – HMAC-SHA256 Token Service
=========================================
Generates and verifies short-lived, tamper-proof URL tokens used for
protected video streaming.  Each token is bound to a specific user,
slide, and browser session so that shared URLs are useless.

Token format:  ``<base64url-payload>.<base64url-signature>``
Payload JSON:  ``{"uid": int, "sid": int, "sh": str, "exp": int, "res": "video"}``
"""
import base64
import hashlib
import hmac
import json
import secrets
import time


def _b64url_encode(data):
    """Base64-URL encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value):
    """Base64-URL decode with re-added padding."""
    padding = 4 - len(value) % 4
    if padding != 4:
        value += "=" * padding
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _get_secret(env):
    """Return the token signing secret, auto-generating one if absent."""
    icp = env["ir.config_parameter"].sudo()
    secret = icp.get_param("slide_shield.token_secret")
    if not secret:
        secret = secrets.token_urlsafe(48)
        icp.set_param("slide_shield.token_secret", secret)
    return secret.encode("utf-8")


def _get_ttl(env):
    """Return the configured token TTL in seconds (minimum 30)."""
    raw = env["ir.config_parameter"].sudo().get_param(
        "slide_shield.token_ttl_seconds", "300"
    )
    return max(30, int(raw or 300))


def hash_value(env, value, purpose):
    """
    Create a keyed HMAC-SHA256 hash of *value* for a given *purpose*.
    Used for session hashes, device fingerprints, etc.
    """
    payload = ("%s:%s" % (purpose, value or "")).encode("utf-8")
    return hmac.new(_get_secret(env), payload, hashlib.sha256).hexdigest()


def get_session_hash(env, request):
    """Hash the current Odoo browser session ID."""
    return hash_value(env, request.session.sid or "", "session")


def generate_video_token(env, user_id, slide_id, session_hash, ttl=None):
    """
    Generate a signed video-access token.

    :param env:          Odoo environment
    :param user_id:      res.users ID
    :param slide_id:     slide.slide ID
    :param session_hash: HMAC of the browser session
    :param ttl:          Override token lifetime (seconds)
    :returns:            Token string ``payload_b64.signature_b64``
    """
    payload = {
        "uid": int(user_id),
        "sid": int(slide_id),
        "sh": session_hash,
        "exp": int(time.time()) + int(ttl or _get_ttl(env)),
        "res": "video",
    }
    payload_json = json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    signature = hmac.new(
        _get_secret(env), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    return "%s.%s" % (payload_b64, _b64url_encode(signature))


def verify_video_token(env, token, slide_id=None):
    """
    Verify a video-access token.

    :param env:      Odoo environment
    :param token:    The token string
    :param slide_id: Expected slide ID (optional extra check)
    :returns:        Parsed payload dict
    :raises ValueError: On any validation failure
    """
    if not token or not isinstance(token, str):
        raise ValueError("Missing token.")

    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("Malformed token.")

    payload_b64, signature_b64 = parts

    # Verify signature
    expected = hmac.new(
        _get_secret(env), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_b64url_encode(expected), signature_b64):
        raise ValueError("Invalid token signature.")

    # Decode payload
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid token payload: %s" % exc) from exc

    # Validate required fields
    for key in ("uid", "sid", "sh", "exp", "res"):
        if key not in payload:
            raise ValueError("Token missing field: %s" % key)

    # Check expiry
    if int(time.time()) > int(payload["exp"]):
        raise ValueError("Token has expired.")

    # Check resource type
    if payload["res"] != "video":
        raise ValueError("Token resource mismatch.")

    # Optional: check slide ID
    if slide_id is not None and int(payload["sid"]) != int(slide_id):
        raise ValueError("Token slide ID mismatch.")

    return payload
