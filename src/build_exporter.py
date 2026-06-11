from __future__ import annotations

import csv
import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import DATA_DIR, PROFILE_DIR, Settings
from .manifest_loader import ManifestLoader
from .utils import display_name, read_json


BUILD_EXPORT_DIR = DATA_DIR / "build_exports"

ITEM_TYPE_ARMOR = 2
ITEM_TYPE_WEAPON = 3

CATEGORY_WEAPON = 1
CATEGORY_ARMOR = 20
CATEGORY_GHOST = 39
CATEGORY_SUBCLASS = 50
CATEGORY_SUBCLASS_MOD = 1043342778
CATEGORY_ARTIFACT = 1378222069

BUCKET_SUBCLASS = 3284755031
BUCKET_GHOST = 4023194814
BUCKET_ARTIFACT = 1506418338

EXCLUDED_MOD_NAME_PARTS = ("赛雀", "飞船", "入场券", "传送效果", "Sparrow", "Ship", "Transmat", "Ticket")


def export_build_data(settings: Settings) -> dict[str, Any]:
    loader = ManifestLoader(settings)
    if not loader.db_path or not loader.db_path.exists():
        loader.update()
    if not loader.db_path or not loader.db_path.exists():
        raise RuntimeError("Manifest SQLite 不存在，无法导出 build 数据。")

    meta = read_json(DATA_DIR / "manifest" / "manifest_meta.json", default={}) or {}
    version_slug = str(meta.get("version", "unknown")).replace("/", "_").replace("\\", "_")
    out_dir = BUILD_EXPORT_DIR / f"build_{meta.get('locale', 'unknown')}_{version_slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(loader.db_path) as conn:
        categories = _load_table(conn, "DestinyItemCategoryDefinition")
        items = _load_table(conn, "DestinyInventoryItemDefinition")
        plug_sets = _load_table(conn, "DestinyPlugSetDefinition")
        stats = _load_table(conn, "DestinyStatDefinition")

        selected_items = [
            item
            for item in items.values()
            if _is_build_relevant_item(item, categories)
        ]
        selected_hashes = {int(item["hash"]) for item in selected_items if item.get("hash") is not None}

        compact_items, referenced_plug_hashes, referenced_perk_hashes = _compact_items(selected_items, categories, items, plug_sets, stats)
        for plug_hash in sorted(referenced_plug_hashes - selected_hashes):
            plug = items.get(int(plug_hash))
            if not plug:
                continue
            compact, _, perk_hashes = _compact_item(plug, categories, items, plug_sets, stats, include_sockets=False)
            compact["buildRole"] = compact.get("buildRole") or "referenced_plug"
            compact_items.append(compact)
            referenced_perk_hashes.update(perk_hashes)

        sandbox_perks = _compact_perks(conn, referenced_perk_hashes)
        _write_jsonl_gz(out_dir / "build_items.jsonl.gz", compact_items)
        _write_jsonl_gz(out_dir / "sandbox_perks.jsonl.gz", sandbox_perks)
        _write_basic_tables(conn, out_dir)
        _write_item_index(out_dir / "build_items_index.csv", compact_items)

    summary = {
        "manifest_version": meta.get("version"),
        "manifest_locale": meta.get("locale"),
        "source_db": str(loader.db_path),
        "output_dir": str(out_dir),
        "files": {
            "build_items": "build_items.jsonl.gz",
            "build_items_index": "build_items_index.csv",
            "sandbox_perks": "sandbox_perks.jsonl.gz",
            "stats": "stats.json",
            "classes": "classes.json",
            "damage_types": "damage_types.json",
            "socket_categories": "socket_categories.json",
            "socket_types": "socket_types.json",
        },
        "profile_files": _profile_files(),
        "counts": {
            "build_items": len(compact_items),
            "sandbox_perks": len(sandbox_perks),
        },
    }
    (out_dir / "build_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _load_table(conn: sqlite3.Connection, table: str) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row_id, raw in conn.execute(f'select id, json from "{table}"'):
        data = json.loads(raw)
        key = data.get("hash", row_id)
        out[int(key)] = data
    return out


def _is_build_relevant_item(item: dict[str, Any], categories: dict[int, dict[str, Any]]) -> bool:
    item_type = item.get("itemType")
    if item_type in (ITEM_TYPE_WEAPON, ITEM_TYPE_ARMOR):
        return True

    category_hashes = {int(value) for value in item.get("itemCategoryHashes", []) or []}
    bucket_hash = item.get("inventory", {}).get("bucketTypeHash")
    if category_hashes & {CATEGORY_WEAPON, CATEGORY_ARMOR, CATEGORY_GHOST, CATEGORY_SUBCLASS, CATEGORY_ARTIFACT, CATEGORY_SUBCLASS_MOD}:
        return True
    if bucket_hash in {BUCKET_SUBCLASS, BUCKET_GHOST, BUCKET_ARTIFACT}:
        return True

    if not _is_mod_item(item, categories):
        return False
    category_names = [_category_name(categories, value) for value in category_hashes]
    joined = " ".join(category_names)
    if any(part in joined for part in EXCLUDED_MOD_NAME_PARTS):
        return False
    return any(part in joined for part in ("武器模组", "护甲模组", "机灵模组", "分支职业模组", "Weapon Mod", "Armor Mod", "Ghost Mod", "Subclass Mod"))


def _is_mod_item(item: dict[str, Any], categories: dict[int, dict[str, Any]]) -> bool:
    if item.get("itemType") == 19:
        return True
    for category_hash in item.get("itemCategoryHashes", []) or []:
        name = _category_name(categories, int(category_hash))
        if "模组" in name or "Mod" in name:
            return True
    return False


def _compact_items(
    selected_items: list[dict[str, Any]],
    categories: dict[int, dict[str, Any]],
    items: dict[int, dict[str, Any]],
    plug_sets: dict[int, dict[str, Any]],
    stats: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[int], set[int]]:
    compact_items: list[dict[str, Any]] = []
    referenced_plug_hashes: set[int] = set()
    referenced_perk_hashes: set[int] = set()
    for item in selected_items:
        compact, plug_hashes, perk_hashes = _compact_item(item, categories, items, plug_sets, stats, include_sockets=True)
        compact_items.append(compact)
        referenced_plug_hashes.update(plug_hashes)
        referenced_perk_hashes.update(perk_hashes)
    return compact_items, referenced_plug_hashes, referenced_perk_hashes


def _compact_item(
    item: dict[str, Any],
    categories: dict[int, dict[str, Any]],
    items: dict[int, dict[str, Any]],
    plug_sets: dict[int, dict[str, Any]],
    stats: dict[int, dict[str, Any]],
    *,
    include_sockets: bool,
) -> tuple[dict[str, Any], set[int], set[int]]:
    category_hashes = [int(value) for value in item.get("itemCategoryHashes", []) or []]
    bucket_hash = item.get("inventory", {}).get("bucketTypeHash")
    compact = {
        "hash": item.get("hash"),
        "name": display_name(item, str(item.get("hash", ""))),
        "description": item.get("displayProperties", {}).get("description", ""),
        "buildRole": _build_role(item, categories),
        "itemType": item.get("itemType"),
        "itemTypeDisplayName": item.get("itemTypeDisplayName", ""),
        "itemTypeAndTierDisplayName": item.get("itemTypeAndTierDisplayName", ""),
        "classType": item.get("classType"),
        "tierType": item.get("inventory", {}).get("tierType"),
        "tierTypeName": item.get("inventory", {}).get("tierTypeName", ""),
        "bucketTypeHash": bucket_hash,
        "categoryHashes": category_hashes,
        "categoryNames": [_category_name(categories, value) for value in category_hashes],
        "defaultDamageTypeHash": item.get("defaultDamageTypeHash"),
        "collectibleHash": item.get("collectibleHash"),
        "icon": item.get("displayProperties", {}).get("icon", ""),
        "screenshot": item.get("screenshot", ""),
        "stats": _definition_stats(stats, item),
        "perks": _item_perks(item),
    }
    perk_hashes = {int(perk["perkHash"]) for perk in compact["perks"] if perk.get("perkHash") is not None}
    plug_hashes: set[int] = set()
    if include_sockets:
        expand_plugs = compact["buildRole"] in {"weapon", "subclass", "artifact", "ghost"}
        sockets, plug_hashes, socket_perk_hashes = _sockets(items, plug_sets, item, expand_plugs=expand_plugs)
        compact["sockets"] = sockets
        perk_hashes.update(socket_perk_hashes)
    return compact, plug_hashes, perk_hashes


def _build_role(item: dict[str, Any], categories: dict[int, dict[str, Any]]) -> str:
    item_type = item.get("itemType")
    if item_type == ITEM_TYPE_WEAPON:
        return "weapon"
    if item_type == ITEM_TYPE_ARMOR:
        return "armor"
    category_hashes = {int(value) for value in item.get("itemCategoryHashes", []) or []}
    bucket_hash = item.get("inventory", {}).get("bucketTypeHash")
    if CATEGORY_SUBCLASS in category_hashes or bucket_hash == BUCKET_SUBCLASS:
        return "subclass"
    if CATEGORY_ARTIFACT in category_hashes or bucket_hash == BUCKET_ARTIFACT:
        return "artifact"
    if CATEGORY_GHOST in category_hashes or bucket_hash == BUCKET_GHOST:
        return "ghost"
    if _is_mod_item(item, categories):
        return "mod"
    if item.get("plug"):
        return "plug"
    return "other_build_item"


def _category_name(categories: dict[int, dict[str, Any]], category_hash: int) -> str:
    return display_name(categories.get(category_hash), str(category_hash))


def _definition_stats(stats: dict[int, dict[str, Any]], item: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for stat_hash, stat in (item.get("stats", {}).get("stats") or {}).items():
        value = stat.get("value")
        if value in ("", None):
            continue
        stat_def = stats.get(int(stat_hash))
        out[display_name(stat_def, str(stat_hash))] = value
    return out


def _item_perks(item: dict[str, Any]) -> list[dict[str, Any]]:
    perks = []
    for perk in item.get("perks", []) or []:
        perks.append({
            "perkHash": perk.get("perkHash"),
            "requirementDisplayString": perk.get("requirementDisplayString", ""),
        })
    return perks


def _sockets(
    items: dict[int, dict[str, Any]],
    plug_sets: dict[int, dict[str, Any]],
    item: dict[str, Any],
    *,
    expand_plugs: bool,
) -> tuple[list[dict[str, Any]], set[int], set[int]]:
    sockets: list[dict[str, Any]] = []
    plug_hashes: set[int] = set()
    perk_hashes: set[int] = set()
    for index, entry in enumerate(item.get("sockets", {}).get("socketEntries") or []):
        plug_set_hashes = [
            value
            for value in [entry.get("randomizedPlugSetHash"), entry.get("reusablePlugSetHash")]
            if value not in ("", None)
        ]
        socket = {
            "index": index,
            "socketTypeHash": entry.get("socketTypeHash"),
            "singleInitialItemHash": entry.get("singleInitialItemHash"),
            "randomizedPlugSetHash": entry.get("randomizedPlugSetHash"),
            "reusablePlugSetHash": entry.get("reusablePlugSetHash"),
            "plugSetHashes": plug_set_hashes,
        }
        if expand_plugs:
            plugs = []
            for plug_hash in _plug_hashes(plug_sets, entry, plug_set_hashes):
                plug = items.get(int(plug_hash))
                if not plug:
                    continue
                plug_hashes.add(int(plug_hash))
                plug_perks = _item_perks(plug)
                perk_hashes.update(int(perk["perkHash"]) for perk in plug_perks if perk.get("perkHash") is not None)
                plugs.append({
                    "hash": plug.get("hash", plug_hash),
                    "name": display_name(plug, str(plug_hash)),
                    "description": plug.get("displayProperties", {}).get("description", ""),
                    "itemTypeDisplayName": plug.get("itemTypeDisplayName", ""),
                    "plugCategoryIdentifier": plug.get("plug", {}).get("plugCategoryIdentifier", ""),
                    "perks": plug_perks,
                })
            socket["plugs"] = plugs
        sockets.append(socket)
    return sockets, plug_hashes, perk_hashes


def _plug_hashes(plug_sets: dict[int, dict[str, Any]], socket_entry: dict[str, Any], plug_set_hashes: list[Any]) -> list[int]:
    out: list[int] = []
    for plug_set_hash in plug_set_hashes:
        plug_set = plug_sets.get(int(plug_set_hash))
        for plug in (plug_set or {}).get("reusablePlugItems", []) or []:
            plug_hash = plug.get("plugItemHash")
            if plug_hash not in ("", None):
                out.append(int(plug_hash))
    for plug in socket_entry.get("reusablePlugItems", []) or []:
        plug_hash = plug.get("plugItemHash")
        if plug_hash not in ("", None):
            out.append(int(plug_hash))
    if socket_entry.get("singleInitialItemHash") not in ("", None):
        out.append(int(socket_entry["singleInitialItemHash"]))
    seen: set[int] = set()
    deduped: list[int] = []
    for value in out:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _compact_perks(conn: sqlite3.Connection, perk_hashes: set[int]) -> list[dict[str, Any]]:
    if not perk_hashes:
        return []
    placeholders = ",".join("?" for _ in perk_hashes)
    rows = conn.execute(
        f'select json from "DestinySandboxPerkDefinition" where id in ({placeholders}) or json_extract(json, "$.hash") in ({placeholders})',
        [*perk_hashes, *perk_hashes],
    ).fetchall()
    perks = []
    for (raw,) in rows:
        data = json.loads(raw)
        perks.append({
            "hash": data.get("hash"),
            "name": display_name(data, str(data.get("hash", ""))),
            "description": data.get("displayProperties", {}).get("description", ""),
            "isDisplayable": data.get("isDisplayable"),
            "icon": data.get("displayProperties", {}).get("icon", ""),
        })
    return perks


def _write_basic_tables(conn: sqlite3.Connection, out_dir: Path) -> None:
    tables = {
        "DestinyStatDefinition": "stats.json",
        "DestinyClassDefinition": "classes.json",
        "DestinyDamageTypeDefinition": "damage_types.json",
        "DestinySocketCategoryDefinition": "socket_categories.json",
        "DestinySocketTypeDefinition": "socket_types.json",
    }
    for table, filename in tables.items():
        rows = []
        for (raw,) in conn.execute(f'select json from "{table}"'):
            data = json.loads(raw)
            rows.append({
                "hash": data.get("hash"),
                "name": display_name(data, str(data.get("hash", ""))),
                "description": data.get("displayProperties", {}).get("description", ""),
                "raw": data,
            })
        (out_dir / filename).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def _write_item_index(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["hash", "name", "buildRole", "itemTypeDisplayName", "itemTypeAndTierDisplayName", "tierTypeName", "bucketTypeHash", "categoryNames"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "hash": row.get("hash"),
                "name": row.get("name", ""),
                "buildRole": row.get("buildRole", ""),
                "itemTypeDisplayName": row.get("itemTypeDisplayName", ""),
                "itemTypeAndTierDisplayName": row.get("itemTypeAndTierDisplayName", ""),
                "tierTypeName": row.get("tierTypeName", ""),
                "bucketTypeHash": row.get("bucketTypeHash", ""),
                "categoryNames": " | ".join(row.get("categoryNames", []) or []),
            })


def _profile_files() -> dict[str, str]:
    paths = {
        "items_readable": PROFILE_DIR / "items_readable.json",
        "weapons": PROFILE_DIR / "weapons.csv",
        "armor": PROFILE_DIR / "armor.csv",
        "exotics": PROFILE_DIR / "exotics.csv",
        "craftables": PROFILE_DIR / "craftables.json",
        "craftables_csv": PROFILE_DIR / "craftables.csv",
    }
    return {key: str(path) for key, path in paths.items() if path.exists()}
