"""
tuolumne_bot.py — BdgrovesBot
Queries WFIGS for active Tuolumne County fires and:
  1. Updates acreages on the 2026 Tuolumne County wildfires Wikipedia page
  2. Refreshes the QGIS GeoJSON layer file with rich attributes

Usage:
    python bot/tuolumne_bot.py           # dry run (safe, default)
    python bot/tuolumne_bot.py --no-dry-run  # live — actually saves to Wikipedia
"""

import sys
import re
import json
import logging
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
PAGE_NAME  = "2026 Tuolumne County wildfires"
LOG_FILE   = "logs/tuolumne_bot.log"
GEOJSON_OUT = r"C:\data\01_Projects\_QGIS\tuolumne_active_fires.geojson"

# Active fires only — ContainmentDateTime IS NULL means still burning
WFIGS_ACTIVE_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query"
    "?where=" + urllib.parse.quote(
        "attr_POOCounty = 'Tuolumne' "
        "AND attr_POOState = 'US-CA' "
        "AND attr_ContainmentDateTime IS NULL"
    ) +
    "&outFields="
    "attr_IncidentName,"
    "poly_GISAcres,"
    "attr_PercentContained,"
    "attr_FireCauseSpecific,"
    "attr_FireCauseGeneral,"
    "attr_POOJurisdictionalAgency,"
    "attr_POOProtectingAgency,"
    "attr_POOLandownerCategory,"
    "attr_PredominantFuelGroup,"
    "attr_PredominantFuelModel,"
    "attr_FireBehaviorGeneral,"
    "attr_FireBehaviorGeneral1,"
    "attr_FireBehaviorGeneral2,"
    "attr_FireBehaviorGeneral3,"
    "attr_TotalIncidentPersonnel,"
    "attr_EstimatedCostToDate,"
    "attr_IncidentComplexityLevel,"
    "attr_InitialLatitude,"
    "attr_InitialLongitude,"
    "attr_FireDiscoveryDateTime,"
    "attr_ModifiedOnDateTime_dt,"
    "attr_UniqueFireIdentifier,"
    "attr_POOCounty,"
    "attr_POOState,"
    "poly_PolygonDateTime,"
    "poly_MapMethod,"
    "poly_FeatureCategory"
    "&returnGeometry=true&f=geojson"
    "&orderByFields=poly_GISAcres+DESC"
)

