"""OIDC Authorization Code + PKCE flow, session management, and decorators."""

import os
import hashlib
import base64
import secrets
import urllib.parse
import logging
from functools import wraps

import requests
import jwt
from jwt import PyJWK
from flask import Blueprint, session, redirect, request, abort, jsonify, url_for

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# ---------------------------------------------------------------------------
# OIDC discovery and JWKS — fetched once per worker process, then cached.
# Both use `requests` so the same User-Agent and SSL stack are used for all
# outbound calls, avoiding the 403s that urllib (used by PyJWKClient) triggers
# on some IdPs (Authentik, Cloudflare-protected endpoints, …).
# ---------------------------------------------------------------------------

_oidc_config: dict | None = None
_jwks_keys: list | None = None       # raw list of JWK dicts


def _discover() -> dict:
    """Return the cached OIDC discovery document, fetching it if needed."""
    global _oidc_config
    if _oidc_config is None:
        url = os.environ.get("OIDC_DISCOVERY_URL", "")
        if not url:
            raise RuntimeError("OIDC_DISCOVERY_URL is not configured")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        _oidc_config = resp.json()
        logger.info("OIDC discovery loaded from %s (issuer: %s)", url, _oidc_config.get("issuer"))
    return _oidc_config


def _get_signing_key(id_token: str):
    """Return the signing key for *id_token*, fetching JWKS via requests if needed."""
    global _jwks_keys
    if _jwks_keys is None:
        resp = requests.get(_discover()["jwks_uri"], timeout=10)
        resp.raise_for_status()
        _jwks_keys = resp.json().get("keys", [])

    kid = jwt.get_unverified_header(id_token).get("kid")
    for key_data in _jwks_keys:
        if not kid or key_data.get("kid") == kid:
            return PyJWK(key_data).key

    raise ValueError(f"No matching signing key found (kid={kid!r})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _build_auth_url(state: str, challenge: str, prompt: str) -> str:
    params = {
        "response_type": "code",
        "client_id": _cfg("OIDC_CLIENT_ID"),
        "redirect_uri": url_for("auth.callback", _external=True),
        "scope": "openid profile email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": prompt,
    }
    return _discover()["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)


def _exchange_code(code: str, verifier: str) -> dict:
    resp = requests.post(
        _discover()["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": url_for("auth.callback", _external=True),
            "client_id": _cfg("OIDC_CLIENT_ID"),
            "client_secret": _cfg("OIDC_CLIENT_SECRET"),
            "code_verifier": verifier,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _validate_id_token(id_token: str) -> dict:
    oidc = _discover()
    signing_key = _get_signing_key(id_token)
    claims = jwt.decode(
        id_token,
        signing_key,
        algorithms=["RS256", "ES256"],
        audience=_cfg("OIDC_CLIENT_ID"),
        issuer=oidc["issuer"],
        options={"require": ["exp", "iat", "sub"]},
    )
    return claims


def _check_group(claims: dict) -> bool:
    required = _cfg("OIDC_REQUIRED_GROUP")
    if not required:
        return True
    return required in claims.get("groups", [])


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def require_session(f):
    """Protect a route: redirect to login or return 401 for API calls."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            if request.path.startswith("/api/"):
                abort(401)
            return redirect("/auth/login")
        return f(*args, **kwargs)
    return decorated


def require_csrf(f):
    """Validate X-CSRF-Token header for state-mutating requests."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(token, expected):
            abort(403, "CSRF token missing or invalid")
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth_bp.route("/auth/login")
def login():
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    session["oidc_state"] = state
    session["oidc_code_verifier"] = verifier
    # First attempt: silent login (avoids login page flash if already authed)
    return redirect(_build_auth_url(state, challenge, prompt="none"))


@auth_bp.route("/auth/callback")
def callback():
    error = request.args.get("error")

    # Silent login failed → retry interactively
    if error in ("login_required", "interaction_required", "consent_required"):
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(16)
        session["oidc_state"] = state
        session["oidc_code_verifier"] = verifier
        return redirect(_build_auth_url(state, challenge, prompt="login"))

    if error:
        logger.warning("OIDC error: %s — %s", error, request.args.get("error_description"))
        abort(401, f"Authentication failed: {error}")

    returned_state = request.args.get("state", "")
    stored_state = session.pop("oidc_state", None)
    if not stored_state or not secrets.compare_digest(returned_state, stored_state):
        abort(400, "OAuth state mismatch")

    code = request.args.get("code")
    verifier = session.pop("oidc_code_verifier", None)
    if not code or not verifier:
        abort(400, "Missing authorization code or PKCE verifier")

    try:
        tokens = _exchange_code(code, verifier)
        claims = _validate_id_token(tokens["id_token"])
    except Exception as exc:
        logger.error("Token exchange/validation failed: %s", exc)
        abort(401, "Token validation failed")

    if not _check_group(claims):
        abort(403, "Access denied: required group membership missing")

    session.clear()
    session.permanent = True
    session["user"] = {
        "email": claims.get("email") or claims.get("preferred_username", "unknown"),
        "name": claims.get("name", ""),
    }
    session["csrf_token"] = secrets.token_urlsafe(32)

    return redirect("/")


@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/auth/login")


@auth_bp.route("/api/csrf")
@require_session
def csrf_token():
    return jsonify({"csrf_token": session["csrf_token"]})


@auth_bp.route("/api/me")
@require_session
def me():
    return jsonify(session["user"])
