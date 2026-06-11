from __future__ import annotations

from typing import Any

import pandas as pd

from .config import PROFILE_DIR
from .manifest_loader import ManifestLoader
from .utils import display_name, get_path, read_json, write_json


CLASS_NAMES = {0: "Titan", 1: "Hunter", 2: "Warlock", 3: "Unknown"}
ITEM_TYPE_WEAPON = 3
ITEM_TYPE_ARMOR = 2
TIER_EXOTIC = 6
STAT_HASHES = {
    2996146975: "Mobility",
    392767087: "Resilience",
    1943323491: "Recovery",
    1735777505: "Discipline",
    144602215: "Intellect",
    4244567218: "Strength",
}
BUCKET_GROUPS = {
    1498876634: "Kinetic",
    2465295065: "Energy",
    953998645: "Heavy",
}
SOCKET_LABELS = ["intrinsic", "barrel", "magazine", "perk1", "perk2", "originTrait", "masterwork"]


def parse_items(manifest: ManifestLoader) -> dict[str, Any]:
    raw = read_json(PROFILE_DIR / "raw_profile.json")
    if not raw:
        raise RuntimeError("缺少 data/profile/raw_profile.json，请先运行 python main.py profile。")
    profile = raw["profile"]
    warnings: list[str] = []
    characters = get_path(profile, "characters", "data", default={}) or {}
    instances = get_path(profile, "itemComponents", "instances", "data", default={}) or {}
    sockets = get_path(profile, "itemComponents", "sockets", "data", default={}) or {}
    stats = get_path(profile, "itemComponents", "stats", "data", default={}) or {}
    reusable = get_path(profile, "itemComponents", "reusablePlugs", "data", default={}) or {}
    craftables = get_path(profile, "characterCraftables", "data", default={}) or {}

    equipment_ids = _equipment_ids(profile)
    inventory_items = _all_inventory_items(profile)
    readable: list[dict[str, Any]] = []
    weapons: list[dict[str, Any]] = []
    armor: list[dict[str, Any]] = []
    exotics: list[dict[str, Any]] = []

    for source in inventory_items:
        item = dict(source["item"])
        item_hash = item.get("itemHash")
        item_instance_id = item.get("itemInstanceId")
        definition = manifest.get_inventory_item(item_hash)
        if not definition:
            warnings.append(f"找不到物品定义 itemHash={item_hash}")
            continue

        instance = instances.get(str(item_instance_id), {}) if item_instance_id else {}
        socket_data = sockets.get(str(item_instance_id), {}) if item_instance_id else {}
        stat_data = stats.get(str(item_instance_id), {}) if item_instance_id else {}
        reusable_data = reusable.get(str(item_instance_id), {}) if item_instance_id else {}
        socket_info = _socket_info(manifest, socket_data, reusable_data)
        common = _common_fields(manifest, definition, item, instance, source, item_instance_id in equipment_ids, socket_info)

        if definition.get("itemType") == ITEM_TYPE_WEAPON:
            row = _weapon_row(manifest, definition, common, socket_info)
            row["crafted"] = _looks_crafted(socket_info)
            row["shaped"] = row["crafted"]
            row["enhanced_traits"] = [s["name"] for s in socket_info if "enhanced" in s.get("name", "").lower() or "强化" in s.get("name", "")]
            weapons.append(row)
            readable.append(row)
        elif definition.get("itemType") == ITEM_TYPE_ARMOR:
            row = _armor_row(manifest, definition, common, stat_data, socket_info)
            armor.append(row)
            readable.append(row)
            if definition.get("inventory", {}).get("tierType") == TIER_EXOTIC:
                exotics.append(row)
        else:
            readable.append(common)

    outputs = {
        "metadata": {
            "profile_fetched_at": raw.get("fetched_at"),
            "membership": raw.get("membership"),
            "characters": characters,
            "warnings": warnings,
        },
        "items": readable,
    }
    write_json(PROFILE_DIR / "items_readable.json", outputs)
    _write_csv(PROFILE_DIR / "weapons.csv", weapons)
    _write_csv(PROFILE_DIR / "armor.csv", armor)
    _write_csv(PROFILE_DIR / "exotics.csv", exotics)
    write_json(PROFILE_DIR / "craftables.json", craftables)
    _write_csv(PROFILE_DIR / "craftables.csv", _flatten_craftables(craftables))
    return outputs


