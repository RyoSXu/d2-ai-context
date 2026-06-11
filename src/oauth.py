from __future__ import annotations

import base64
import json
import ssl
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import requests

from .config import CERTS_DIR, TOKEN_PATH, Settings, require_oauth_settings
from .utils import read_json, write_json


AUTH_URL = "https://www.bungie.net/en/OAuth/Authorize"
TOKEN_URL = "https://www.bungie.net/Platform/App/OAuth/Token/"
CERT_PATH = CERTS_DIR / "localhost.crt"
KEY_PATH = CERTS_DIR / "localhost.key"


def _basic_auth(settings: Settings) -> str:
    raw = f"{settings.client_id}:{settings.client_secret}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _save_token(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["expires_at"] = int(time.time()) + int(payload.get("expires_in", 3600)) - 60
    if "refresh_expires_in" in payload:
        payload["refresh_expires_at"] = int(time.time()) + int(payload.get("refresh_expires_in", 0)) - 60
    write_json(TOKEN_PATH, payload)
    return payload


def exchange_code(settings: Settings, code: str) -> dict[str, Any]:
    headers = {"Authorization": f"Basic {_basic_auth(settings)}"}
    data = {"grant_type": "authorization_code", "code": code}
    response = requests.post(TOKEN_URL, headers=headers, data=data, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"OAuth token 交换失败，HTTP {response.status_code}: {response.text[:500]}")
    return _save_token(response.json())


def refresh_token(settings: Settings, token: dict[str, Any]) -> dict[str, Any]:
    refresh = token.get("refresh_token")
    if not refresh:
        raise RuntimeError("token 中没有 refresh_token。")
    headers = {"Authorization": f"Basic {_basic_auth(settings)}"}
    data = {"grant_type": "refresh_token", "refresh_token": refresh}
    response = requests.post(TOKEN_URL, headers=headers, data=data, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"OAuth refresh 失败，HTTP {response.status_code}: {response.text[:500]}")
    return _save_token(response.json())


def login(settings: Settings) -> dict[str, Any]:
    require_oauth_settings(settings)
    done = Event()
    result: dict[str, str] = {}
    expected_path = settings.redirect_path

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return
            query = parse_qs(parsed.query)
            if "code" in query:
                result["code"] = query["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write("OAuth complete. You can close this tab.".encode("utf-8"))
            else:
                result["error"] = json.dumps(query)
                self.send_response(400)
                self.end_headers()
                self.wfile.write("OAuth failed. Return to the terminal.".encode("utf-8"))
            done.set()

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer((settings.redirect_host, settings.redirect_port), CallbackHandler)
    if urlparse(settings.redirect_uri).scheme == "https":
        cert_path, key_path = ensure_localhost_cert()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    params = {"client_id": settings.client_id, "response_type": "code", "redirect_uri": settings.redirect_uri}
    webbrowser.open(f"{AUTH_URL}?{urlencode(params)}")
    while not done.is_set():
        server.handle_request()
    server.server_close()
    if "code" not in result:
        raise RuntimeError(f"OAuth 登录失败：{result.get('error', '未收到 authorization code')}")
    return exchange_code(settings, result["code"])


def ensure_localhost_cert() -> tuple[str, str]:
    if CERT_PATH.exists() and KEY_PATH.exists():
        return str(CERT_PATH), str(KEY_PATH)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "d2-ai-context local dev"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(CERT_PATH), str(KEY_PATH)


def get_valid_token(settings: Settings, *, force_login: bool = False) -> dict[str, Any]:
    token = read_json(TOKEN_PATH, default=None)
    if force_login or not token:
        return login(settings)
    if int(token.get("expires_at", 0)) > int(time.time()):
        return token
    try:
        return refresh_token(settings, token)
    except Exception:
        return login(settings)
