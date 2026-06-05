# French Slave Voyages — Interactive Map

An animated web visualization of French slave voyages during the early modern period (1710–1868), focusing on the experience of the enslaved. Ships move across a world map along historically-grounded routes, with a running tally of slaves transported. At key moments the animation pauses to tell the story of a specific ship — one illustrated panel and one sentence at a time.

## Data sources

- **[IOSDB](https://www.slavevoyages.org/voyage/indian-ocean#voyages)** — Indian Ocean Slave Trade Database, filtered to French-flagged vessels
- **[TASTDB](https://www.slavevoyages.org/voyage/trans-atlantic#voyages)** — Trans-Atlantic Slave Trade Database, filtered to French-flagged vessels

Combined: **5,178 French voyages** (941 Indian Ocean, 4,237 Atlantic), spanning 1571–1868.

---

## Repository structure

```
data_processing/
  slavevoyages_dotorg/
    clean_voyages.py       # main ETL: reads CSVs → output.json
    geocode_ports.py       # geocodes port names → ports.json (run once, cached)
    test_routes.py         # verifies no animated routes cross land
    pyproject.toml         # uv dependencies (httpx + shapely, for geocoding/testing)
    slave_voyages_db_indian_ocean.csv
    slave_voyages_db_atlantic.csv
    ports.json             # generated: port name → [lat, lon]
    output.json            # generated: cleaned voyages with coordinates

visualization/
  index.html               # single-page app
  app.js                   # animation engine
  ship.svg                 # ship glyph stamped on canvas
  ship2.svg                # brigantine variant
  ship3.svg                # lateen ketch variant

illustrations/
  stories.json             # story manifest: trigger years, panel texts, image paths
  1696-witch/              # story of The Witch, Gorée 1696
    panel1.png … panel4.png
    story.txt
```

---

## Data pipeline

### 1. Geocoding (`geocode_ports.py`)

Run once with `uv run geocode_ports.py`. Looks up each unique port name via the [Nominatim](https://nominatim.openstreetmap.org/) OpenStreetMap API (1 req/sec), caching results in `ports.json`. Many historical port names (e.g. "Whydah, Ouidah", "Île de France, Mauritius", "Cap Français") are in a hand-curated `OVERRIDES` dict that always takes precedence — Nominatim frequently returns wrong continents for 18th-century names.

### 2. Cleaning (`clean_voyages.py`)

Run with `python3 clean_voyages.py`. Reads both CSVs, filters to French-flagged vessels, extracts the slave-carrying leg of each voyage (purchase port → arrival port), parses the internal `YEAR,MONTH,DAY` date format into ISO strings, injects coordinates from `ports.json`, and writes `output.json`.

Key choices:

- **Slave-carrying leg only**: the outbound leg (home port → purchase location) is dropped; animation starts at the slave purchase location.
- **Partial dates preserved**: year-only and year+month dates are kept rather than nulled, so voyages can still be placed on the timeline.
- **Ocean-aware coordinates**: a few port names (e.g. "Sainte Luce") refer to different places in the Atlantic vs Indian Ocean datasets — handled via `OCEAN_PORT_OVERRIDES` in `clean_voyages.py`.
- **Metadata per voyage**: `slaves_embarked`, `slaves_disembarked`, `crossing_days`, vessel name, bibliographic sources.

### 3. Route testing (`test_routes.py`)

Run with `uv run test_routes.py`. Downloads the Natural Earth 110m land polygon (cached locally), erodes it by 0.25° to avoid false positives at coastlines, then samples each animated route at 80 points and flags any that land inside the eroded polygon. Requires `shapely` and `httpx` (via `uv`).

---

## Visualization

Served with any static file server from the repo root:

```bash
python3 -m http.server 8080
# open http://localhost:8080/visualization/index.html
```

### Libraries (all via CDN, no build step)

- **[Leaflet.js](https://leafletjs.com/) 1.9** — map rendering
- **[ESRI World Physical Map](https://www.esri.com/)** tiles — physical terrain only, no anachronistic country names or borders

### Animation model

Each voyage is a ship icon moving from its purchase port to its arrival port. Time is a decimal year (e.g. 1762.5 = mid-1762), parsed from ISO dates in `output.json`.

**Speed**: configurable. Default is 0.15 yr/s. Slider is centre-weighted: midpoint = 1×, left half → 0.13×, right half → 33×. Speed also adapts automatically — the animation slows during busy periods (many concurrent ships) and speeds up during quiet stretches, using a 7-year rolling average of slaves embarked per year.

**Route interpolation**: great-circle arcs (spherical linear interpolation) with a library of hand-tuned routing waypoints that keep ships in the ocean:

- Gulf of Guinea → Americas: detour south through the equatorial Atlantic to catch the trade winds, then northwest.
- East Africa → Caribbean/Americas: south along the coast, round the Cape of Good Hope, bypass Brazil's northeastern bulge.
- East/west Madagascar ↔ Indian Ocean islands: routed around Madagascar's southern tip, with latitude-aware via points.
- Hispaniola/Cuba arrivals: approach from the north via the Windward Passage.
- Gulf of Mexico arrivals: approach via the Florida Straits.

`slerpPath()` weights each path segment by its angular arc length so ships move at geographically uniform speed regardless of the number of waypoints.

**Ship glyphs**: three SVG variants (full-rigged ship, brigantine, lateen ketch), assigned randomly per voyage and mirrored horizontally for eastward-sailing ships.

**Counters**:

- _Year_ — current animation year, updated every frame.
- _Slaves embarked_ — cumulative, incremented when each voyage's `t_start` is crossed.
- _Per-year histogram_ — drawn on a small canvas panel; past bars in orange, future bars faded, gold cursor line at current year.

**Controls**: Play/Pause (button or spacebar), timeline scrubber, speed slider.

**Hover tooltip**: `document.mousemove` hit-tests against an `activeShips` array (refreshed each draw frame) and shows vessel name, ocean, slave counts, dates, and port-to-port route.

### Story interludes

At trigger years defined in `illustrations/stories.json`, the animation pauses and shows a full-screen illustrated story. Each story is a sequence of panels (image + text). Text is revealed one sentence at a time with a typewriter effect; the layout is fixed from the start (all characters pre-rendered as invisible spans) so already-visible text never shifts as new characters appear.

- **Click or Space**: skip the typewriter on the current sentence, or advance to the next
- **Escape**: dismiss the story and resume the animation immediately
- After the final panel the animation resumes automatically

To add a new story, create a folder under `illustrations/` with panel images and add an entry to `stories.json` with a `triggerYear` and the panel texts.

--

# Attributions

- Ocean Waves Crashing on the Coast of Big Lagoon, Redwoods by CVLTIV8R -- https://freesound.org/s/803679/ -- License: Creative Commons 0
- Ambience music tracks generated with Suno
- Illustrations generated with Gemini (Nano Banana)
- ship sprites generated with Claude
- story narration voice-overs generated with ElevenLabs
