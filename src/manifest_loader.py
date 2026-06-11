from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import requests

from .bungie_client import BungieClient
from .config import MANIFEST_DIR, Settings
from .utils import read_json, signed_hash, write_json


META_PATH = MANIFEST_DIR / "manifest_meta.json"


class ManifestLoader:
    TABLES = [
        "DestinyInventoryItemDefinition",
        "DestinySandboxPerkDefinition",
        "DestinyPlugSetDefinition",
        "DestinyStatDefinition",
        "DestinyInventoryBucketDefinition",
        "DestinySocketCategoryDefinition",
        "DestinySocketTypeDefinition",
        "DestinyClassDefinition",
        "DestinyDamageTypeDefinition",
        "DestinyCollectibleDefinition",
        "DestinyPresentationNodeDefinition",
        "DestinyRecordDefinition",
        "DestinyVendorDefinition",
        "DestinyActivityDefinition",
    ]

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = BungieClient(settings)
        self.db_path = self._current_db_path()

    def update(self) -> dict[str, Any]:
        manifest = self.client.get_response("/Destiny2/Manifest/")
        version = manifest.get("version")
        meta = read_json(META_PATH, default={}) or {}
        if meta.get("version") == version and meta.get("db_path") and Path(meta["db_path"]).exists():
            self.db_path = Path(meta["db_path"])
            return meta

        paths = manifest.get("mobileWorldContentPaths", {})
        locale = self.settings.locale
        chosen_locale = locale if locale in paths else "en"
        zip_path = paths.get(chosen_locale) or paths.get("en")
        if not zip_path:
            raise RuntimeError("Manifest 响应中没有可下载的 mobileWorldContentPaths。")
        try:
            db_path = self._download_and_extract(zip_path, chosen_locale, version)
        except Exception:
            if chosen_locale == "en":
                raise
            db_path = self._download_and_extract(paths["en"], "en", version)
            chosen_locale = "en"

        meta = {"version": version, "locale": chosen_locale, "db_path": str(db_path), "downloaded_from": zip_path}
        write_json(META_PATH, meta)
        self.db_path = db_path
        return meta

    def _download_and_extract(self, path: str, locale: str, version: str) -> Path:
        url = f"{self.settings.bungie_root}{path}"
        zip_file = MANIFEST_DIR / f"manifest_{locale}_{version}.zip"
        response = requests.get(url, timeout=180)
        if response.status_code >= 400:
            raise RuntimeError(f"Manifest 下载失败，HTTP {response.status_code}: {response.text[:300]}")
        zip_file.write_bytes(response.content)
        with zipfile.ZipFile(zip_file) as zf:
            sqlite_members = [name for name in zf.namelist() if name.endswith((".content", ".sqlite"))]
            if not sqlite_members:
                raise RuntimeError("Manifest zip 中没有 SQLite/content 文件。")
            member = sqlite_members[0]
            extracted = zf.extract(member, MANIFEST_DIR)
        target = MANIFEST_DIR / f"manifest_{locale}_{version}.sqlite"
        Path(extracted).replace(target)
        return target

    def _current_db_path(self) -> Path | None:
        meta = read_json(META_PATH, default={}) or {}
        path = meta.get("db_path")
        if path and Path(path).exists():
            return Path(path)

        version = meta.get("version")
        locale = meta.get("locale")
        candidates: list[Path] = []
        if version and locale:
            candidates.extend(MANIFEST_DIR.glob(f"manifest_{locale}_{version}.sqlite"))
        candidates.extend(sorted(MANIFEST_DIR.glob("manifest_*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True))
        if not candidates:
            return None

        db_path = candidates[0]
        if meta:
            meta["db_path"] = str(db_path)
            write_json(META_PATH, meta)
        return db_path

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path or not self.db_path.exists():
            raise RuntimeError("Manifest SQLite 不存在，请先运行 python main.py manifest。")
        return sqlite3.connect(self.db_path)

    def get_definition(self, table_name: str, hash_value: int | str | None) -> dict[str, Any] | None:
        if hash_value is None:
            return None
        with self._connect() as conn:
            for candidate in [int(hash_value), signed_hash(hash_value)]:
                row = conn.execute(f'SELECT json FROM "{table_name}" WHERE id = ?', (candidate,)).fetchone()
                if row:
                    return json.loads(row[0])
        return None

    def search_inventory_items(self, keyword: str, limit: int = 50) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        key = keyword.lower()
        with self._connect() as conn:
            rows = conn.execute('SELECT json FROM "DestinyInventoryItemDefinition"').fetchall()
        for (raw,) in rows:
            item = json.loads(raw)
            name = item.get("displayProperties", {}).get("name", "")
            if key in name.lower():
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    def get_inventory_item(self, item_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinyInventoryItemDefinition", item_hash)

    def get_stat(self, stat_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinyStatDefinition", stat_hash)

    def get_bucket(self, bucket_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinyInventoryBucketDefinition", bucket_hash)

    def get_class(self, class_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinyClassDefinition", class_hash)

    def get_damage_type(self, damage_type_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinyDamageTypeDefinition", damage_type_hash)

    def get_collectible(self, collectible_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinyCollectibleDefinition", collectible_hash)

    def get_plug_set(self, plug_set_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinyPlugSetDefinition", plug_set_hash)

    def get_socket_type(self, socket_type_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinySocketTypeDefinition", socket_type_hash)

    def get_socket_category(self, socket_category_hash: int | str | None) -> dict[str, Any] | None:
        return self.get_definition("DestinySocketCategoryDefinition", socket_category_hash)