# All fires including contained — for QGIS historical layer
WFIGS_ALL_URL = WFIGS_ACTIVE_URL.replace(
    "AND attr_ContainmentDateTime IS NULL", ""
).replace("returnGeometry=true", "returnGeometry=true")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False) if hasattr(sys.stdout, "fileno") else sys.stdout),
    ],
)
log = logging.getLogger("bdgrovesbot.tuolumne")


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_ts(ms):
    if ms:
        try:
            return datetime.fromtimestamp(ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except: pass
    return "—"

def behavior_str(props):
    """Combine behavior sub-fields into readable string."""
    parts = [
        props.get("attr_FireBehaviorGeneral"),
        props.get("attr_FireBehaviorGeneral1"),
        props.get("attr_FireBehaviorGeneral2"),
        props.get("attr_FireBehaviorGeneral3"),
    ]
    return " · ".join(p for p in parts if p) or "—"


# ── WFIGS ─────────────────────────────────────────────────────────────────────
def get_active_fires():
    """Pull active (uncontained) Tuolumne County fires from WFIGS."""
    log.info("Querying WFIGS — active Tuolumne County fires only...")
    try:
        with urllib.request.urlopen(WFIGS_ACTIVE_URL, timeout=15) as r:
            d = json.loads(r.read())
        fires = []
        for f in d.get("features", []):
            p     = f.get("properties", {})
            name  = str(p.get("attr_IncidentName", "")).title().strip()
            acres = round(p.get("poly_GISAcres") or 0, 1)
            pct   = int(p.get("attr_PercentContained") or 0)
            if acres > 0 and name:
                fires.append({
                    "name":        name,
                    "acres":       acres,
                    "pct":         pct,
                    "cause":       p.get("attr_FireCauseSpecific") or p.get("attr_FireCauseGeneral") or "—",
                    "agency":      p.get("attr_POOJurisdictionalAgency") or "—",
                    "fuel":        p.get("attr_PredominantFuelGroup") or "—",
                    "fuel_model":  p.get("attr_PredominantFuelModel") or "—",
                    "behavior":    behavior_str(p),
                    "personnel":   p.get("attr_TotalIncidentPersonnel") or 0,
                    "complexity":  p.get("attr_IncidentComplexityLevel") or "—",
                    "discovered":  fmt_ts(p.get("attr_FireDiscoveryDateTime")),
                    "modified":    fmt_ts(p.get("attr_ModifiedOnDateTime_dt")),
                    "map_method":  p.get("poly_MapMethod") or "—",
                    "uid":         p.get("attr_UniqueFireIdentifier") or "—",
                })
                log.info(
                    f"  {name:<22} {acres:>6} ac  {pct}%  "
                    f"cause={fires[-1]['cause']:<12} agency={fires[-1]['agency']:<6}  "
                    f"fuel={fires[-1]['fuel']}"
                )
        log.info(f"Found {len(fires)} active fire(s)")
        return fires
    except Exception as e:
        log.error(f"WFIGS active query failed: {e}")
        return []


# ── QGIS GeoJSON refresh ──────────────────────────────────────────────────────
def refresh_geojson():
    """Download fresh GeoJSON (all fires) and save for QGIS."""
    log.info(f"Refreshing QGIS GeoJSON -> {GEOJSON_OUT}")
    try:
        # Build all-fires URL (active + contained for full picture)
        url = (
            "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
            "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query"
            "?where=" + urllib.parse.quote(
                "attr_POOCounty = 'Tuolumne' AND attr_POOState = 'US-CA'"
            ) +
            "&outFields="
            "attr_IncidentName,poly_GISAcres,attr_PercentContained,"
            "attr_FireCauseSpecific,attr_FireCauseGeneral,"
            "attr_POOJurisdictionalAgency,attr_PredominantFuelGroup,"
            "attr_PredominantFuelModel,attr_FireBehaviorGeneral,"
            "attr_FireBehaviorGeneral1,attr_FireBehaviorGeneral2,"
            "attr_TotalIncidentPersonnel,attr_EstimatedCostToDate,"
            "attr_IncidentComplexityLevel,attr_FireDiscoveryDateTime,"
            "attr_ContainmentDateTime,attr_FireOutDateTime,"
            "attr_ModifiedOnDateTime_dt,attr_UniqueFireIdentifier,"
            "attr_InitialLatitude,attr_InitialLongitude,"
            "poly_MapMethod,poly_FeatureCategory,poly_PolygonDateTime"
            "&returnGeometry=true&f=geojson"
            "&orderByFields=poly_GISAcres+DESC"
        )
        with urllib.request.urlopen(url, timeout=15) as r:
            gjson = r.read().decode()
        with open(GEOJSON_OUT, 'w') as f:
            f.write(gjson)
        fc = len(json.loads(gjson).get("features", []))
        log.info(f"  OK GeoJSON saved — {fc} feature(s)")
        return True
    except Exception as e:
        log.error(f"GeoJSON refresh failed: {e}")
        return False


# ── Wikipedia ─────────────────────────────────────────────────────────────────
def update_acreage(text, fire_name, new_acres, pct):
    """Find fire row in wikitable and update {{no|X}} or {{yes2|X}}."""
    template = "yes2" if pct >= 100 else "no"
    escaped  = re.escape(fire_name)
    pattern  = (
        rf'(\|{escaped}\s*\n'
        rf'(?:\|[^\n]*\n){{1,3}})'
        rf'\|\{{{{(?:no|yes2)\|[\d,.]+\}}}}'
    )
    repl    = rf'\g<1>|{{{{{template}|{int(new_acres):,}}}}}'
    new_txt, n = re.subn(pattern, repl, text, flags=re.DOTALL | re.IGNORECASE)
    return new_txt, n


# ── Main ──────────────────────────────────────────────────────────────────────
def main(dry_run: bool):
    log.info("=" * 60)
    log.info("BdgrovesBot — Tuolumne County Wildfire Updater")
    log.info(f"Mode: {'DRY RUN (no Wikipedia edits)' if dry_run else '*** LIVE ***'}")
    log.info(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)

    # Always refresh the QGIS GeoJSON regardless of dry/live
    refresh_geojson()

    # Get active fires for Wikipedia
    fires = get_active_fires()

    if not fires:
        log.info("No active Tuolumne County fires — nothing to update on Wikipedia.")
        return

    # Print rich summary
    log.info("\n── Active fire summary ──────────────────────────────────")
    for f in fires:
        log.info(f"  {f['name']}")
        log.info(f"    Acres:      {f['acres']} ac  |  Contained: {f['pct']}%")
        log.info(f"    Cause:      {f['cause']}")
        log.info(f"    Agency:     {f['agency']}  |  Fuel: {f['fuel']} ({f['fuel_model']})")
        log.info(f"    Behavior:   {f['behavior']}")
        log.info(f"    Personnel:  {f['personnel']}  |  Complexity: {f['complexity']}")
        log.info(f"    Discovered: {f['discovered']}")
        log.info(f"    WFIGS ID:   {f['uid']}")
        log.info(f"    Map method: {f['map_method']}")
        log.info("")

    # Wikipedia update
    import pywikibot
    site = pywikibot.Site("en", "wikipedia")
    page = pywikibot.Page(site, PAGE_NAME)

    if not page.exists():
        log.error(f"Wikipedia page not found: {PAGE_NAME}")
        return

    text    = page.text
    changes = []

    for f in fires:
        new_text, n = update_acreage(text, f["name"], f["acres"], f["pct"])
        if n:
            text = new_text
            changes.append(f"{f['name']} -> {int(f['acres']):,} ac")
            log.info(f"  OK Queued Wikipedia update: {f['name']} = {int(f['acres']):,} ac")
        else:
            log.info(f"  — Not in Wikipedia article (manual add needed): {f['name']}")

    if not changes:
        log.info("No Wikipedia acreage changes needed.")
        return

    summary = (
        "Update Tuolumne County fire acreages from WFIGS poly_GISAcres: "
        + "; ".join(changes)
    )
    log.info(f"\nEdit summary: {summary}")

    if dry_run:
        log.info("[DRY RUN] Wikipedia NOT updated. Run --no-dry-run to go live.")
    else:
        page.text = text
        page.save(summary=summary, minor=True, botflag=False)
        log.info("OK Wikipedia page saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="BdgrovesBot — Tuolumne County wildfire updater"
    )
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
