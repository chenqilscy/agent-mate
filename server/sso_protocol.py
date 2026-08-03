"""Provider-specific OAuth/OIDC protocol handling for the Server SSO broker."""
from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from config import settings


def callback_uri(provider: str) -> str:
    return f"{settings.SSO_PUBLIC_BASE_URL}/api/auth/sso/{provider}/callback"


def authorization_url(provider: str, config: dict[str, Any], attempt: dict, state: str) -> str:
    redirect = callback_uri(provider)
    if provider == "wechat":
        query = urlencode({
            "appid": config["client_id"], "redirect_uri": redirect,
            "response_type": "code", "scope": "snsapi_login", "state": state,
        })
        return f"https://open.weixin.qq.com/connect/qrconnect?{query}#wechat_redirect"
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(attempt["code_verifier"].encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    if provider == "google":
        endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        scope = "openid email profile"
    elif provider == "telegram":
        endpoint = "https://oauth.telegram.org/auth"
        scope = "openid profile"
    else:
        raise ValueError("unsupported_provider")
    return endpoint + "?" + urlencode({
        "client_id": config["client_id"], "redirect_uri": redirect,
        "response_type": "code", "scope": scope, "state": state,
        "nonce": attempt["nonce"], "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def _verify_oidc(provider: str, id_token: str, config: dict, nonce: str) -> dict[str, Any]:
    if provider == "google":
        jwks_uri = "https://www.googleapis.com/oauth2/v3/certs"
        issuer = "https://accounts.google.com"
        algorithms = ["RS256"]
    else:
        jwks_uri = "https://oauth.telegram.org/.well-known/jwks.json"
        issuer = "https://oauth.telegram.org"
        algorithms = ["RS256", "ES256"]
    key = jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token, key=key, algorithms=algorithms,
        audience=str(config["client_id"]), issuer=issuer,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
    )
    if str(claims.get("nonce") or "") != nonce:
        raise ValueError("invalid_nonce")
    if provider == "google" and claims.get("email") and claims.get("email_verified") is not True:
        raise ValueError("email_not_verified")
    return {
        "subject": str(claims["sub"]), "email": str(claims.get("email") or ""),
        "name": str(claims.get("name") or claims.get("preferred_username") or ""),
    }


def exchange_identity(provider: str, config: dict, attempt: dict, code: str) -> dict[str, Any]:
    redirect = callback_uri(provider)
    if provider == "wechat":
        token_response = httpx.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": config["client_id"], "secret": config["client_secret"],
                "code": code, "grant_type": "authorization_code",
            }, timeout=10.0,
        )
        token_response.raise_for_status()
        token = token_response.json()
        if token.get("errcode") or not token.get("access_token") or not token.get("openid"):
            raise ValueError("provider_token_rejected")
        profile_response = httpx.get(
            "https://api.weixin.qq.com/sns/userinfo",
            params={
                "access_token": token["access_token"], "openid": token["openid"],
                "lang": "zh_CN",
            }, timeout=10.0,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
        if profile.get("errcode"):
            raise ValueError("provider_profile_rejected")
        subject = str(profile.get("unionid") or f"{config['client_id']}:{token['openid']}")
        return {"subject": subject, "email": "", "name": str(profile.get("nickname") or "微信用户")}

    token_url = (
        "https://oauth2.googleapis.com/token"
        if provider == "google" else "https://oauth.telegram.org/token"
    )
    data = {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": redirect, "client_id": config["client_id"],
        "code_verifier": attempt["code_verifier"],
    }
    headers: dict[str, str] = {}
    if provider == "google":
        data["client_secret"] = config["client_secret"]
    else:
        basic = base64.b64encode(
            f"{config['client_id']}:{config['client_secret']}".encode("utf-8")
        ).decode("ascii")
        headers["Authorization"] = f"Basic {basic}"
    response = httpx.post(token_url, data=data, headers=headers, timeout=10.0)
    response.raise_for_status()
    body = response.json()
    id_token = str(body.get("id_token") or "")
    if not id_token:
        raise ValueError("missing_id_token")
    return _verify_oidc(provider, id_token, config, str(attempt["nonce"]))
