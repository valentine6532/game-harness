---
name: d2b2-reference
description: Search the locally archived D2B2 Diablo II Resurrected item database when item names, base items, uniques, sets, runewords, or item tooltip data are relevant. Do not use it as a source for Diablo III or IV mechanics.
---

# D2B2 item reference

The local archive is in `~/.agents/reference-data/d2b2`, independent of the Orca account directory. Read `latest.json` there for the current game version and snapshot path. Use the source URL and game version when reporting specific facts. This is reference material for designing original game systems, not content to copy into the game.

Search with `python <this skill folder>/scripts/search.py <query>`. For a complete item record add `--id <item-id>`. The raw snapshot also contains `catalog.json`, all listed language name files, tooltip strings, tooltip core tables, one tooltip JSON per catalog item, and referenced item images. Inspect raw tables when a search result does not contain the needed detail.

Create or refresh the archive with `python <this skill folder>/scripts/sync.py`; on a new PC the archive does not exist until this has run once. Both scripts use `~/.agents/reference-data/d2b2` wherever the skill is installed (`--data-root` overrides it). The script writes an immutable version directory and updates `latest.json` only after all downloads validate. The site covers D2R items and related tooltip tables, not every Diablo game system. Verify other mechanics from separate sources.
