from __future__ import annotations

import csv
import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import DATA_DIR, Settings
from .manifest_loader import ManifestLoader
from .utils import read_json


EXPORT_DIR = DATA_DIR / "exports"


def export_manifest_data(settings: Settings) -> dict[str, Any]:
    loader = ManifestLoader(settings)
    if not loader.db_path or not loader.db_path.exists():
        loader.update()
    if not loader.db_path or not loader.db_path.exists():
        raise RuntimeError("Manifest SQLite 不存在，无法导出。")

    meta = read_json(DATA_DIR / "manifest" / "manifest_meta.json", default={}) or {}
    version_slug = str(meta.get("version", "unknown")).replace("/", "_").replace("\\", "_")
    out_dir = EXPORT_DIR / f"manifest_{meta.get('locale', 'unknown')}_{version_slug}"
    tables_dir = out_dir / "tables_jsonl_gz"
    indexes_dir = out_dir / "indexes"
    tables_dir.mkdir(parents=True, exist_ok=True)
    indexes_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "manifest_version": meta.get("version"),
        "manifest_locale": meta.get("locale"),
        "source_db": str(loader.db_path),
        "output_dir": str(out_dir),
        "tables": {},
    }

    with sqlite3.connect(loader.db_path) as conn:
        table_names = [
            row[0]
            for row in conn.execute("select name from sqlite_master where type='table' order by name").fetchall()
        ]
        for table in table_names:
            count = _export_table(conn, table, tables_dir / f"{table}.jsonl.gz")
            summary["tables"][table] = {"rows": count, "file": f"tables_jsonl_gz/{table}.jsonl.gz"}

        _export_inventory_item_index(conn, indexes_dir / "inventory_items_index.csv")
        _export_perk_index(conn, indexes_dir / "sandbox_perks_index.csv")
        _export_collectible_index(conn, indexes_dir / "collectibles_index.csv")

    summary["index_files"] = {
        "inventory_items": "indexes/inventory_items_index.csv",
        "sandbox_perks": "indexes/sandbox_perks_index.csv",
        "collectibles": "indexes/collectibles_index.csv",
    }
    (out_dir / "manifest_export_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def _export_table(conn: sqlite3.Connection, table: str, output_path: Path) -> int:
    count = 0
    columns = [row[1] for row in conn.execute(f'pragma table_info("{table}")').fetchall()]
    key_expr = "id" if "id" in columns else "rowid"
    json_column = "json" if "json" in columns else columns[-1]
    with gzip.open(output_path, "wt", encoding="utf-8") as handle:
        for row_id, raw_json in conn.execute(f'select {key_expr}, "{json_column}" from "{table}" order by {key_expr}'):
            data = json.loads(raw_json)
            handle.write(json.dumps({"id": row_id, "data": data}, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def _display_name(data: dict[str, Any]) -> str:
    return data.get("displayProperties", {}).get("name", "")


def _description(data: dict[str, Any]) -> str:
    return data.get("displayProperties", {}).get("description", "")


def _export_inventory_item_index(conn: sqlite3.Connection, output_path: Path) -> None:
    fields = [
        "hash",
        "name",
        "description",
        "itemTypeDisplayName",
        "itemTypeAndTierDisplayName",
        "classType",
        "tierType",
        "tierTypeName",
        "bucketTypeHash",
        "defaultDamageTypeHash",
        "collectibleHash",
        "icon",
        "screenshot",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (raw_json,) in conn.execute('select json from "DestinyInventoryItemDefinition"'):
            data = json.loads(raw_json)
            inventory = data.get("inventory", {})
            writer.writerow(
                {
                    "hash": data.get("hash"),
                    "name": _display_name(data),
                    "description": _description(data),
                    "itemTypeDisplayName": data.get("itemTypeDisplayName", ""),
                    "itemTypeAndTierDisplayName": data.get("itemTypeAndTierDisplayName", ""),
                    "classType": data.get("classType", ""),
                    "tierType": inventory.get("tierType", ""),
                    "tierTypeName": inventory.get("tierTypeName", ""),
                    "bucketTypeHash": inventory.get("bucketTypeHash", ""),
                    "defaultDamageTypeHash": data.get("defaultDamageTypeHash", ""),
                    "collectibleHash": data.get("collectibleHash", ""),
                    "icon": data.get("displayProperties", {}).get("icon", ""),
                    "screenshot": data.get("screenshot", ""),
                }
            )


def _export_perk_index(conn: sqlite3.Connection, output_path: Path) -> None:
    fields = ["hash", "name", "description", "icon", "isDisplayable"]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (raw_json,) in conn.execute('select json from "DestinySandboxPerkDefinition"'):
            data = json.loads(raw_json)
            writer.writerow(
                {
                    "hash": data.get("hash"),
                    "name": _display_name(data),
                    "description": _description(data),
                    "icon": data.get("displayProperties", {}).get("icon", ""),
                    "isDisplayable": data.get("isDisplayable", ""),
                }
            )


def _export_collectible_index(conn: sqlite3.Connection, output_path: Path) -> None:
    fields = ["hash", "name", "description", "itemHash", "sourceString", "icon"]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (raw_json,) in conn.execute('select json from "DestinyCollectibleDefinition"'):
            data = json.loads(raw_json)
            writer.writerow(
                {
                    "hash": data.get("hash"),
                    "name": _display_name(data),
                    "description": _description(data),
                    "itemHash": data.get("itemHash", ""),
                    "sourceString": data.get("sourceString", ""),
                    "icon": data.get("displayProperties", {}).get("icon", ""),
                }
            )
