# BdgrovesBot

Wikipedia bot for automated wildfire acreage updates, operated by [User:Bdgroves](https://en.wikipedia.org/wiki/User:Bdgroves).

## What it does
- Queries WFIGS (National Interagency Fire Center) and CAL FIRE daily
- Updates fire acreages and containment on Wikipedia wildfire pages
- Currently targets:
  - [2026 Tuolumne County wildfires](https://en.wikipedia.org/wiki/2026_Tuolumne_County_wildfires)
  - [Wildfires in Tuolumne County, California](https://en.wikipedia.org/wiki/Wildfires_in_Tuolumne_County,_California)

## Setup

```bash
# 1. Install pixi (https://pixi.sh)
# Windows PowerShell:
iwr -useb https://pixi.sh/install.ps1 | iex

# 2. Install dependencies
pixi install

# 3. Configure Wikipedia credentials
cp user-config.example.py user-config.py
# Edit user-config.py with your Wikipedia username

# 4. Run in dry-run mode (safe — no edits made)
pixi run dryrun

# 5. When ready to go live
pixi run bot
```

## Project structure
```
bdgrovesbot/
├── pixi.toml              — dependency management
├── user-config.py         — pywikibot credentials (not committed)
├── bot/
│   ├── tuolumne_bot.py    — Tuolumne County fire updater
│   ├── nevada_bot.py      — Nevada fire updater (future)
│   └── wfigs.py           — shared WFIGS API helper
└── logs/                  — run logs
```

## Bot compliance
- Operated under Wikipedia bot policy
- DRY_RUN=True by default — must explicitly set False to make edits
- Edit summaries always cite WFIGS as data source
- Trial mode before any BAG approval request
