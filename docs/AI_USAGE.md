# AI Usage Guide

This repository is a local read-only Destiny 2 context source for AI-assisted build discussion.

## Read Order

When an AI agent starts a task, read these first:

1. `data/context/ai_context_pack.md`
2. `data/manifest/manifest_meta.json`
3. `data/profile/weapons.csv`
4. `data/profile/armor.csv`
5. `data/profile/exotics.csv`
6. `data/exports/*/indexes/inventory_items_index.csv`
7. `data/exports/*/indexes/sandbox_perks_index.csv`

Only query the full SQLite database or `tables_jsonl_gz` files when the indexes are not enough.

## Commands

Generate/update the compact AI context pack:

```powershell
python main.py setup
python main.py sync
python main.py doctor
```

Generate/update only the compact AI context pack:

```powershell
python main.py context-pack
```

Search current Manifest and profile data:

```powershell
python main.py search "星界夜鹰"
python main.py search "诱导推销" --scope manifest
python main.py search "边缘交通" --scope profile
```

Update current Bungie Manifest:

```powershell
python main.py manifest
```

Refresh private profile data:

```powershell
python main.py profile
python main.py parse
```

Export all Manifest tables and indexes:

```powershell
python main.py export-data
```

## Data Boundaries

Facts from Bungie/API:

- Manifest table contents.
- Profile inventory, character, item instance, socket, stat, and craftable data.
- Chinese item and perk names/descriptions.

External judgment:

- User-provided rules or notes.
- Patch-note interpretation.
- Community recommendations.
- Activity-specific build discussion.

When answering build questions, explicitly separate API facts from external judgment.

## Privacy

Private files:

- `.env`
- `data/token.json`
- `data/profile/raw_profile.json`
- profile-derived CSV/JSON files if sharing publicly

Do not upload or paste private token/API secret/profile files.

## Safety

This project is read-only. Agents must not add or call write endpoints such as:

- transfer item
- equip item
- socket item
- dismantle item
- purchase item
- focus item

## Latest-Version Rule

For live/meta recommendations, always verify the current date and current Destiny 2 version first.

Use:

```powershell
python main.py sync
python main.py doctor
```

Then check official Bungie update notes and only use community sources that are clearly current for the active patch.
