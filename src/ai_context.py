from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .config import DATA_DIR, PROFILE_DIR, Settings
from .manifest_loader import ManifestLoader
from .utils import display_name, read_json


CONTEXT_DIR = DATA_DIR / "context"


SEARCH_TABLES = {
    "items": "DestinyInventoryItemDefinition",
    "perks": "DestinySandboxPerkDefinition",
    "collectibles": "DestinyCollectibleDefinition",
    "activities": "DestinyActivityDefinition",
    "records": "DestinyRecordDefinition",
    "vendors": "DestinyVendorDefinition",
}

ARMOR_STAT_NAMES = ["Mobility", "Resilience", "Recovery", "Discipline", "Intellect", "Strength"]
PROFILE_ITEM_PATH = PROFILE_DIR / "items_readable.json"


def search_data(settings: Settings, query: str, *, limit: int = 20, scope: str = "all") -> dict[str, Any]:
    loader = ManifestLoader(settings)
    if not loader.db_path or not loader.db_path.exists():
        loader.update()

    results: dict[str, Any] = {"query": query, "scope": scope, "manifest": {}, "profile": {}}
    if scope in ("all", "manifest"):
        results["manifest"] = _search_manifest(loader, query, limit)
    if scope in ("all", "profile"):
        results["profile"] = _search_profile(query, limit)
    return results


def print_search_results(results: dict[str, Any]) -> None:
    print(f"Query: {results['query']}")
    manifest = results.get("manifest") or {}
    for label, rows in manifest.items():
        print(f"\n[{label}] {len(rows)}")
        for row in rows:
            parts = [str(row.get("hash", "")), row.get("name", ""), row.get("type", "")]
            desc = row.get("description", "")
            if desc:
                parts.append(desc[:120].replace("\n", " "))
            print(" | ".join(part for part in parts if part))

    profile = results.get("profile") or {}
    for label, rows in profile.items():
        print(f"\n[profile:{label}] {len(rows)}")
        for row in rows:
            print(" | ".join(str(row.get(key, "")) for key in ["name", "itemTypeDisplayName", "damageType", "perk1", "perk2", "location"] if row.get(key, "") != ""))


def inspect_item(settings: Settings, query: str, *, owned_limit: int = 10) -> dict[str, Any]:
    loader = ManifestLoader(settings)
    if not loader.db_path or not loader.db_path.exists():
        loader.update()

    item = _resolve_inventory_item(loader, query)
    if not item:
        return {"query": query, "found": False, "item": None, "owned": [], "alternatives": []}

    alternatives = []
    if not _looks_like_hash(query):
        alternatives = [
            _manifest_summary(candidate)
            for candidate in loader.search_inventory_items(query, limit=10)
            if candidate.get("hash") != item.get("hash")
        ]

    owned_name = query if not _looks_like_hash(query) else None
    owned = _owned_instances(item, owned_limit, name=owned_name)
    return {
        "query": query,
        "found": True,
        "item": _manifest_detail(loader, item),
        "owned": owned,
        "owned_total": _owned_total(item, name=owned_name),
        "alternatives": alternatives,
    }


def print_inspect_item(result: dict[str, Any]) -> None:
    if not result.get("found"):
        print(f"未找到物品：{result.get('query', '')}")
        print("建议先运行 python main.py manifest，或检查中文名 / item hash。")
        return

    item = result["item"]
    print(f"# {item['name']}")
    print("")
    print("## Bungie/API 事实")
    print(f"- hash: {item['hash']}")
    print(f"- 类型: {_join_nonempty([item.get('tier'), item.get('typeName')])}")
    if item.get("itemTypeDisplayName"):
        print(f"- 类别: {item['itemTypeDisplayName']}")
    if item.get("classType"):
        print(f"- 职业限制: {item['classType']}")
    if item.get("damageType"):
        print(f"- 伤害类型: {item['damageType']}")
    if item.get("ammoType"):
        print(f"- 弹药类型: {item['ammoType']}")
    if item.get("description"):
        print(f"- 官方描述: {item['description']}")
    if item.get("flavorText"):
        print(f"- 风味文本: {item['flavorText']}")
    if item.get("collectibleHash"):
        print(f"- collectibleHash: {item['collectibleHash']}")
    if item.get("icon"):
        print(f"- icon: {item['icon']}")
    if item.get("screenshot"):
        print(f"- screenshot: {item['screenshot']}")

    stats = item.get("stats") or {}
    if stats:
        print("")
        print("## 定义属性")
        for name, value in stats.items():
            print(f"- {name}: {value}")

    owned = result.get("owned") or []
    print("")
    print("## 用户 Profile 事实")
    print(f"- 拥有实例数: {result.get('owned_total', len(owned))}")
    if not owned:
        print("- 当前解析数据里没有找到该物品实例。")
        print("- 如果刚同步过 Profile，请运行 python main.py parse 后重试。")
    for index, instance in enumerate(owned, start=1):
        _print_owned_instance(index, instance)

    alternatives = result.get("alternatives") or []
    if alternatives:
        print("")
        print("## 其他同名/近似 Manifest 命中")
        for candidate in alternatives[:5]:
            print(f"- {candidate['hash']} | {candidate['name']} | {candidate.get('typeName', '')}")


