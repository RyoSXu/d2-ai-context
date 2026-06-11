from __future__ import annotations

import importlib.metadata
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .ai_context import build_context_pack
from .build_exporter import export_build_data
from .config import (
    CERTS_DIR,
    DATA_DIR,
    MANIFEST_DIR,
    PROFILE_DIR,
    PROJECT_ROOT,
    TOKEN_PATH,
    Settings,
    ensure_dirs,
)
from .item_parser import parse_items
from .manifest_loader import META_PATH, ManifestLoader
from .oauth import CERT_PATH, KEY_PATH, ensure_localhost_cert, get_valid_token
from .profile_loader import load_profile
from .utils import read_json


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""


REQUIRED_PACKAGES = ["requests", "python-dotenv", "pandas", "rich", "PyYAML", "cryptography"]


def run_setup(settings: Settings) -> list[Check]:
    ensure_dirs()
    checks: list[Check] = []
    checks.append(_check_python())
    _ensure_env_example()
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        shutil.copyfile(PROJECT_ROOT / ".env.example", env_path)
        checks.append(Check(".env", False, "已从 .env.example 创建 .env", "请填写 Bungie API key/client id/client secret 后再运行 sync。"))
    else:
        checks.append(Check(".env", True, ".env 已存在"))
    cert_path, key_path = ensure_localhost_cert()
    checks.append(Check("Local HTTPS cert", Path(cert_path).exists() and Path(key_path).exists(), f"{cert_path}"))
    checks.extend(_config_checks(settings))
    checks.extend(_dependency_checks())
    return checks


def run_sync(settings: Settings) -> dict[str, object]:
    result: dict[str, object] = {}
    result["manifest"] = ManifestLoader(settings).update()
    token = get_valid_token(settings)
    result["token_expires_at"] = token.get("expires_at")
    result["profile"] = load_profile(settings).get("fetched_at")
    parsed = parse_items(ManifestLoader(settings))
    result["parsed_items"] = len(parsed.get("items", []))
    result["build_export"] = export_build_data(settings).get("output_dir")
    result["context_pack"] = str(build_context_pack(settings))
    return result


def run_doctor(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    checks.append(_check_python())
    checks.extend(_dependency_checks())
    checks.extend(_config_checks(settings))
    checks.append(_path_check("Data dir", DATA_DIR, "运行 python main.py setup"))
    checks.append(_path_check("Manifest meta", META_PATH, "运行 python main.py manifest"))
    manifest_meta = read_json(META_PATH, default={}) or {}
    db_path_raw = manifest_meta.get("db_path")
    db_path = Path(db_path_raw) if db_path_raw else None
    checks.append(_path_check("Manifest SQLite", db_path, "运行 python main.py manifest"))
    checks.append(_path_check("OAuth token", TOKEN_PATH, "运行 python main.py login"))
    checks.append(_path_check("Profile raw", PROFILE_DIR / "raw_profile.json", "运行 python main.py profile"))
    checks.append(_path_check("Weapons CSV", PROFILE_DIR / "weapons.csv", "运行 python main.py parse"))
    checks.append(_path_check("Armor CSV", PROFILE_DIR / "armor.csv", "运行 python main.py parse"))
    checks.append(_path_check("Exotics CSV", PROFILE_DIR / "exotics.csv", "运行 python main.py parse"))
    checks.append(_path_check("Build export summary", _latest_build_export_summary(), "运行 python main.py export-build-data"))
    checks.append(_path_check("AI context pack", DATA_DIR / "context" / "ai_context_pack.md", "运行 python main.py context-pack"))
    checks.append(_path_check("Local HTTPS cert", CERT_PATH, "运行 python main.py setup"))
    checks.append(_path_check("Local HTTPS key", KEY_PATH, "运行 python main.py setup"))
    return checks


def print_checks(checks: list[Check]) -> None:
    for check in checks:
        status = "OK" if check.ok else "WARN"
        line = f"[{status}] {check.name}: {check.detail}"
        if check.hint and not check.ok:
            line += f" | {check.hint}"
        print(line)
    failed = [check for check in checks if not check.ok]
    print(f"\nSummary: {len(checks) - len(failed)}/{len(checks)} checks OK")


def print_sync_result(result: dict[str, object]) -> None:
    manifest = result.get("manifest")
    if isinstance(manifest, dict):
        print(f"Manifest: version={manifest.get('version')} locale={manifest.get('locale')}")
    print(f"Token expires_at: {result.get('token_expires_at')}")
    print(f"Profile fetched_at: {result.get('profile')}")
    print(f"Parsed items: {result.get('parsed_items')}")
    print(f"Build export: {result.get('build_export')}")
    print(f"AI context pack: {result.get('context_pack')}")


def _check_python() -> Check:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 11)
    return Check("Python", ok, version, "请使用 Python 3.11 或更高版本。")


