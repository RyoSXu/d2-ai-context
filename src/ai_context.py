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
