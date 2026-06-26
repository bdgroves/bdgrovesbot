"""
tuolumne_bot.py — BdgrovesBot
Queries WFIGS for active Tuolumne County fires and:
  1. Updates acreages on the 2026 Tuolumne County wildfires Wikipedia page
  2. Inserts stub rows for fires not yet in the table
  3. Refreshes the QGIS GeoJSON layer file with rich attributes

Usage:
    python bot/tuolumne_bot.py               # dry run (safe, default)
    python bot/tuolumne_bot.py --no-dry-run  # live — actually saves to Wikipedia

New-fire stub rows are inserted with <!-- bot-stub --> markers so you can
find and fill in location + notes details manually after the bot adds the row.
Acres and containment are fully automated after the initial stub is placed.
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
PAGE_NAME   = "2026 Tuolumne County wildfires"
LOG_FILE    = "logs/tuolumne_bot.log"
GEOJSON_OUT = r"C:\data\01_Projects\_QGIS\tuolumne_active_fires.geojson"

# Minimum acres threshold to auto-insert a new row.
# Fires under this size are logged but not added (keeps table clean).
MIN_ACRES_FOR_NEW_ROW = 10

# WFIGS — active fires only (ContainmentDateTime IS NULL = still burning)
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
    "attr_ContainmentDateTime,"
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

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(
            open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
            if hasattr(sys.stdout, "fileno") else sys.stdout
        ),
    ],
)
log = logging.getLogger("bdgrovesbot.tuolumne")


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_ts(ms):
    """Unix ms timestamp -> human-readable UTC string."""
    if ms:
        try:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        except Exception:
            pass
    return "—"


def fmt_wiki_date(ms):
    """Unix ms timestamp -> Wikipedia table date format: 'June 2'."""
    if ms:
        try:
            dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            # Drop leading zero: June 2, not June 02
            return dt.strftime("%B %-d") if sys.platform != "win32" else dt.strftime(
                "%B %d"
            ).replace(" 0", " ")
        except Exception:
            pass
    return "—"


def behavior_str(props):
    """Combine fire behavior sub-fields into a readable string."""
    parts = [
        props.get("attr_FireBehaviorGeneral"),
        props.get("attr_FireBehaviorGeneral1"),
        props.get("attr_FireBehaviorGeneral2"),
        props.get("attr_FireBehaviorGeneral3"),
    ]
    return " · ".join(p for p in parts if p) or "—"


def get_existing_fire_names(text):
    """
    Return a set of fire names already present in the wikitable.
    Matches the first pipe-cell of every table row: lines like '| FireName'
    that appear after a '|-' row separator.
    """
    names = set()
    # Each data row starts with |- then | CellOne || CellTwo ...
    # We capture the very first cell content (the fire name column).
    for m in re.finditer(r'^\|\s*([A-Za-z][^\|\n\[<{]+?)\s*\|\|', text, re.MULTILINE):
        names.add(m.group(1).strip())
    return names


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
                lat = p.get("attr_InitialLatitude")
                lon = p.get("attr_InitialLongitude")
                fires.append({
                    "name":        name,
                    "acres":       acres,
                    "pct":         pct,
                    "cause":       (
                        p.get("attr_FireCauseSpecific")
                        or p.get("attr_FireCauseGeneral")
                        or "—"
                    ),
                    "agency":      p.get("attr_POOJurisdictionalAgency") or "—",
                    "fuel":        p.get("attr_PredominantFuelGroup") or "—",
                    "fuel_model":  p.get("attr_PredominantFuelModel") or "—",
                    "behavior":    behavior_str(p),
                    "personnel":   p.get("attr_TotalIncidentPersonnel") or 0,
                    "complexity":  p.get("attr_IncidentComplexityLevel") or "—",
                    "discovered_ms": p.get("attr_FireDiscoveryDateTime"),
                    "discovered":  fmt_ts(p.get("attr_FireDiscoveryDateTime")),
                    "start_date":  fmt_wiki_date(p.get("attr_FireDiscoveryDateTime")),
                    "contained_ms": p.get("attr_ContainmentDateTime"),
                    "containment_date": fmt_wiki_date(p.get("attr_ContainmentDateTime")),
                    "modified":    fmt_ts(p.get("attr_ModifiedOnDateTime_dt")),
                    "map_method":  p.get("poly_MapMethod") or "—",
                    "uid":         p.get("attr_UniqueFireIdentifier") or "—",
                    "lat":         lat,
                    "lon":         lon,
                })
                log.info(
                    f"  {name:<22} {acres:>8} ac  {pct}%  "
                    f"cause={fires[-1]['cause']:<14}  "
                    f"start={fires[-1]['start_date']}"
                )
        log.info(f"Found {len(fires)} active fire(s)")
        return fires
    except Exception as e:
        log.error(f"WFIGS active query failed: {e}")
        return []


# ── QGIS GeoJSON refresh ──────────────────────────────────────────────────────
def refresh_geojson():
    """Download fresh GeoJSON (all fires, active + contained) and save for QGIS."""
    log.info(f"Refreshing QGIS GeoJSON -> {GEOJSON_OUT}")
    try:
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
        with open(GEOJSON_OUT, "w") as fh:
            fh.write(gjson)
        fc = len(json.loads(gjson).get("features", []))
        log.info(f"  OK GeoJSON saved — {fc} feature(s)")
        return True
    except Exception as e:
        log.error(f"GeoJSON refresh failed: {e}")
        return False


# ── Wikipedia table logic ─────────────────────────────────────────────────────
def update_acreage(text, fire_name, new_acres, pct):
    """
    Find an existing fire row and update its acres cell.
    Table uses {{no|X}} for active fires, {{yes2|X}} for fully contained.
    Returns (new_text, number_of_substitutions).
    """
    template = "yes2" if pct >= 100 else "no"
    escaped  = re.escape(fire_name)
    # Match the row opening (name cell) then skip 1-3 cells to reach acres
    pattern = (
        rf'(\|\s*{escaped}\s*\n'
        rf'(?:\|[^\n]*\n){{1,3}})'
        rf'\|\{{{{(?:no|yes2)\|[\d,.]+\}}}}'
    )
    repl = rf'\g<1>|{{{{{template}|{int(new_acres):,}}}}}'
    new_txt, n = re.subn(pattern, repl, text, flags=re.DOTALL | re.IGNORECASE)
    return new_txt, n


def build_new_row(fire):
    """
    Build a wikitext table row for a fire not yet in the article.

    Location and Notes are stubbed with HTML comments — fill these in manually
    after the bot adds the row. Everything else is auto-populated from WFIGS.

    Cause note for stub: included in the Notes stub so editors know what to fill.
    """
    name        = fire["name"]
    acres       = int(fire["acres"])
    start_date  = fire["start_date"]
    containment = fire["containment_date"] if fire.get("contained_ms") else ""
    cause       = fire["cause"]
    lat         = fire.get("lat")
    lon         = fire.get("lon")
    uid         = fire["uid"]

    # Location stub: include coords if available so editor can look it up
    if lat and lon:
        loc_stub = (
            f"<!-- bot-stub: fill location. "
            f"Coords: {lat:.4f}, {lon:.4f} -->"
        )
    else:
        loc_stub = "<!-- bot-stub: fill location -->"

    # Notes stub: pre-fill cause if known, leave rest for editor
    if cause and cause != "—":
        cause_note = f"Cause: {cause}."
    else:
        cause_note = "Cause under investigation."
    notes_stub = f"{cause_note} <!-- bot-stub: add details -->"

    # Acres cell: {{no|X}} while active (bot will update this each run)
    acres_cell = f"{{{{no|{acres:,}}}}}"

    # References: stub — editor should add a proper CAL FIRE or WFIGS ref
    ref_stub = (
        f"<!-- bot-stub: add ref. WFIGS ID: {uid} -->"
    )

    row = (
        "|-\n"
        f"| {name}\n"
        f"| {loc_stub}\n"
        f"| {acres_cell}\n"
        f"| {start_date}\n"
        f"| {containment}\n"
        f"| {notes_stub}\n"
        f"| {ref_stub}\n"
    )
    return row


def insert_new_row(text, fire):
    """
    Insert a new fire row immediately before the closing |} of the wildfires
    wikitable. Returns (new_text, True) on success or (text, False) if the
    table closing marker wasn't found.
    """
    row = build_new_row(fire)

    # Find the closing |} of the fires table (first one after the table header)
    # Use a pattern that matches |} on its own line
    pattern = r'(\|\})'
    # We want the FIRST |} after the wikitable header for our fires list.
    # The page has only one table, so first match is safe.
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        log.error("  Could not find table closing |} — row not inserted")
        return text, False

    insert_pos = m.start()
    new_text = text[:insert_pos] + row + text[insert_pos:]
    return new_text, True


# ── Main ──────────────────────────────────────────────────────────────────────
def main(dry_run: bool):
    log.info("=" * 60)
    log.info("BdgrovesBot — Tuolumne County Wildfire Updater")
    log.info(f"Mode: {'DRY RUN (no Wikipedia edits)' if dry_run else '*** LIVE ***'}")
    log.info(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)

    # Always refresh QGIS GeoJSON regardless of dry/live mode
    refresh_geojson()

    fires = get_active_fires()

    if not fires:
        log.info("No active Tuolumne County fires — nothing to update on Wikipedia.")
        return

    # Rich console summary
    log.info("\n── Active fire summary ─────────────────────────────────────")
    for f in fires:
        log.info(f"  {f['name']}")
        log.info(f"    Acres:      {f['acres']} ac  |  Contained: {f['pct']}%")
        log.info(f"    Cause:      {f['cause']}")
        log.info(f"    Agency:     {f['agency']}  |  Fuel: {f['fuel']} ({f['fuel_model']})")
        log.info(f"    Behavior:   {f['behavior']}")
        log.info(f"    Personnel:  {f['personnel']}  |  Complexity: {f['complexity']}")
        log.info(f"    Discovered: {f['discovered']}  (wiki date: {f['start_date']})")
        log.info(f"    WFIGS ID:   {f['uid']}")
        log.info(f"    Map method: {f['map_method']}")
        if f.get("lat"):
            log.info(f"    Coords:     {f['lat']:.4f}, {f['lon']:.4f}")
        log.info("")

    # Wikipedia
    import pywikibot
    site = pywikibot.Site("en", "wikipedia")
    page = pywikibot.Page(site, PAGE_NAME)

    if not page.exists():
        log.error(f"Wikipedia page not found: {PAGE_NAME}")
        return

    text = page.text

    # What fires are already in the table?
    existing = get_existing_fire_names(text)
    log.info(f"Fires currently in article: {existing or '(none)'}")

    acreage_changes = []
    new_rows        = []

    for f in fires:
        name = f["name"]

        if name in existing:
            # ── Fire already has a row: update acres ──────────────────────────
            new_text, n = update_acreage(text, name, f["acres"], f["pct"])
            if n:
                text = new_text
                acreage_changes.append(f"{name} → {int(f['acres']):,} ac")
                log.info(f"  OK Updated acreage: {name} = {int(f['acres']):,} ac")
            else:
                log.warning(
                    f"  ⚠ {name} found in article text but acres cell regex "
                    f"didn't match — check table format"
                )
        else:
            # ── New fire: insert stub row if large enough ─────────────────────
            if f["acres"] < MIN_ACRES_FOR_NEW_ROW:
                log.info(
                    f"  — Skipping new row for {name} "
                    f"({f['acres']} ac < {MIN_ACRES_FOR_NEW_ROW} ac threshold)"
                )
                continue

            new_text, ok = insert_new_row(text, f)
            if ok:
                text = new_text
                new_rows.append(f"{name} ({int(f['acres']):,} ac)")
                log.info(
                    f"  ++ Inserted stub row: {name} "
                    f"({int(f['acres']):,} ac, start {f['start_date']})"
                )
                log.info(
                    f"     ↳ Location + notes need manual fill "
                    f"(search '<!-- bot-stub' on the page)"
                )
            else:
                log.error(f"  ✗ Failed to insert row for {name}")

    # Build edit summary
    parts = []
    if acreage_changes:
        parts.append("Update acreage: " + "; ".join(acreage_changes))
    if new_rows:
        parts.append("Add stub rows: " + "; ".join(new_rows))

    if not parts:
        log.info("No Wikipedia changes needed.")
        return

    summary = (
        "[[Wikipedia:Bots/Requests for approval/BdgrovesBot|BdgrovesBot]]: "
        + " | ".join(parts)
        + " (data: WFIGS poly_GISAcres)"
    )
    log.info(f"\nEdit summary: {summary}")

    if dry_run:
        log.info("[DRY RUN] Wikipedia NOT saved. Run --no-dry-run to go live.")
        if new_rows:
            log.info("\n── Preview of new row(s) that would be inserted: ───────────")
            for f in fires:
                if f["name"] in [r.split(" (")[0] for r in new_rows]:
                    log.info(build_new_row(f))
    else:
        page.text = text
        page.save(summary=summary, minor=False, botflag=False)
        log.info("OK Wikipedia page saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="BdgrovesBot — Tuolumne County wildfire updater"
    )
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
