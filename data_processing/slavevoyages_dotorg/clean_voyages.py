#!/usr/bin/env python3
"""
Extract French slave voyages from CSVs downloaded from
https://www.slavevoyages.org/voyage/indian-ocean#voyages
and
https://www.slavevoyages.org/voyage/trans-atlantic#voyages
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
PORTS_JSON = HERE / "ports.json"

SOURCES = [
    {"input": HERE / "slave_voyages_db_indian_ocean.csv", "label": "indian_ocean"},
    {"input": HERE / "slave_voyages_db_atlantic.csv", "label": "atlantic"},
]
OUTPUT = HERE / "output.json"


def parse_date(raw):
    """'YEAR,MONTH,DAY' quoted field → ISO string or None."""
    if not raw or raw.replace(",", "").strip() == "":
        return None
    parts = [p.strip() for p in raw.split(",")]
    year = parts[0] if len(parts) > 0 else ""
    month = parts[1] if len(parts) > 1 else ""
    day = parts[2] if len(parts) > 2 else ""
    if not year:
        return None
    try:
        if month and day:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        elif month:
            return f"{int(year):04d}-{int(month):02d}"
        else:
            return year
    except ValueError:
        return None


def clean_port(val):
    """Return None for missing/placeholder port values."""
    if not val or val.strip() in ("", "0", "None", "nan"):
        return None
    return val.strip()


def clean_count(val):
    """Return int or None for slave count fields."""
    if not val or val.strip() in ("", "nan"):
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def clean_sources(val):
    """Return None if empty/nan, otherwise strip whitespace."""
    if not val or val.strip() in ("", "nan"):
        return None
    return val.strip()


# Some port names appear in both Atlantic and Indian Ocean datasets but refer to
# different locations. Override coordinates based on ocean context.
OCEAN_PORT_OVERRIDES: dict[tuple[str, str], list[float]] = {
    ("indian_ocean", "Sainte Luce"):  [-24.7, 47.2],   # Sainte-Luce Bay, SE Madagascar
    ("indian_ocean", "Pointe Larée"): [-14.9, 47.9],   # Pointe Larée, NW Madagascar
}


def get_coords(port_name: str, ocean: str, ports: dict) -> list[float] | None:
    key = (ocean, port_name)
    if key in OCEAN_PORT_OVERRIDES:
        return OCEAN_PORT_OVERRIDES[key]
    return ports.get(port_name)


def make_waypoints(row, ports, ocean):
    """Waypoints covering only the slave-carrying portion: purchase → arrival."""
    purch_port = clean_port(row["Imputed principal place of captive purchase"])
    purch_date = parse_date(row["Date purchase of captives began"])
    africa_depart = parse_date(row["Date vessel departed Africa"])

    arr_port = clean_port(row["Imputed principal port of captive disembarkation"])
    arr_date = parse_date(row["Date first disembarkation of captives"])

    waypoints = []

    if purch_port or purch_date:
        wp = {"event": "purchase", "port": purch_port, "date": purch_date}
        if africa_depart:
            wp["departed_date"] = africa_depart
        if purch_port:
            wp["coordinates"] = get_coords(purch_port, ocean, ports)
        waypoints.append(wp)

    if arr_port or arr_date:
        wp = {"event": "arrival", "port": arr_port, "date": arr_date}
        if arr_port:
            wp["coordinates"] = get_coords(arr_port, ocean, ports)
        waypoints.append(wp)

    return waypoints


def load_voyages(input_path, label, ports):
    with open(input_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    voyages = []
    for r in rows:
        if r["Flag of vessel (IMP)"] != "France":
            continue
        waypoints = make_waypoints(r, ports, label)
        crossing_days = clean_count(r["Duration of captives' crossing (in days)"])
        voyages.append(
            {
                "voyage_id": r["Voyage ID"].strip(),
                "vessel": r["Name of vessel"].strip() or None,
                "ocean": label,
                "slaves_embarked": clean_count(r["Total embarked (IMP)"]),
                "slaves_disembarked": clean_count(r["Total disembarked (IMP)"]),
                "crossing_days": crossing_days,
                "sources": clean_sources(r["Sources"]),
                "waypoints": waypoints,
            }
        )
    return voyages


def main():
    ports: dict = {}
    if PORTS_JSON.exists():
        with open(PORTS_JSON, encoding="utf-8") as f:
            ports = json.load(f)

    all_voyages = []
    for src in SOURCES:
        voyages = load_voyages(src["input"], src["label"], ports)
        print(f"[{src['label']}] {len(voyages)} French voyages")
        all_voyages.extend(voyages)

    def sort_key(v):
        for wp in v["waypoints"]:
            if wp["date"]:
                return wp["date"]
        return "9999"

    all_voyages.sort(key=sort_key)

    all_years = [
        int(wp["date"][:4])
        for v in all_voyages
        for wp in v["waypoints"]
        if wp["date"]
    ]
    voyages_with_full_route = sum(
        1
        for v in all_voyages
        if any(wp["event"] == "purchase" and wp["port"] for wp in v["waypoints"])
        and any(wp["event"] == "arrival" and wp["port"] for wp in v["waypoints"])
    )

    total_embarked = sum(v["slaves_embarked"] for v in all_voyages if v["slaves_embarked"])
    total_disembarked = sum(v["slaves_disembarked"] for v in all_voyages if v["slaves_disembarked"])

    output = {
        "meta": {
            "total_voyages": len(all_voyages),
            "voyages_with_full_route": voyages_with_full_route,
            "total_slaves_embarked": total_embarked,
            "total_slaves_disembarked": total_disembarked,
            "date_range": (
                [str(min(all_years)), str(max(all_years))] if all_years else []
            ),
        },
        "voyages": all_voyages,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(all_voyages)} total voyages to {OUTPUT.name}")
    print(f"  Voyages with full route: {voyages_with_full_route}")
    if all_years:
        print(f"  Date range: {min(all_years)}–{max(all_years)}")


if __name__ == "__main__":
    main()
