from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifest"
PROFILE_DIR = DATA_DIR / "profile"
CERTS_DIR = DATA_DIR / "certs"
TOKEN_PATH = DATA_DIR / "token.json"


@dataclass(frozen=True)
class Settings:
    api_key: str
    client_id: str
    client_secret: str
    redirect_uri: str
    locale: str
    api_root: str = "https://www.bungie.net/Platform"
    bungie_root: str = "https://www.bungie.net"

    @property
    def redirect_host(self) -> str:
        return urlparse(self.redirect_uri).hostname or "localhost"

    @property
    def redirect_port(self) -> int:
        return urlparse(self.redirect_uri).port or 8765

    @property
    def redirect_path(self) -> str:
        return urlparse(self.redirect_uri).path or "/callback"


def ensure_dirs() -> None:
    for path in [DATA_DIR, MANIFEST_DIR, PROFILE_DIR, CERTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    ensure_dirs()
    return Settings(
        api_key=os.getenv("BUNGIE_API_KEY", "").strip(),
        client_id=os.getenv("BUNGIE_CLIENT_ID", "").strip(),
        client_secret=os.getenv("BUNGIE_CLIENT_SECRET", "").strip(),
        redirect_uri=os.getenv("BUNGIE_REDIRECT_URI", "https://localhost:8765/callback").strip(),
        locale=os.getenv("BUNGIE_LOCALE", "zh-chs").strip() or "zh-chs",
    )


def require_api_key(settings: Settings) -> None:
    if not settings.api_key:
        raise RuntimeError("BUNGIE_API_KEY 缺失，请在 .env 中填写 Bungie API key。")


def require_oauth_settings(settings: Settings) -> None:
    require_api_key(settings)
    missing = [name for name, value in {
        "BUNGIE_CLIENT_ID": settings.client_id,
        "BUNGIE_CLIENT_SECRET": settings.client_secret,
        "BUNGIE_REDIRECT_URI": settings.redirect_uri,
    }.items() if not value]
    if missing:
        raise RuntimeError(f"OAuth 配置缺失：{', '.join(missing)}。请检查 .env。")
