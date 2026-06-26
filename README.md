# 🔥 BdgrovesBot

> *"It's already on the ground."*

A wildfire intelligence bot that watches the fire lines so you don't have to. Built by a GIS analyst who got tired of manually updating Wikipedia at 2am while watching fire perimeters grow on the map.

---

## What it does

BdgrovesBot is always watching. Every morning at 7am Pacific it wakes up, hits the **National Interagency Fire Center's WFIGS API**, pulls live fire perimeter data, and pushes updates straight to Wikipedia — no human in the loop.

When a fire ignites in Tuolumne County and crosses the threshold, the bot sees it before most people are awake. It drops a stub row into the Wikipedia table with acreage, start date, and coordinates. When the fire grows, the bot updates it. When it's contained, the bot marks it green.

The data pipeline runs entirely in the background, automated end-to-end through GitHub Actions. Real fire data. Real-time. On Wikipedia.

```
WFIGS API → BdgrovesBot → Wikipedia
    ↓
QGIS GeoJSON layer (for live fire mapping)
```

---

## The stack

| Layer | Tech |
|---|---|
| Data source | NIFC WFIGS Interagency Perimeters API |
| Bot framework | Python + Pywikibot |
| Dependency management | [pixi](https://pixi.sh) |
| Automation | GitHub Actions (daily cron, 7am Pacific) |
| GIS output | GeoJSON → QGIS live layer |
| Wikipedia auth | Bot password via GitHub Secrets |

---

## Currently tracking

- **[2026 Tuolumne County wildfires](https://en.wikipedia.org/wiki/2026_Tuolumne_County_wildfires)** — active season page
- **[Wildfires in Tuolumne County, California](https://en.wikipedia.org/wiki/Wildfires_in_Tuolumne_County,_California)** — historical record

Coverage expands as fire season demands it.

---

## Setup

```powershell
# 1. Install pixi (Windows PowerShell)
iwr -useb https://pixi.sh/install.ps1 | iex

# 2. Install dependencies
pixi install

# 3. Configure Wikipedia credentials
cp user-config.example.py user-config.py
# Edit user-config.py with your Wikipedia username
# Create passwords.py with your bot password (see user-config.example.py)

# 4. Dry run — safe, no edits made, shows what the bot would do
pixi run dryrun

# 5. Go live
pixi run bot

# 6. Test the full Wikipedia write pipeline
pixi run python bot/tuolumne_bot.py --test-insert --dry-run
pixi run python bot/tuolumne_bot.py --test-insert --no-dry-run
```

---

## Project structure

```
bdgrovesbot/
├── pixi.toml                  — dependency management
├── user-config.py             — pywikibot credentials (not committed)
├── passwords.py               — bot password (not committed, in .gitignore)
├── .github/
│   └── workflows/
│       └── daily_update.yml   — GitHub Actions cron job
├── bot/
│   ├── tuolumne_bot.py        — Tuolumne County fire updater
│   ├── nevada_bot.py          — Nevada fire updater (future)
│   └── wfigs.py               — shared WFIGS API helper
└── logs/                      — run logs
```

---

## How the automation works

Every day at 07:00 Pacific, GitHub's servers:

1. Check out the repo
2. Install pywikibot
3. Write credentials from GitHub Secrets (no passwords stored in code)
4. Run the bot against live WFIGS data
5. If a fire is found → update or insert on Wikipedia
6. If nothing's burning → clean exit, logs it, goes back to sleep

The QGIS GeoJSON layer is refreshed on every run regardless of Wikipedia activity, keeping the live fire map current.

---

## New fire behavior

When WFIGS reports a new fire over **10 acres** in Tuolumne County:

- A stub row is automatically inserted into the Wikipedia table
- Location and notes cells are marked `<!-- bot-stub -->` for manual fill
- Coordinates from WFIGS are included in the stub so you can find the fire fast
- Acreage updates automatically on every subsequent run until contained

---

## Bot compliance

- Operated under [Wikipedia bot policy](https://en.wikipedia.org/wiki/Wikipedia:Bot_policy)
- BRFA filed: [Wikipedia:Bots/Requests for approval/BdgrovesBot](https://en.wikipedia.org/wiki/Wikipedia:Bots/Requests_for_approval/BdgrovesBot)
- `DRY_RUN=True` by default — must explicitly pass `--no-dry-run` to make edits
- Edit summaries always cite WFIGS as data source
- Bot account: [User:BdgrovesBot](https://en.wikipedia.org/wiki/User:BdgrovesBot)

---

## Related projects

- **[@SierraNevadaWX](https://twitter.com/SierraNevadaWX)** — companion Twitter bot for real-time Sierra Nevada fire and weather alerts
- **[bdgroves/QGIS fire monitoring](https://en.wikipedia.org/wiki/User:Bdgroves)** — GIS-based fire perimeter and weather watch tracking in QGIS

---

*Built in Tuolumne County territory. If you can see the smoke from your porch, the bot already knows.*
