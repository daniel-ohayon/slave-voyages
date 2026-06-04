#!/usr/bin/env python3
"""
geocode_ports.py — look up lat/lon for every unique port in output.json
Output: ports.json  { "port name": [lat, lon] or null }

Run with:  uv run geocode_ports.py
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///

import json
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
OUTPUT_JSON = HERE / "output.json"
PORTS_JSON = HERE / "ports.json"

# Historical port names that Nominatim won't resolve reliably.
# [lat, lon] in decimal degrees.
OVERRIDES: dict[str, list[float] | None] = {
    "Africa, port unspecified": None,
    "Africa port unspecified": None,
    "Americas port unspecified": None,
    "Americas region unspecified": None,
    "Caribbean (colony unspecified)": None,
    "British Caribbean colony unspecified": None,
    "French Caribbean colony unspecified": None,
    "Spanish Circum-Caribbean,unspecified": None,
    "Southeast Africa and Indian Ocean islands port unspecified": None,
    "East Africa port unspecified": None,
    "West Central Africa and St Helena port unspecified": None,
    "Senegambia and offshore Atlantic port unspecified": None,
    "Bight of Biafra and Gulf of Guinea Islands port unspecified": None,
    "Gold Coast port unspecified": None,
    "Windward Coast place unspecified": None,
    "South Asia port unspecified": None,
    "Southeast Asia port unspecified": None,
    "Malabar Coast port unspecified": None,
    "Red Sea and Gulf of Aden port unspecified": None,
    "Seychelles port unspecified": None,
    "Java port unspecified": None,
    "Saint-Domingue then Haiti port unspecified": [18.9712, -72.2852],
    "Ile de France, Mauritius": [-20.2789, 57.5546],
    "Ile de France Mauritius": [-20.2789, 57.5546],
    "Bourbon Reunion": [-21.1151, 55.5364],
    "Whydah Ouidah": [6.3649, 2.0834],
    "Foulpointe, Mahavelona": [-17.6928, 49.5111],
    "Foulpointe Mahavelona": [-17.6928, 49.5111],
    "Johanna Island Anjouan Nzwani": [-12.2108, 44.4256],
    "Sainte Marie St Mary's Island": [-16.8667, 49.9167],
    "St Lawrence Madagascar": [-23.3667, 43.7167],
    "Fort Dauphin": [-25.0333, 46.9833],
    "Port Dauphin Fort Dauphin": [-25.0333, 46.9833],
    "Antongil Bay": [-15.5, 49.8333],
    "Bombetoc; Bombetoka; Mahajanga; Majunga": [-15.7167, 46.3167],
    "Farantangane Farafangana": [-22.8167, 47.8333],
    "Fénérive Fenoarivo": [-17.3833, 49.4167],
    "Manazary; Manajary": [-21.2333, 48.35],
    "Masabe Massaby": [-22.3, 43.4667],
    "Massalege; Massaliege; Massaly; Magelage; Mazalagem": [-14.85, 40.75],
    "Tamatave Toamasina": [-18.1603, 49.4027],
    "Morondava Morondova": [-20.2833, 44.3167],
    "Gold Coast Fr definition": [5.5557, -0.1969],
    "Gold Coast + Bight of Benin + Bight of Biafra": [5.5557, -0.1969],
    "Windward + Ivory + Gold + Benin": [4.9, -4.8],   # offshore Ivory Coast coast
    "Costa da Mina place unspecified": [5.354, -4.0083],
    "Bight of Benin place unspecified": [6.3649, 2.0834],
    "Bights": [4.0, 3.0],
    "Congo North": [-4.0, 11.8633],
    "Congo River": [-4.3265, 15.3277],
    "Rio de Janeiro Sao Paulo Santa Catarina": [-22.9068, -43.1729],
    "Rio de la Plata port unspecified": [-34.6037, -58.3816],
    "Princes Island and Cape Lopez": [1.5167, 9.5500],
    "Princes Island": [1.5167, 7.3833],
    "Cape Grand Mount": [6.65, -11.5333],
    "Cape Mount (Cape Grand Mount)": [6.65, -11.5333],
    "Côte de Malaguette (runs through to Cape Palmas on Windward Coast)": [4.375, -7.7167],
    "Martinique place unspecified": [14.6415, -61.0242],
    "Martinique, place unspecified": [14.6415, -61.0242],
    "Guadeloupe place unspecified": [16.265, -61.551],
    "Barbados place unspecified": [13.1939, -59.5432],
    "Antigua place unspecified": [17.0747, -61.8175],
    "Dominica place unspecified": [15.415, -61.371],
    "Grenada place unspecified": [12.1165, -61.679],
    "Jamaica place unspecified": [18.5, -77.3],      # offshore north Jamaica coast
    "Saint John (Antigua)": [17.1274, -61.8468],
    "Cuba port unspecified": [23.2, -80.5],           # Florida Straits north of Cuba
    "Cuba south coast": [21.0, -79.5],                # open Caribbean south of Cuba
    "Bahamas port unspecified": [25.0343, -77.3963],
    "Puerto Rico port unspecified": [18.2208, -66.5901],
    "St Kitts port unspecified": [17.3578, -62.7830],
    "St Lucia port unspecified": [13.9094, -60.9789],
    "St Barthélemy port unspecified": [17.8975, -62.8514],
    "St Croix": [17.7306, -64.7340],
    "Suriname place unspecified": [3.9193, -56.0278],
    "Bahia place unspecified": [-12.9714, -38.5014],
    "Pernambuco place unspecified": [-8.0476, -34.877],
    "French Africa (Goree or Senegal)": [14.6928, -17.4467],
    "French Africa (Goree or Senegal) ": [14.6928, -17.4467],
    "Gustavia St Barthélemy": [17.8975, -62.8514],
    "Angola (possibly New Calabar)": [-8.8369, 13.2894],
    "Angola to Ardra": [-8.8369, 13.2894],
    "Angossy Bay Angontsy": [-13.3833, 49.8833],
    "Mongale": [-4.2500, 15.2833],
    "Maningare; Manningare": [-16.25, 49.7],
    "Mangally": [-21.75, 43.3833],
    "Bonnivoul": [-15.6167, 46.2167],
    "Mogincual": [-16.0333, 39.8500],
    "Oibo": [4.0, 6.5],
    "Pointe Larée": [16.265, -61.551],
    "Louisiana": [30.9843, -91.9623],
    "Liberia": [6.4281, -9.4295],
    "Berbice": [6.1, -57.3167],
    "Mascarene Islands": [-20.2789, 57.5546],
    "France place unspecified": [46.2276, 2.2137],
    "Joal or Saloum River": [14.1667, -16.8333],
    "Joal, or Saloum River": [14.1667, -16.8333],
    "Amokou": [6.2, 1.6],
    "Apammin": [5.0, -1.6],   # offshore Ghana coast
    # East African / Indian Ocean ports — corrected to coastal positions
    "Mozambique": [-15.036, 40.733],   # Ilha de Moçambique (the island port), not Tete inland
    "Inhambane": [-23.865, 35.383],    # Coastal Inhambane, not inland Zimbabwe border
    "Madagascar": [-18.155, 49.415],   # Tamatave/Toamasina east coast (not country center inland)
    # Corrections for wrong Nominatim results
    "Ardra": [6.275, 2.090],           # Slaves from Ardra kingdom were shipped via Whydah beach; city is 30km inland
    "Cap Français": [19.758, -72.204], # Cap-Haïtien, Haiti (not Indian Ocean)
    "Benin": [6.20, 2.50],             # Bight of Benin coast (Nominatim gave country center, very inland)
    "Bengal": [23.685, 90.356],        # South Asia (not Indiana, USA)
    "Boina": [-15.717, 46.317],        # Boina Bay, Madagascar (not Serbia)
    "Cabanas": [22.982, -82.955],      # Cabanas, Cuba (not France)
    "Cartagena": [10.391, -75.479],    # Cartagena, Colombia (not Spain)
    "Cess": [5.467, -9.600],           # River Cess, Liberia (not England)
    "Chama": [5.0, -1.75],             # Komenda/Chama area, Ghana (not New Mexico)
    "Christiansborg": [5.548, -0.185], # Christiansborg Castle, Accra, Ghana (not Denmark)
    "Coringa": [16.806, 82.234],       # Coringa, Andhra Pradesh, India (not Australia)
    "Epe": [6.617, 3.975],             # Epe, Lagos State, Nigeria (not Netherlands)
    "Galam": [14.5, -11.5],            # Galam, Senegal/Mali area (not Indonesia)
    "Gallinhas": [7.533, -11.717],     # Gallinas River, Sierra Leone
    "Grand Junk": [5.0, -9.5],         # Grand Junk, Liberia coast (not Alsace)
    "Jacquin": [6.358, 1.975],         # Jakin (Jacquin), Benin (not Italy)
    "La Balise": [29.0, -89.5],        # La Balise, Mississippi Delta (not Brittany)
    "Lagos, Onim": [6.455, 3.396],     # Lagos, Nigeria
    "Little Popo": [6.238, 1.613],     # Aneho (Little Popo), Togo (not Wyoming)
    "Lindi": [-10.005, 39.708],        # Lindi, Tanzania
    "Lourenço Marques": [-25.966, 32.573], # Maputo, Mozambique (not Brazil)
    "Margarita": [11.0, -64.0],        # Margarita Island, Venezuela (not Italy)
    "New Calabar": [4.642, 7.003],     # New Calabar, Nigeria (not Wales)
    "Popo": [6.276, 1.807],            # Grand Popo / Popo area, Benin (not Indonesia)
    "Quilimane": [-17.879, 36.888],    # Quelimane, Mozambique
    "Rio Nun": [4.5, 6.0],             # Niger Delta, Nigeria (not Brazil)
    "Sagua": [22.812, -80.072],        # Sagua la Grande, Cuba (not Philippines)
    "Saint-Louis": [16.018, -16.490],  # Saint-Louis, Senegal (not Missouri)
    "Saint-Marc": [19.116, -72.697],   # Saint-Marc, Haiti (not France)
    "Saint-Pierre": [14.741, -61.179], # Saint-Pierre, Martinique (not Alsace)
    "Sainte Luce": [14.478, -60.898],  # Sainte-Luce, Martinique (not French Alps)
    "Sainte Marie, St Mary's Island": [-16.867, 49.917], # Île Sainte-Marie, Madagascar (not Ontario)
    "Sierra Leone estuary": [8.5, -13.2],
    "St Paul": [-21.009, 55.270],      # Saint-Paul, Réunion (not Minnesota)
    "St Thomas": [18.343, -64.930],    # St. Thomas, USVI (not France)
    "Bassa": [5.9, -9.8],              # Bassa Coast, Liberia (not Italy)
    "Formosa": None,
    "Eva": None,
    "Saint-Domingue, then Haiti, port unspecified": [18.971, -72.285],

    # ── Comma-variant names ────────────────────────────────────────────────
    # The slavevoyages.org database stores port names with commas (e.g.
    # "Whydah, Ouidah") but earlier OVERRIDES were keyed without commas.
    # Adding all comma variants here so ports.json covers both forms.
    "Whydah, Ouidah":                        [6.275,   2.090],    # beach/slave port, not city center (9km inland)
    "Gold Coast, Fr definition":             [5.5557, -0.1969],
    "Angossy Bay, Angontsy":                 [-13.3833, 49.8833],
    "Farantangane, Farafangana":             [-22.8167, 47.8333],
    "Morondava, Morondova":                  [-20.2833, 44.3167],
    "Masabe, Massaby":                       [-22.3,   43.4667],
    "Guadeloupe, place unspecified":         [16.265,  -61.551],
    "Bahia, place unspecified":              [-12.9714,-38.5014],
    "Barbados, place unspecified":           [13.1939, -59.5432],
    "Antigua, place unspecified":            [17.0747, -61.8175],
    "Dominica, place unspecified":           [15.415,  -61.371],
    "Grenada, place unspecified":            [12.1165, -61.679],
    "Jamaica, place unspecified":            [18.5,  -77.3],     # offshore north Jamaica
    "Cuba, port unspecified":               [23.2,  -80.5],     # Florida Straits
    "Cuba, south coast":                    [21.0,  -79.5],
    "Bahamas, port unspecified":             [25.0343, -77.3963],
    "Puerto Rico, port unspecified":         [18.2208, -66.5901],
    "St Kitts, port unspecified":            [17.3578, -62.783],
    "St Lucia, port unspecified":            [13.9094, -60.9789],
    "St Barthélemy, port unspecified":       [17.8975, -62.8514],
    "Suriname, place unspecified":           [3.9193,  -56.0278],
    "Bahia, place unspecified":              [-12.9714,-38.5014],
    "Pernambuco, place unspecified":         [-8.0476, -34.877],
    "Rio de la Plata, port unspecified":     [-34.6037,-58.3816],
    "St Lawrence, Madagascar":               [-23.3667, 43.7167],
    "Momboza or Zanzibar":                   [-6.17,   39.19],
    "Joal, or Saloum River":                 [14.1667, -16.8333],
    "Americas, port unspecified":            None,
    "Americas, region unspecified":          None,

    # ── Previously-null regional ports — approximate coastal coordinates ──
    "Whydah Ouidah":                         [6.275,   2.090],    # beach/slave port, not city center
    "Gold Coast, port unspecified":          [5.5,    -0.5],
    "Gold Coast port unspecified":           [5.5,    -0.5],
    "Windward Coast, place unspecified":     [5.0,    -7.5],
    "Windward Coast place unspecified":      [5.0,    -7.5],
    "Bight of Benin, place unspecified":     [6.275,   2.090],   # Whydah coast area
    "Bight of Biafra and Gulf of Guinea Islands, port unspecified": [4.0, 8.0],
    "Bight of Biafra and Gulf of Guinea Islands port unspecified":  [4.0, 8.0],
    "Senegambia and offshore Atlantic, port unspecified": [13.5,  -17.0],
    "Senegambia and offshore Atlantic port unspecified":  [13.5,  -17.0],
    "West Central Africa and St Helena, port unspecified": [-5.0,  12.0],
    "West Central Africa and St Helena port unspecified":  [-5.0,  12.0],
    "East Africa, port unspecified":         [-2.0,    42.0],
    "East Africa port unspecified":          [-2.0,    42.0],
    "Southeast Africa and Indian Ocean islands, port unspecified": [-15.0, 44.0],
    "Southeast Africa and Indian Ocean islands port unspecified":  [-15.0, 44.0],
    "French Caribbean, colony unspecified":  [15.0,   -61.5],
    "French Caribbean colony unspecified":   [15.0,   -61.5],
    "British Caribbean, colony unspecified": [17.0,   -62.5],
    "British Caribbean colony unspecified":  [17.0,   -62.5],
    "Caribbean (colony unspecified)":        [17.0,   -63.0],
    "Spanish Circum-Caribbean, unspecified": [17.0,   -66.0],
    "Spanish Circum-Caribbean,unspecified":  [17.0,   -66.0],
    "Seychelles, port unspecified":          [-4.68,   55.49],
    "Seychelles port unspecified":           [-4.68,   55.49],
    "Sierra Leone, port unspecified":        [8.49,   -13.23],
    "Sierra Leone port unspecified":         [8.49,   -13.23],
    "Malabar Coast, port unspecified":       [10.5,    76.0],
    "Malabar Coast port unspecified":        [10.5,    76.0],
    "South Asia, port unspecified":          [15.0,    74.0],
    "South Asia port unspecified":           [15.0,    74.0],
    "Southeast Asia, port unspecified":      [5.0,    110.0],
    "Southeast Asia port unspecified":       [5.0,    110.0],
    "Java, port unspecified":                [-7.0,   110.5],
    "Java port unspecified":                 [-7.0,   110.5],
    "Red Sea and Gulf of Aden, port unspecified": [12.0, 44.0],
    "Red Sea and Gulf of Aden port unspecified":  [12.0, 44.0],
    "Montserrat, port unspecified":          [16.7425,-62.1878],
    "Montserrat port unspecified":           [16.7425,-62.1878],
    "St Barthélemy, port unspecified":       [17.8975,-62.8514],
    "France, place unspecified":             [46.2276,  2.2137],

    # ── New specific ports (not previously in overrides) ──────────────────
    "Bance/Bunce Island":                    [8.43,   -12.97],
    "Cape Lahou":                            [5.15,    -5.02],
    "Grand Mesurado":                        [6.31,   -10.81],
    "Grand Sestos":                          [4.68,    -8.45],
    "Petit Mesurado":                        [6.3,    -10.8],
    "Kormantine":                            [5.28,    -1.08],
    "Rio Dande (N of Luanda)":               [-8.46,   13.39],
    "Saint Augustine's Bay; St Augustin Bay": [-23.55, 43.75],
    "Tulia, Tulear":                         [-23.35,  43.67],
    "Bimilipatam":                           [17.89,   83.45],
    "Portuguese Guinea":                     [11.86,  -15.58],

    # ── Regional centers corrected to coastlines ──────────────────────────
    "Ivory Coast":  [5.35,   -4.0],    # Abidjan coast, not country center
    "Liberia":      [6.3,   -10.8],    # Monrovia coast, not country center
    "Gabon":        [-0.6,    9.0],    # offshore Libreville (previous coords were inland)
    "Senegal":      [14.7,  -17.4],    # Saint-Louis/Dakar coast, not country center

    # ── Ports moved offshore (were flagged as inland by land mask) ─────────
    "Cabinda":      [-5.0,   11.8],    # slightly offshore Gulf of Guinea
    "Malembo":      [-5.2,   11.9],    # slightly offshore
    "Epe":          [6.45,    3.30],   # Lagos ocean coast (prev coords were inland lagoon)
    "West Central Africa and St Helena, port unspecified": [-5.0, 11.6],
    "Kilwa":        [-8.93,  39.60],   # Kilwa Kisiwani, slightly offshore Tanzania
    "Gallinhas":    [7.30,  -12.20],   # Cape Gallinas, clearly offshore Sierra Leone coast
    "Gambia":       [13.40, -16.80],   # Gambia River mouth, clear of coast
    "Windward Coast, place unspecified": [4.60, -8.20],  # offshore Ivory Coast/Liberia
    "Windward Coast place unspecified":  [4.60, -8.20],
    "Buenos Aires": [-35.50, -56.50],  # open Río de la Plata, avoids Uruguay coast clip
    "Bengal":       [21.90,  88.50],   # Bay of Bengal coast (prev coords were inland)

    # ── Saint-Domingue moved to Port-au-Prince harbor (was inland Haiti) ───
    "Saint-Domingue, then Haiti, port unspecified": [18.55, -72.34],

    # ── SE Africa destination: open Mozambique Channel (Comoros area) ──────
    # Previous [-15, 44] was on/near Madagascar's west coast causing land crossings
    "Southeast Africa and Indian Ocean islands, port unspecified": [-13.0, 43.5],
    "Southeast Africa and Indian Ocean islands, port unspecified ": [-13.0, 43.5],

    # ── Sainte Luce: appears in Indian Ocean dataset = SE Madagascar, not Martinique ─
    # Cannot disambiguate by port name alone; handled in clean_voyages.py instead

    # ── Additional port corrections ────────────────────────────────────────
    "Zion Hill":  [18.2,  -77.7],    # Zion Hill, Jamaica (Nominatim returned Connecticut)
    "Bissau":     [11.85, -15.70],   # slightly more offshore Guinea-Bissau coast
    "Cess":       [5.47,  -9.60],    # duplicate entry fix
}


def nominatim_lookup(client: httpx.Client, port: str) -> list[float] | None:
    try:
        r = client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": port, "format": "json", "limit": 1},
            headers={"User-Agent": "slave-voyages-research/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json()
        if results:
            return [float(results[0]["lat"]), float(results[0]["lon"])]
    except Exception as e:
        print(f"  ERROR looking up '{port}': {e}")
    return None


def main():
    with open(OUTPUT_JSON, encoding="utf-8") as f:
        data = json.load(f)

    # Collect unique port names
    ports: set[str] = set()
    for voyage in data["voyages"]:
        for wp in voyage["waypoints"]:
            if wp.get("port"):
                ports.add(wp["port"])

    print(f"Found {len(ports)} unique port names")

    # Load existing ports.json if present (allows resuming interrupted runs)
    if PORTS_JSON.exists():
        with open(PORTS_JSON, encoding="utf-8") as f:
            results: dict[str, list[float] | None] = json.load(f)
        print(f"Resuming — {len(results)} ports already cached")
    else:
        results = {}

    # Apply overrides — always wins over cached Nominatim results
    for port, coords in OVERRIDES.items():
        results[port] = coords

    # Geocode remaining ports via Nominatim
    to_lookup = [p for p in sorted(ports) if p not in results]
    print(f"Looking up {len(to_lookup)} ports via Nominatim…")

    with httpx.Client() as client:
        for i, port in enumerate(to_lookup, 1):
            coords = nominatim_lookup(client, port)
            results[port] = coords
            status = f"{coords[0]:.3f}, {coords[1]:.3f}" if coords else "NOT FOUND"
            print(f"  [{i}/{len(to_lookup)}] {port} → {status}")
            # Save after every 10 lookups so progress isn't lost
            if i % 10 == 0:
                with open(PORTS_JSON, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
            time.sleep(1)  # Nominatim rate limit: 1 req/sec

    with open(PORTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    found = sum(1 for v in results.values() if v is not None)
    print(f"\nDone. {found}/{len(results)} ports geocoded → {PORTS_JSON}")


if __name__ == "__main__":
    main()