def _dependency_checks() -> list[Check]:
    checks: list[Check] = []
    for package in REQUIRED_PACKAGES:
        try:
            version = importlib.metadata.version(package)
            checks.append(Check(f"Package {package}", True, version))
        except importlib.metadata.PackageNotFoundError:
            checks.append(Check(f"Package {package}", False, "未安装", "运行 pip install -r requirements.txt"))
    return checks


def _config_checks(settings: Settings) -> list[Check]:
    parsed = urlparse(settings.redirect_uri)
    checks = [
        Check("BUNGIE_API_KEY", bool(settings.api_key), "已配置" if settings.api_key else "缺失", "编辑 .env"),
        Check("BUNGIE_CLIENT_ID", bool(settings.client_id), "已配置" if settings.client_id else "缺失", "编辑 .env"),
        Check("BUNGIE_CLIENT_SECRET", bool(settings.client_secret), "已配置" if settings.client_secret else "缺失", "编辑 .env"),
        Check("BUNGIE_LOCALE", bool(settings.locale), settings.locale or "缺失", "推荐 zh-chs"),
        Check(
            "Redirect URL",
            settings.redirect_uri == "https://localhost:8765/callback",
            settings.redirect_uri,
            "Bungie Application 和 .env 都应填写 https://localhost:8765/callback",
        ),
        Check("Redirect scheme", parsed.scheme == "https", parsed.scheme or "缺失", "Bungie 当前要求 https。"),
        Check("Redirect host", parsed.hostname == "localhost", parsed.hostname or "缺失", "推荐 localhost。"),
        Check("Redirect port", parsed.port == 8765, str(parsed.port or ""), "推荐 8765。"),
    ]
    return checks


def _path_check(name: str, path: Path | None, hint: str) -> Check:
    exists = path is not None and path.exists()
    detail = str(path) if exists and path is not None else "缺失"
    return Check(name, exists, detail, hint)


def _latest_export_summary() -> Path:
    exports_dir = DATA_DIR / "exports"
    if not exports_dir.exists():
        return exports_dir / "missing"
    candidates = sorted(exports_dir.glob("manifest_*/manifest_export_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else exports_dir / "missing"


def _latest_build_export_summary() -> Path:
    exports_dir = DATA_DIR / "build_exports"
    if not exports_dir.exists():
        return exports_dir / "missing"
    candidates = sorted(exports_dir.glob("build_*/build_export_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else exports_dir / "missing"


def _ensure_env_example() -> None:
    example = PROJECT_ROOT / ".env.example"
    if not example.exists():
        example.write_text(
            "\n".join(
                [
                    "BUNGIE_API_KEY=",
                    "BUNGIE_CLIENT_ID=",
                    "BUNGIE_CLIENT_SECRET=",
                    "BUNGIE_REDIRECT_URI=https://localhost:8765/callback",
                    "BUNGIE_LOCALE=zh-chs",
                    "",
                ]
            ),
            encoding="utf-8",
        )