def _all_inventory_items(profile: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for item in get_path(profile, "profileInventory", "data", "items", default=[]) or []:
        collected.append({"item": item, "location": "profile", "characterId": "", "vault": True})
    for char_id, inventory in (get_path(profile, "characterInventories", "data", default={}) or {}).items():
        for item in inventory.get("items", []):
            collected.append({"item": item, "location": "character_inventory", "characterId": char_id, "vault": False})
    for char_id, equipment in (get_path(profile, "characterEquipment", "data", default={}) or {}).items():
        for item in equipment.get("items", []):
            collected.append({"item": item, "location": "equipped", "characterId": char_id, "vault": False})
    return collected


def _equipment_ids(profile: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for equipment in (get_path(profile, "characterEquipment", "data", default={}) or {}).values():
        ids.update(str(item.get("itemInstanceId")) for item in equipment.get("items", []) if item.get("itemInstanceId"))
    return ids


def _common_fields(manifest: ManifestLoader, definition: dict[str, Any], item: dict[str, Any], instance: dict[str, Any], source: dict[str, Any], equipped: bool, sockets: list[dict[str, Any]]) -> dict[str, Any]:
    bucket = manifest.get_bucket(item.get("bucketHash") or definition.get("inventory", {}).get("bucketTypeHash"))
    damage = manifest.get_damage_type(instance.get("damageTypeHash") or definition.get("defaultDamageTypeHash"))
    tier = definition.get("inventory", {}).get("tierTypeName") or definition.get("inventory", {}).get("tierType")
    return {
        "itemInstanceId": item.get("itemInstanceId", ""),
        "name": display_name(definition, str(item.get("itemHash"))),
        "itemHash": item.get("itemHash"),
        "typeName": definition.get("itemTypeAndTierDisplayName", ""),
        "itemTypeDisplayName": definition.get("itemTypeDisplayName", ""),
        "tierTypeName": tier,
        "bucket": display_name(bucket, ""),
        "bucketHash": item.get("bucketHash") or definition.get("inventory", {}).get("bucketTypeHash"),
        "classType": CLASS_NAMES.get(definition.get("classType", 3), str(definition.get("classType", ""))),
        "power": instance.get("primaryStat", {}).get("value"),
        "isEquipped": equipped,
        "isLocked": bool(int(item.get("state", 0)) & 1),
        "location": source["location"],
        "characterId": source["characterId"],
        "vault": source["vault"],
        "damageType": display_name(damage, ""),
        "collectibleHash": definition.get("collectibleHash"),
        "icon": definition.get("displayProperties", {}).get("icon", ""),
        "screenshot": definition.get("screenshot", ""),
        "allSocketsReadable": sockets,
    }


def _weapon_row(manifest: ManifestLoader, definition: dict[str, Any], common: dict[str, Any], sockets: list[dict[str, Any]]) -> dict[str, Any]:
    row = dict(common)
    row["ammoType"] = definition.get("equippingBlock", {}).get("ammoType", "")
    for label, socket in zip(SOCKET_LABELS, sockets):
        row[label] = socket.get("name", "")
    row["statsReadable"] = _definition_stats(manifest, definition)
    row["slotGroup"] = BUCKET_GROUPS.get(int(row.get("bucketHash") or 0), row.get("bucket", ""))
    return row


def _armor_row(manifest: ManifestLoader, definition: dict[str, Any], common: dict[str, Any], stat_data: dict[str, Any], sockets: list[dict[str, Any]]) -> dict[str, Any]:
    row = dict(common)
    row["slot"] = common.get("bucket", "")
    row["energyType"] = get_path(stat_data, "energy", "energyTypeHash", default="")
    row["energyCapacity"] = get_path(stat_data, "energy", "energyCapacity", default="")
    armor_stats: dict[str, int] = {}
    for raw_hash, stat in (stat_data.get("stats") or {}).items():
        name = STAT_HASHES.get(int(raw_hash))
        if name:
            armor_stats[name] = stat.get("value", 0)
    row.update({name: armor_stats.get(name, 0) for name in STAT_HASHES.values()})
    row["totalStats"] = sum(armor_stats.values())
    row["exotic_or_legendary"] = "Exotic" if definition.get("inventory", {}).get("tierType") == TIER_EXOTIC else "Legendary"
    row["socketsReadable"] = sockets
    row["modsReadable"] = [socket["name"] for socket in sockets if socket.get("name")]
    row["armor_tier"] = definition.get("quality", {}).get("infusionCategoryName", "")
    return row


def _socket_info(manifest: ManifestLoader, socket_data: dict[str, Any], reusable_data: dict[str, Any]) -> list[dict[str, Any]]:
    sockets: list[dict[str, Any]] = []
    for index, socket in enumerate(socket_data.get("sockets", []) or []):
        plug_hash = socket.get("plugHash")
        plug_def = manifest.get_inventory_item(plug_hash)
        reusable_hashes = []
        for plug in (reusable_data.get("plugs", {}) or {}).get(str(index), []):
            reusable_hashes.append(plug.get("plugItemHash"))
        sockets.append({
            "index": index,
            "plugHash": plug_hash,
            "name": display_name(plug_def, ""),
            "reusablePlugHashes": reusable_hashes,
        })
    return sockets


def _definition_stats(manifest: ManifestLoader, definition: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for stat_hash, stat in (definition.get("stats", {}).get("stats") or {}).items():
        stat_def = manifest.get_stat(stat_hash)
        name = display_name(stat_def, str(stat_hash))
        out[name] = stat.get("value", 0)
    return out


def _looks_crafted(sockets: list[dict[str, Any]]) -> bool:
    text = " ".join(socket.get("name", "") for socket in sockets).lower()
    return "enhanced" in text or "memento" in text or "强化" in text or "纪念品" in text


def _write_csv(path, rows: list[dict[str, Any]]) -> None:
    flat_rows = []
    for row in rows:
        flat = {key: value for key, value in row.items() if not isinstance(value, (list, dict))}
        flat_rows.append(flat)
    pd.DataFrame(flat_rows).to_csv(path, index=False, encoding="utf-8-sig")


def _flatten_craftables(craftables: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for character_id, payload in craftables.items():
        for craftable_hash, craftable in (payload.get("craftables") or {}).items():
            rows.append({
                "characterId": character_id,
                "craftableHash": craftable_hash,
                "visible": craftable.get("visible"),
                "failedRequirementIndexes": ",".join(str(v) for v in craftable.get("failedRequirementIndexes", [])),
            })
    return rows
