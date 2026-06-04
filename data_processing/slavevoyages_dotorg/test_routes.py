#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["shapely>=2.0", "httpx>=0.27"]
# ///
"""
test_routes.py — verify no animated ship routes pass significantly inland.

Run with:  uv run test_routes.py
"""
import json, math
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import unary_union
import httpx

HERE = Path(__file__).parent
LAND_CACHE = HERE / "ne_110m_land.geojson"
OUTPUT_JSON = HERE / "output.json"
N_SAMPLES = 80       # samples per voyage
EROSION_DEG = 0.25   # degrees inland to ignore — avoids coast false-positives (~25 km)


# ── Geo helpers (mirrors app.js exactly) ──────────────────────────────────

def slerp(lat1, lon1, lat2, lon2, t):
    R = math.pi / 180
    p1, l1, p2, l2 = lat1*R, lon1*R, lat2*R, lon2*R
    x1 = math.cos(p1)*math.cos(l1); y1 = math.cos(p1)*math.sin(l1); z1 = math.sin(p1)
    x2 = math.cos(p2)*math.cos(l2); y2 = math.cos(p2)*math.sin(l2); z2 = math.sin(p2)
    dot = max(-1, min(1, x1*x2 + y1*y2 + z1*z2))
    om = math.acos(dot)
    if om < 1e-6:
        return lat1, lon1
    s0 = math.sin((1-t)*om)/math.sin(om); s1 = math.sin(t*om)/math.sin(om)
    x, y, z = s0*x1+s1*x2, s0*y1+s1*y2, s0*z1+s1*z2
    return math.atan2(z, math.sqrt(x*x+y*y))/R, math.atan2(y, x)/R


def arc_length(p1, p2):
    R = math.pi / 180
    x1 = math.cos(p1[0]*R)*math.cos(p1[1]*R); y1 = math.cos(p1[0]*R)*math.sin(p1[1]*R); z1 = math.sin(p1[0]*R)
    x2 = math.cos(p2[0]*R)*math.cos(p2[1]*R); y2 = math.cos(p2[0]*R)*math.sin(p2[1]*R); z2 = math.sin(p2[0]*R)
    return math.acos(max(-1, min(1, x1*x2 + y1*y2 + z1*z2)))


def slerp_path(path, t):
    n = len(path) - 1
    if n == 1:
        return slerp(path[0][0], path[0][1], path[1][0], path[1][1], t)
    lengths = [arc_length(path[i], path[i+1]) for i in range(n)]
    total = sum(lengths)
    cum = 0.0
    for i in range(n):
        frac = lengths[i] / total
        if t <= cum + frac + 1e-9 or i == n - 1:
            local_t = max(0.0, min(1.0, (t - cum) / frac))
            return slerp(path[i][0], path[i][1], path[i+1][0], path[i+1][1], local_t)
        cum += frac
    return slerp(path[-2][0], path[-2][1], path[-1][0], path[-1][1], 1)


