from __future__ import annotations

import argparse
import sys

from src.ai_context import (
    add_ai_subcommands,
    build_context_pack,
    inspect_item,
    print_weapon_perk_pool,
    print_inspect_item,
    print_search_results,
    search_data,
    weapon_perk_pool,
)
from src.config import load_settings
from src.item_parser import parse_items
from src.data_exporter import export_manifest_data
from src.manifest_loader import ManifestLoader
from src.oauth import get_valid_token
from src.operations import print_checks, print_sync_result, run_doctor, run_setup, run_sync
from src.profile_loader import load_profile


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Destiny 2 AI Context Framework")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ["setup", "sync", "doctor", "manifest", "login", "profile", "parse", "export-data", "all"]:
        subparsers.add_parser(command)
    add_ai_subcommands(subparsers)
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "setup":
        print_checks(run_setup(settings))
        return

    if args.command == "doctor":
        print_checks(run_doctor(settings))
        return

    if args.command == "sync":
        print_sync_result(run_sync(settings))
        return

    if args.command in ("manifest", "all"):
        meta = ManifestLoader(settings).update()
        print(f"Manifest ready: version={meta.get('version')} locale={meta.get('locale')}")

    if args.command in ("login", "all"):
        token = get_valid_token(settings, force_login=args.command == "login")
        print(f"OAuth token ready. expires_at={token.get('expires_at')}")

    if args.command in ("profile", "all"):
        raw = load_profile(settings)
        membership = raw.get("membership", {})
        print(f"Profile saved: membershipType={membership.get('membershipType')} membershipId={membership.get('membershipId')}")

    if args.command in ("parse", "all"):
        parsed = parse_items(ManifestLoader(settings))
        print(f"Parsed items: {len(parsed.get('items', []))}")

    if args.command in ("export-data",):
        summary = export_manifest_data(settings)
        print(f"Manifest export written: {summary.get('output_dir')}")
        print(f"Tables exported: {len(summary.get('tables', {}))}")

    if args.command == "search":
        results = search_data(settings, args.query, limit=args.limit, scope=args.scope)
        print_search_results(results)

    if args.command == "context-pack":
        path = build_context_pack(settings)
        print(f"AI context pack written: {path}")

    if args.command == "inspect-item":
        result = inspect_item(settings, args.query, owned_limit=args.owned_limit)
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_inspect_item(result)

    if args.command == "perk-pool":
        result = weapon_perk_pool(settings, args.query, include_reusable=args.include_reusable)
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_weapon_perk_pool(result)


if __name__ == "__main__":
    main()