def build_context_pack(settings: Settings) -> Path:
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    loader = ManifestLoader(settings)
    if not loader.db_path or not loader.db_path.exists():
        loader.update()

    manifest_meta = read_json(DATA_DIR / "manifest" / "manifest_meta.json", default={}) or {}
    raw_profile = read_json(PROFILE_DIR / "raw_profile.json", default={}) or {}
    parsed_items = read_json(PROFILE_DIR / "items_readable.json", default={}) or {}

    lines: list[str] = []
    lines.append("# AI Context Pack: d2-ai-context")
    lines.append("")
    lines.append("## What This Repository Contains")
    lines.append("")
    lines.append("This repository is a local read-only Destiny 2 context framework for AI-assisted build discussion.")
    lines.append("It contains the current Bungie Manifest SQLite database, exported indexes, the user's OAuth profile data, and parsed readable inventory.")
    lines.append("")
    lines.append("## Freshness")
    lines.append("")
    lines.append(f"- Manifest version: {manifest_meta.get('version', 'unknown')}")
    lines.append(f"- Manifest locale: {manifest_meta.get('locale', 'unknown')}")
    lines.append(f"- Profile fetched at: {raw_profile.get('fetched_at', 'unknown')}")
    membership = raw_profile.get("membership", {})
    lines.append(f"- Profile owner: {membership.get('displayName', 'unknown')} / membershipType={membership.get('membershipType', 'unknown')} / destinyMembershipId={membership.get('membershipId', 'unknown')}")
    lines.append("")
    lines.append("## First Files To Read")
    lines.append("")
    lines.append("- `docs/AI_USAGE.md`: instructions for AI agents.")
    lines.append("- `data/manifest/manifest_meta.json`: current manifest version and SQLite path.")
    lines.append("- `data/exports/*/manifest_export_summary.json`: full table list and row counts.")
    lines.append("- `data/exports/*/indexes/inventory_items_index.csv`: searchable item index.")
    lines.append("- `data/exports/*/indexes/sandbox_perks_index.csv`: searchable perk index with descriptions.")
    lines.append("- `data/profile/weapons.csv`: user's readable weapons and current rolls.")
    lines.append("- `data/profile/exotics.csv`: user's exotic armor.")
    lines.append("")
    lines.append("## Useful Commands")
    lines.append("")
    lines.append("```powershell")
    lines.append("python main.py manifest")
    lines.append("python main.py profile")
    lines.append("python main.py parse")
    lines.append("python main.py export-data")
    lines.append("python main.py search \"星界夜鹰\"")
    lines.append("python main.py search \"诱导推销\" --scope manifest")
    lines.append("python main.py inspect-item \"牵引器火炮\"")
    lines.append("python main.py context-pack")
    lines.append("```")
    lines.append("")
    lines.append("## Current User Inventory Summary")
    lines.append("")
    weapons_count = _csv_count(PROFILE_DIR / "weapons.csv")
    armor_count = _csv_count(PROFILE_DIR / "armor.csv")
    exotics_count = _csv_count(PROFILE_DIR / "exotics.csv")
    lines.append(f"- Weapons CSV rows: {weapons_count}")
    lines.append(f"- Armor CSV rows: {armor_count}")
    lines.append(f"- Exotics CSV rows: {exotics_count}")
    lines.append(f"- Parsed items: {len(parsed_items.get('items', [])) if parsed_items else 0}")
    lines.append("")
    lines.append("## Safety")
    lines.append("")
    lines.append("- This project is read-only with respect to Bungie account data.")
    lines.append("- Do not call transfer/equip/dismantle/purchase/focus APIs.")
    lines.append("- `.env`, `data/token.json`, and `data/profile/raw_profile.json` are private.")
    lines.append("- When discussing builds, distinguish Bungie/Manifest/Profile facts from community/meta judgments.")
    lines.append("")

    output = CONTEXT_DIR / "ai_context_pack.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _search_manifest(loader: ManifestLoader, query: str, limit: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    with loader._connect() as conn:  # noqa: SLF001 - local tool intentionally reuses manifest connection.
        for label, table in SEARCH_TABLES.items():
            rows = conn.execute(f'select json from "{table}" where json like ? limit ?', (f"%{query}%", limit)).fetchall()
            out[label] = []
            for (raw,) in rows:
                data = json.loads(raw)
                out[label].append(
                    {
                        "hash": data.get("hash"),
                        "name": display_name(data),
                        "type": data.get("itemTypeDisplayName") or data.get("itemTypeAndTierDisplayName") or "",
                        "description": data.get("displayProperties", {}).get("description", ""),
                    }
                )
    return out