def build_route_path(from_c, to_c, ocean):
    fLat, fLon = from_c
    tLat, tLon = to_c
    needs_hisp = 17 < tLat < 24 and -80 < tLon < -66
    needs_col  = 8  < tLat < 17 and -80 < tLon < -67
    needs_gulf = tLat > 24 and tLon < -82

    if ocean == "atlantic" and tLon < -40:
        if fLon > 30:
            eaf = ([from_c, [fLat, fLon+3], [-20, 43], [-38, 25], [-3, -30]]
                   if fLat > -12 else
                   [from_c, [-28, 43], [-38, 25], [-3, -30]])
            if needs_hisp:  return [*eaf, [21.5, -73.5], to_c]
            if needs_col:   return [*eaf, [14, -76], to_c]
            if needs_gulf:  return [*eaf, [24.5, -82.5], to_c]
            return [*eaf, to_c]
        if fLon > -6:
            via1 = [-5, 5] if fLat > -10 else [-15, -10]
            if needs_hisp:  return [from_c, via1, [21.5, -73.5], to_c]
            if needs_col:   return [from_c, via1, [14, -76], to_c]
            if needs_gulf:  return [from_c, via1, [24.5, -82.5], to_c]
            return [from_c, via1, to_c]
        if needs_hisp:  return [from_c, [21.5, -73.5], to_c]
        if needs_col:   return [from_c, [14, -76], to_c]
        if needs_gulf:  return [from_c, [24.5, -82.5], to_c]

    if ocean == "indian_ocean":
        if fLon < 0 and tLon > 40:
            return [from_c, [-36, 20], to_c]
        if fLon > 70 and fLat > 5 and tLon < 70:
            return [from_c, [8, fLon + 2], to_c]
        if 38 <= fLon < 44 and fLat > -20:
            tz = fLat > -12
            if tLon > 50:
                return ([from_c, [fLat, fLon+3], [-20, 43], [-28, 43], [-32, 55], to_c]
                        if tz else [from_c, [-28, 43], [-32, 55], to_c])
            if abs(tLon - fLon) < 8 and abs(tLat - fLat) < 10:
                return [from_c, to_c]
            return ([from_c, [fLat, fLon+3], [-20, 43], [-38, 25], to_c]
                    if tz else [from_c, [-28, 43], [-38, 25], to_c])
        if fLon < 46 and fLat < -15 and tLon > 50:
            return [from_c, [-28, 43], [-32, 50], to_c]
        if fLon > 52 and tLon < 46:
            return [from_c, [-32, 50], [-28, 43], to_c]
        if 46 <= fLon <= 51 and fLat < -10 and tLon > fLon + 4:
            return [from_c, [fLat - 4, fLon + 2], to_c]
        if 44 <= fLon <= 52 and fLat < -5 and tLon < fLon - 3:
            return [from_c, [-28, 50], [-30, 43], to_c]

    return [from_c, to_c]


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    # Download land polygon once
    if not LAND_CACHE.exists():
        print("Downloading Natural Earth 110m land polygon...")
        url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
        r = httpx.get(url, timeout=30)
        LAND_CACHE.write_bytes(r.content)
        print("  Done.")

    print("Building land mask (eroded by {:.2f}°)...".format(EROSION_DEG))
    with open(LAND_CACHE) as f:
        land_data = json.load(f)
    land = unary_union([shape(feat["geometry"]) for feat in land_data["features"]])
    land_mask = land.buffer(-EROSION_DEG)

    print("Loading voyages...")
    with open(OUTPUT_JSON) as f:
        data = json.load(f)

    issues: dict[tuple, dict] = {}  # keyed by (from_port, to_port, ocean)

    for v in data["voyages"]:
        purchase = next((w for w in v["waypoints"] if w["event"] == "purchase"), None)
        arrival  = next((w for w in v["waypoints"] if w["event"] == "arrival"),  None)
        if not purchase or not arrival:
            continue
        if not purchase.get("coordinates") or not arrival.get("coordinates"):
            continue

        fcoords = purchase["coordinates"]
        tcoords = arrival["coordinates"]
        ocean   = v["ocean"]
        path    = build_route_path(fcoords, tcoords, ocean)

        inland = []
        for i in range(N_SAMPLES + 1):
            t = i / N_SAMPLES
            lat, lon = slerp_path(path, t)
            if land_mask.contains(Point(lon, lat)):
                inland.append((round(t, 3), round(lat, 2), round(lon, 2)))

        if not inland:
            continue

        key = (purchase.get("port", "?"), arrival.get("port", "?"), ocean)
        if key not in issues:
            issues[key] = {
                "from_coords": fcoords,
                "to_coords":   tcoords,
                "path":        path,
                "ocean":       ocean,
                "count":       0,
                "inland":      inland,
                "example":     v.get("vessel", "?"),
            }
        issues[key]["count"] += 1

    if not issues:
        print("\n✅  No inland crossings found!")
        return

    print(f"\n❌  {len(issues)} unique routes with inland crossings ({sum(v['count'] for v in issues.values())} total voyages):\n")
    for (fp, tp, oc), info in sorted(issues.items(), key=lambda x: -x[1]["count"]):
        mid = [p for p in info["inland"] if 0.04 < p[0] < 0.96]
        kind = "ROUTE" if mid else "PORT-EDGE"
        print(f"  [{info['count']:3d}x] [{oc[:7]}] [{kind}] {fp} → {tp}")
        print(f"         from {info['from_coords']}  →  to {info['to_coords']}")
        if len(info['path']) > 2:
            print(f"         via  {info['path'][1:-1]}")
        print(f"         inland at t= {[s[0] for s in info['inland'][:6]]}")
        print(f"         first crossing: lat={info['inland'][0][1]}, lon={info['inland'][0][2]}")
        print(f"         example: {info['example']}")
        print()


if __name__ == "__main__":
    main()
