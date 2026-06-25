"""
tuolumne_bot.py — BdgrovesBot
Queries WFIGS for Tuolumne County fires and updates acreages
on the 2026 Tuolumne County wildfires Wikipedia page.

Usage:
    python bot/tuolumne_bot.py           # dry run (safe, default)
    python bot/tuolumne_bot.py --no-dry-run  # live — actually saves
"""

import sys
import re
import json
import logging
import argparse
import urllib.request
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
PAGE_NAME = "2026 Tuolumne County wildfires"
LOG_FILE  = "logs/tuolumne_bot.log"

WFIGS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query"
    "?where=attr_POOCounty+%3D+%27Tuolumne%27"
    "+AND+attr_POOState+%3D+%27US-CA%27"
    "&outFields=attr_IncidentName,poly_GISAcres,"
    "attr_PercentContained,attr_ModifiedOnDateTime_dt"
    "&returnGeometry=false&f=json"
    "&orderByFields=poly_GISAcres+DESC"
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bdgrovesbot.tuolumne")


# ── WFIGS ─────────────────────────────────────────────────────────────────────
def get_wfigs_fires():
    """Pull Tuolumne County fires from WFIGS. Returns list of dicts."""
    log.info("Querying WFIGS for Tuolumne County fires...")
    try:
        with urllib.request.urlopen(WFIGS_URL, timeout=15) as r:
            d = json.loads(r.read())
        fires = []
        for f in d.get("features", []):
            a     = f["attributes"]
            name  = str(a.get("attr_IncidentName", "")).title().strip()
            acres = round(a.get("poly_GISAcres") or 0)
            pct   = int(a.get("attr_PercentContained") or 0)
            if acres > 0 and name:
                fires.append({"name": name, "acres": acres, "pct": pct})
                log.info(f"  {name:<28} {acres:>6,} ac  {pct}% contained")
        log.info(f"WFIGS returned {len(fires)} Tuolumne County fire(s)")
        return fires
    except Exception as e:
        log.error(f"WFIGS query failed: {e}")
        return []


# ── Wikipedia ─────────────────────────────────────────────────────────────────
def update_acreage(text, fire_name, new_acres, pct):
    """
    Find the fire's wikitable row and update {{no|X}} or {{yes2|X}}.
    Returns (new_text, number_of_replacements_made).
    """
    template = "yes2" if pct >= 100 else "no"
    escaped  = re.escape(fire_name)

    # Pattern: fire name cell, then 1-3 more cells, then the acreage template
    pattern = (
        rf'(\|{escaped}\s*\n'
        rf'(?:\|[^\n]*\n){{1,3}})'
        rf'\|\{{{{(?:no|yes2)\|[\d,]+\}}}}'
    )
    repl    = rf'\g<1>|{{{{{template}|{new_acres:,}}}}}'
    new_txt, n = re.subn(pattern, repl, text,
                          flags=re.DOTALL | re.IGNORECASE)
    return new_txt, n


# ── Main ──────────────────────────────────────────────────────────────────────
def main(dry_run: bool):
    log.info("=" * 55)
    log.info(f"BdgrovesBot — Tuolumne County Wildfire Updater")
    log.info(f"Mode: {'DRY RUN (no edits)' if dry_run else '*** LIVE — will save ***'}")
    log.info(f"Time: {datetime.now():%Y-%m-%d %H:%M UTC}")
    log.info("=" * 55)

    import pywikibot
    site = pywikibot.Site("en", "wikipedia")
    page = pywikibot.Page(site, PAGE_NAME)

    if not page.exists():
        log.error(f"Page not found: {PAGE_NAME}")
        return

    text = page.text
    log.info(f"Page loaded: {len(text):,} chars")

    fires   = get_wfigs_fires()
    changes = []

    for f in fires:
        new_text, n = update_acreage(text, f["name"], f["acres"], f["pct"])
        if n:
            text = new_text
            changes.append(f"{f['name']} → {f['acres']:,} ac")
            log.info(f"  ✓ Queued: {f['name']} = {f['acres']:,} ac")
        else:
            log.info(f"  — Not in article (manual add needed): {f['name']}")

    if not changes:
        log.info("No acreage changes needed — all current.")
        return

    summary = (
        "Update Tuolumne County fire acreages from WFIGS poly_GISAcres: "
        + "; ".join(changes)
    )
    log.info(f"Edit summary would be: {summary}")

    if dry_run:
        log.info("")
        log.info("[DRY RUN] Page NOT saved.")
        log.info("Run with --no-dry-run to actually publish changes.")
    else:
        page.text = text
        page.save(summary=summary, minor=True, botflag=False)
        log.info("✓ Page saved to Wikipedia.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="BdgrovesBot — Tuolumne County wildfire acreage updater"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Preview only, no edits (default)"
    )
    parser.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false",
        help="Actually save changes to Wikipedia"
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