def _search_profile(query: str, limit: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for name, path in {
        "weapons": PROFILE_DIR / "weapons.csv",
        "armor": PROFILE_DIR / "armor.csv",
        "exotics": PROFILE_DIR / "exotics.csv",
    }.items():
        out[name] = []
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if query in " ".join(str(value) for value in row.values()):
                    out[name].append(row)
                    if len(out[name]) >= limit:
                        break
    return out


def _resolve_inventory_item(loader: ManifestLoader, query: str) -> dict[str, Any] | None:
    if _looks_like_hash(query):
        return loader.get_inventory_item(query)

    matches = loader.search_inventory_items(query, limit=50)
    if not matches:
        return None

    normalized = query.casefold()
    exact = [item for item in matches if display_name(item, "").casefold() == normalized]
    owned_hashes = _owned_hashes_for_name(query)
    for owned_hash in owned_hashes:
        for item in exact:
            if str(item.get("hash")) == owned_hash:
                return item
    return exact[0] if exact else matches[0]


def _looks_like_hash(query: str) -> bool:
    text = query.strip()
    if text.startswith("-"):
        text = text[1:]
    return text.isdigit()


def _manifest_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "hash": item.get("hash"),
        "name": display_name(item, str(item.get("hash", ""))),
        "typeName": item.get("itemTypeAndTierDisplayName", ""),
        "itemTypeDisplayName": item.get("itemTypeDisplayName", ""),
    }


def _manifest_detail(loader: ManifestLoader, item: dict[str, Any]) -> dict[str, Any]:
    summary = _manifest_summary(item)
    damage = loader.get_damage_type(item.get("defaultDamageTypeHash"))
    summary.update(
        {
            "description": item.get("displayProperties", {}).get("description", ""),
            "flavorText": item.get("flavorText", ""),
            "tier": item.get("inventory", {}).get("tierTypeName") or item.get("inventory", {}).get("tierType"),
            "classType": _class_type_name(item.get("classType")),
            "damageType": display_name(damage, ""),
            "ammoType": _ammo_type_name(item.get("equippingBlock", {}).get("ammoType")),
            "collectibleHash": item.get("collectibleHash"),
            "icon": item.get("displayProperties", {}).get("icon", ""),
            "screenshot": item.get("screenshot", ""),
            "stats": _definition_stats(loader, item),
        }
    )
    return summary


def _owned_instances(item: dict[str, Any], limit: int, *, name: str | None = None) -> list[dict[str, Any]]:
    parsed = read_json(PROFILE_ITEM_PATH, default={}) or {}
    item_hash = item.get("hash")
    if name:
        normalized = name.casefold()
        rows = [row for row in parsed.get("items", []) if str(row.get("name", "")).casefold() == normalized]
    else:
        rows = [row for row in parsed.get("items", []) if str(row.get("itemHash")) == str(item_hash)]
    return rows[:limit]


def _owned_hashes_for_name(name: str) -> list[str]:
    parsed = read_json(PROFILE_ITEM_PATH, default={}) or {}
    normalized = name.casefold()
    hashes: list[str] = []
    for row in parsed.get("items", []):
        item_hash = row.get("itemHash")
        if str(row.get("name", "")).casefold() == normalized and item_hash is not None and str(item_hash) not in hashes:
            hashes.append(str(item_hash))
    return hashes


