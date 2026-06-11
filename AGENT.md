# d2-ai-context Agent Notes

## Project Goal

Build a reusable, local, read-only Destiny 2 context framework for AI tools.

The project should collect and normalize:

- latest Bungie Manifest data
- user's read-only Bungie Profile and inventory data
- parsed weapons, armor, exotics, sockets, stats, and craftables
- optional external knowledge supplied by the user

so AI tools can discuss builds with the user, explain rolls and perks in Chinese, compare owned and missing items, and suggest next farming priorities from real local context.

The project provides data and context for AI conversations. It must not execute account mutations.

## Current Project Path

`C:\D2\d2-analyzer`

## Current State

Implemented:

- Manifest download/update/cache.
- HTTPS OAuth login and token refresh.
- Profile pull and raw profile save.
- Item parsing to readable JSON/CSV.
- Manifest full export to compressed JSONL and CSV indexes.
- AI context pack generation.
- Search command over Manifest and profile data.
- Installer/user convenience commands:
  - `python main.py setup`
  - `python main.py sync`
  - `python main.py doctor`

Validated previously:

- `python -m compileall .`
- `python main.py setup`
- `python main.py sync`
- `python main.py doctor`

Latest known local Manifest:

- version: `244019.26.05.29.1640-4-bnet.65312`
- locale: `zh-chs`

## Important Commands

```powershell
python main.py setup
python main.py sync
python main.py doctor
python main.py manifest
python main.py login
python main.py profile
python main.py parse
python main.py export-data
python main.py context-pack
python main.py search "星界夜鹰"
python main.py search "诱导推销" --scope manifest
python main.py search "边缘交通" --scope profile
```

## Key Files

Read these first when continuing development:

- `README.md`
- `docs/AI_USAGE.md`
- `data/context/ai_context_pack.md`
- `data/manifest/manifest_meta.json`
- `src/operations.py`
- `src/ai_context.py`
- `src/manifest_loader.py`
- `src/item_parser.py`
- `src/data_exporter.py`

Useful generated data:

- `data/profile/weapons.csv`
- `data/profile/armor.csv`
- `data/profile/exotics.csv`
- `data/profile/items_readable.json`
- `data/exports/*/indexes/inventory_items_index.csv`
- `data/exports/*/indexes/sandbox_perks_index.csv`

## Privacy and Safety

This project must remain read-only for Bungie accounts.

Never add or call account write endpoints:

- transfer item
- equip item
- socket item
- dismantle item
- purchase item
- focus item

Private files:

- `.env`
- `data/token.json`
- `data/profile/raw_profile.json`
- profile-derived exports if the user intends to share publicly

Do not commit, upload, paste, or package private files.

## AI Answering Policy

When using this repository to answer build or item questions, separate these categories explicitly:

- Bungie/API facts: Manifest definitions, item names, perk descriptions, sockets, stats, user-owned item instances.
- User profile facts: what the current user owns, equipped state if available, character data, craftable data.
- External judgment: user-provided rules, patch-note interpretation, community consensus, activity-specific recommendations.

Do not let text retrieval or community text decide whether the user owns an item. Ownership and roll details must come from structured profile data.

For live/meta recommendations, verify current date, current Destiny 2 version, and current patch context before presenting strong conclusions.

## Architecture Direction

Do not rewrite the project from scratch. Evolve it.

Recommended architecture:

```text
Core local data framework
├─ data layer: Manifest SQLite and user profile data
├─ parse/export layer: readable JSON, CSV indexes, context pack
├─ query layer: structured search, SQL/index lookup, optional text retrieval
└─ AI interface layer: CLI, MCP server, Codex skill, HTTP API
```

Integration split:

- CLI: baseline user and script interface.
- Context pack: lowest-friction AI input for any chat tool.
- MCP server: preferred tool interface for AI clients that support tools.
- Codex skill: workflow instructions for using this project or its MCP tools.
- HTTP API: optional interface for custom apps, bots, and OpenAI API workflows.

Skill/MCP/HTTP layers should call the local data framework. They should not contain Manifest SQLite files, OAuth tokens, or private profile data.

## Retrieval Policy

Use structured queries for structured facts:

- user ownership
- item hash/name/type
- current roll
- perk pool
- official perk descriptions
- sockets and plug sets

Use text retrieval only for non-authoritative explanatory context supplied by the user.

## Next Development Tasks

Highest priority:

1. `inspect-item`
   - Input: Chinese item name or hash.
   - Output: item basics, official Chinese description, user-owned instances, socket/perk/stat details.

2. `perk-pool`
   - Input: Chinese weapon name or hash.
   - Output: full perk pool by socket column.
   - Include Chinese perk names and descriptions.
   - Use Manifest `sockets`, `socketEntries`, `randomizedPlugSetHash`, `reusablePlugSetHash`, and `DestinyPlugSetDefinition`.

3. MCP server
   - Expose structured tools:
     - `d2_search_manifest`
     - `d2_search_profile`
     - `d2_get_item`
     - `d2_get_perk`
     - `d2_get_weapon_perk_pool`
     - `d2_get_user_context`
     - `d2_compare_missing_items`
     - `d2_refresh_manifest`
     - `d2_refresh_profile`

4. Codex skill
   - Package only workflow instructions and lightweight references.
   - Teach Codex to read `docs/AI_USAGE.md`, context pack, profile CSVs, and indexes.
   - Delegate data access to CLI/MCP instead of embedding private or generated data.

## Coding Guidelines

- Keep user-facing output in Chinese unless the user asks otherwise.
- Prefer official Chinese Manifest names for items and perks.
- If a Chinese name is not in Manifest, use official/community Simplified Chinese naming and mark it as external.
- Use `pathlib`.
- Preserve read-only account behavior.
- Avoid committing generated data unless explicitly requested.
- Keep AI-facing output clear about:
  - Bungie/API facts
  - user profile facts
  - external judgment

## Current User Preference

The user wants this project to become a reusable AI context framework.

They care about:

- latest-version correctness
- Chinese item/perk names
- user inventory-aware discussion
- build context generation
- missing item analysis
- future reuse through CLI, files, MCP, Codex Skill, HTTP API, or external AI chat tools