def _owned_total(item: dict[str, Any], *, name: str | None = None) -> int:
    parsed = read_json(PROFILE_ITEM_PATH, default={}) or {}
    item_hash = item.get("hash")
    if name:
        normalized = name.casefold()
        return sum(1 for row in parsed.get("items", []) if str(row.get("name", "")).casefold() == normalized)
    return sum(1 for row in parsed.get("items", []) if str(row.get("itemHash")) == str(item_hash))


def _definition_stats(loader: ManifestLoader, item: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for stat_hash, stat in (item.get("stats", {}).get("stats") or {}).items():
        value = stat.get("value")
        if value in ("", None):
            continue
        stat_def = loader.get_stat(stat_hash)
        name = display_name(stat_def, str(stat_hash))
        out[name] = value
    return out


def _print_owned_instance(index: int, instance: dict[str, Any]) -> None:
    print("")
    print(f"### 实例 {index}")
    basics = [
        f"itemHash={instance.get('itemHash')}" if instance.get("itemHash") else "",
        f"instanceId={instance.get('itemInstanceId')}" if instance.get("itemInstanceId") else "",
        f"光等={instance.get('power')}" if instance.get("power") is not None else "",
        f"位置={instance.get('location', '')}",
        "已装备" if instance.get("isEquipped") else "",
        "已锁定" if instance.get("isLocked") else "",
    ]
    print(f"- 基础: {_join_nonempty(basics)}")
    if instance.get("damageType"):
        print(f"- 伤害类型: {instance['damageType']}")
    if instance.get("classType"):
        print(f"- 职业: {instance['classType']}")

    roll = _roll_parts(instance)
    if roll:
        print(f"- 当前 roll: {_join_nonempty(roll)}")
    if instance.get("crafted") is not None:
        print(f"- 可制作/塑造标记: {'是' if instance.get('crafted') else '否'}")
    enhanced = instance.get("enhanced_traits") or []
    if enhanced:
        print(f"- 强化特性: {', '.join(enhanced)}")

    armor_stats = {name: instance.get(name) for name in ARMOR_STAT_NAMES if instance.get(name) not in ("", None)}
    if armor_stats:
        text = ", ".join(f"{name}={value}" for name, value in armor_stats.items())
        if instance.get("totalStats") not in ("", None):
            text = f"{text}, total={instance['totalStats']}"
        print(f"- 护甲属性: {text}")

    sockets = instance.get("allSocketsReadable") or instance.get("socketsReadable") or []
    if sockets:
        print("- Socket:")
        for socket in sockets:
            name = socket.get("name") or ""
            plug_hash = socket.get("plugHash")
            reusable_count = len(socket.get("reusablePlugHashes") or [])
            if not name and not plug_hash:
                continue
            suffix = f", 可选 {reusable_count}" if reusable_count else ""
            print(f"  - [{socket.get('index')}] {name or '(空)'} ({plug_hash}){suffix}")


def _roll_parts(instance: dict[str, Any]) -> list[str]:
    keys = ["intrinsic", "barrel", "magazine", "perk1", "perk2", "originTrait", "masterwork"]
    return [str(instance.get(key)) for key in keys if instance.get(key)]


def _class_type_name(value: Any) -> str:
    return {0: "Titan", 1: "Hunter", 2: "Warlock", 3: "通用"}.get(value, str(value) if value not in ("", None) else "")


def _ammo_type_name(value: Any) -> str:
    return {1: "主弹药", 2: "特殊弹药", 3: "重弹药"}.get(value, "")


def _join_nonempty(values: list[Any]) -> str:
    return " | ".join(str(value) for value in values if value not in ("", None))


def _csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def add_ai_subcommands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    search_parser = subparsers.add_parser("search", help="Search manifest and profile data for AI context.")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--scope", choices=["all", "manifest", "profile"], default="all")

    subparsers.add_parser("context-pack", help="Generate a compact Markdown context pack for AI agents.")

    inspect_parser = subparsers.add_parser("inspect-item", help="Inspect one manifest item and owned profile instances.")
    inspect_parser.add_argument("query", help="Chinese item name or item hash.")
    inspect_parser.add_argument("--owned-limit", type=int, default=10, help="Maximum owned instances to print.")
    inspect_parser.add_argument("--json", action="store_true", help="Print structured JSON instead of readable text.")
