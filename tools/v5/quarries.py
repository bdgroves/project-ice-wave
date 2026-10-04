"""
IceWave v5: where Ice Age bones in Washington actually come to light.

Washington's best-known Ice Age finds were all made by someone digging: the Coyote Canyon mammoth in a
rock pit south of Kennewick (1999), the Manis mastodon in a farm pond near Sequim (1977), the Wenas
Creek mammoth during road building near Selah (2005), and a mammoth tusk 30 feet down in a Seattle
apartment excavation (2014). So instead of guessing at terrain, v5 ranks the places where the
digging is happening: every active surface-mine permit in the state, by the rock the pit is cut into.

    python tools/v5/quarries.py          # in CI: needs WA DNR, PBDB and iDigBio

1. Mines: Washington DNR active surface-mine permit sites (name, operator, acreage, depth, commodity).
2. Geology at each pit: WA DNR 1:100,000 geologic map unit, sorted into kinds of ground: Ice Age
   flood deposits, loess, lake and bog deposits, glacial deposits, alluvium, other Quaternary, bedrock.
   Bones of Ice Age animals are in the first four; essentially never in bedrock.
3. Known finds: Pleistocene vertebrate fossils in Washington from PBDB and iDigBio (fossil specimens
   only; the first IceWave also pulled modern museum skins and skeletons, zoo animals included).
4. Score: the kind of ground sets the tier; within a tier, larger and deeper pits rank higher, and pits
   within 25 km of a recorded Ice Age find get a nudge. The rules were written before ranking, but
   knowing Coyote Canyon sits on loess, so its rank is a check of the rules, not a blind test.

Writes data/v5/quarries.csv, quarries.geojson, finds.geojson, eval.json.
"""
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "v5"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "IceWave v5 (github.com/bdgroves/project-ice-wave)"}
DNR = "https://gis.dnr.wa.gov/site1/rest/services/Public_Geology/"
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:5.0f}s]", *a, flush=True)


def get(url, tries=4, timeout=60):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            log("  retry", i, str(e)[:100], url[:90])
            time.sleep(3 * (i + 1))
    return None


def km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# ── 1. mines ─────────────────────────────────────────────────────────────
js = get(DNR + "Active_Surface_Mine_Permit_Sites/MapServer/0/query?" + urllib.parse.urlencode(
    {"where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json", "resultRecordCount": 2000}))
mines = pd.DataFrame([f["attributes"] for f in js["features"]])
mines = mines.dropna(subset=["LATITUDE", "LONGITUDE"])
log(f"active surface-mine permits: {len(mines)}")

# ── 2. geology at each pit ───────────────────────────────────────────────
KINDS = [  # (kind, tier, words in the map unit's description)
    ("Ice Age flood deposits", 1, ("outburst", "cataclysm", "missoula", "flood deposit", "flood gravel", "touchet")),
    ("loess", 1, ("loess", "eolian", "palouse")),
    ("lake or bog deposits", 1, ("lacustrine", "lake deposit", "peat", "bog", "marsh", "pond")),
    ("glacial deposits", 1, ("glacial", "outwash", "till", "drift", "glaciolacustrine", "glaciomarine", "vashon")),
    ("alluvium", 2, ("alluvi", "terrace", "fan deposit", "fluvial")),
    ("other Quaternary", 2, ("quaternary", "pleistocene", "landslide", "mass-wasting", "colluvi")),
]


def kind_of(desc):
    d = (desc or "").lower()
    for k, tier, words in KINDS:
        if any(w in d for w in words):
            return k, tier
    return "bedrock or older", 3


cache = OUT / "geology_at_mines.json"
geo = json.loads(cache.read_text()) if cache.exists() else {}


def unit_at(m):
    q = urllib.parse.urlencode({"geometry": f"{m.LONGITUDE},{m.LATITUDE}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                                "spatialRel": "esriSpatialRelIntersects", "outFields": "MAP_UNIT_100K_LABEL,MAP_UNIT_100K_SYMBOL,MAP_UNIT_100K_QUAD_NAME",
                                "returnGeometry": "false", "f": "json"})
    r = get(DNR + "100K_Surface_Geology_WA_GeMS/MapServer/11/query?" + q, tries=3, timeout=45)
    a = (r or {}).get("features", [{}])
    a = a[0].get("attributes", {}) if a else {}
    return str(int(m.MINE_PERMIT_NUMBER)), {"label": a.get("MAP_UNIT_100K_LABEL"), "desc": a.get("MAP_UNIT_100K_SYMBOL"), "quad": a.get("MAP_UNIT_100K_QUAD_NAME")}


from concurrent.futures import ThreadPoolExecutor   # noqa: E402
todo = [m for _, m in mines.iterrows() if str(int(m.MINE_PERMIT_NUMBER)) not in geo]
log(f"geology lookups to do: {len(todo)}")
with ThreadPoolExecutor(8) as ex:
    for i, (k, v) in enumerate(ex.map(unit_at, todo)):
        geo[k] = v
        if i % 50 == 0:
            log(f"  {i + 1}/{len(todo)}")
            cache.write_text(json.dumps(geo, indent=0))
cache.write_text(json.dumps(geo, indent=0))
mines["unit"] = [geo[str(int(p))]["label"] for p in mines.MINE_PERMIT_NUMBER]
mines["unit_desc"] = [geo[str(int(p))]["desc"] for p in mines.MINE_PERMIT_NUMBER]
kt = [kind_of(d) for d in mines.unit_desc]
mines["ground"] = [k for k, _ in kt]
mines["tier"] = [t for _, t in kt]
log("pits by ground:", mines.ground.value_counts().to_dict())
log("unit descriptions seen, by kind:")
for k, g in mines.groupby("ground"):
    log(f"  {k}: {g.unit_desc.value_counts().head(12).to_dict()}")

# ── 3. known Ice Age finds ───────────────────────────────────────────────
finds = []
pb = get("https://paleobiodb.org/data1.2/occs/list.json?" + urllib.parse.urlencode(
    {"state": "Washington", "interval": "Pleistocene", "base_name": "Vertebrata", "show": "coords,loc,prec", "vocab": "pbdb", "limit": "all"}))
for r in (pb or {}).get("records", []):
    if r.get("lat") and r.get("lng"):
        finds.append({"source": "PBDB", "taxon": r.get("accepted_name"), "lat": float(r["lat"]), "lon": float(r["lng"]),
                      "precision": r.get("latlng_precision"), "county": r.get("county")})
rq = {"stateprovince": "washington", "basisofrecord": "fossilspecimen", "geopoint": {"type": "exists"},
      "genus": ["mammuthus", "mammut", "bison", "equus", "camelops", "paramylodon", "megalonyx", "arctodus", "bootherium",
                "hemiauchenia", "cervus", "rangifer", "symbos", "ovibos", "castoroides"]}
ib = get("https://search.idigbio.org/v2/search/records?" + urllib.parse.urlencode({"rq": json.dumps(rq), "limit": 1000}))
for it in (ib or {}).get("items", []):
    t = it["indexTerms"]
    finds.append({"source": "iDigBio", "taxon": (t.get("genus") or "").capitalize(), "lat": t["geopoint"]["lat"], "lon": t["geopoint"]["lon"],
                  "precision": t.get("coordinateuncertaintyinmeters"), "county": t.get("county"), "inst": t.get("institutioncode")})
F = pd.DataFrame(finds)
if len(F):
    F = F[(F.lat > 45.5) & (F.lat < 49.1) & (F.lon > -124.9) & (F.lon < -116.9)]
F["key"] = F.lat.round(2).astype(str) + "_" + F.lon.round(2).astype(str)
places = F.groupby("key").agg(lat=("lat", "mean"), lon=("lon", "mean"), n=("taxon", "size"),
                              taxa=("taxon", lambda s: sorted({str(x) for x in s if x})[:8]), sources=("source", lambda s: sorted(set(s)))).reset_index()
log(f"Ice Age vertebrate fossil records in WA: {len(F)} at {len(places)} places (PBDB {int((F.source == 'PBDB').sum())}, iDigBio {int((F.source == 'iDigBio').sum())})")

# ── 4. score ─────────────────────────────────────────────────────────────
def near_find(lat, lon):
    return min((km(lat, lon, a, b) for a, b in zip(places.lat, places.lon)), default=999)


mines["km_to_find"] = [round(near_find(a, b), 1) for a, b in zip(mines.LATITUDE, mines.LONGITUDE)]
acre = mines.PERMIT_ACREAGE.fillna(0).clip(lower=0)
depth = mines.PERMIT_DEPTH.fillna(0).clip(lower=0)
size = (acre.rank(pct=True) + depth.rank(pct=True)) / 2
mines["score"] = (3 - mines.tier) + 0.6 * size + 0.4 * (mines.km_to_find <= 25)
mines = mines.sort_values("score", ascending=False).reset_index(drop=True)
mines["rank"] = range(1, len(mines) + 1)
cc = mines[mines.MINE_NAME.str.contains("MAHAFFEY", case=False, na=False)]
ev = {"mines": len(mines), "by_ground": mines.ground.value_counts().to_dict(),
      "tier1": int((mines.tier == 1).sum()), "finds": len(F), "find_places": len(places)}
if len(cc):
    r = cc.iloc[0]
    ev["coyote_canyon_pit"] = {"name": r.MINE_NAME, "permit": int(r.MINE_PERMIT_NUMBER), "rank": int(r["rank"]), "of": len(mines),
                               "ground": r.ground, "unit": r.unit_desc, "km_to_find": float(r.km_to_find),
                               "percentile": round(1 - (r["rank"] - 1) / len(mines), 3)}
    log("Coyote Canyon pit:", ev["coyote_canyon_pit"])
# how many recorded find places sit within 3 km of a tier-1 pit? (a rough check that pits and finds go together)
t1 = mines[mines.tier == 1]
ev["find_places_within_3km_of_tier1_pit"] = int(sum(min((km(a, b, x, y) for x, y in zip(t1.LATITUDE, t1.LONGITUDE)), default=999) <= 3
                                                     for a, b in zip(places.lat, places.lon)))
keep = ["rank", "MINE_NAME", "APPLICANT_NAME", "COUNTY_NAME", "LATITUDE", "LONGITUDE", "PERMIT_ACREAGE", "PERMIT_DEPTH",
        "COMMODITY_DESC", "unit", "unit_desc", "ground", "tier", "km_to_find", "score", "MINE_PERMIT_NUMBER"]
mines[keep].to_csv(OUT / "quarries.csv", index=False)
fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r.LONGITUDE, 5), round(r.LATITUDE, 5)]},
      "properties": {"rank": int(r["rank"]), "name": str(r.MINE_NAME).title(), "operator": str(r.APPLICANT_NAME).title(), "county": r.COUNTY_NAME,
                     "acres": r.PERMIT_ACREAGE, "depth_ft": r.PERMIT_DEPTH, "commodity": (r.COMMODITY_DESC or "").strip(), "ground": r.ground,
                     "tier": int(r.tier), "unit": r.unit_desc, "km_to_find": r.km_to_find}} for _, r in mines.iterrows()]}
(OUT / "quarries.geojson").write_text(json.dumps(fc, default=lambda o: None if o != o else o))
(OUT / "finds.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r.lon, 4), round(r.lat, 4)]},
     "properties": {"n": int(r.n), "taxa": r.taxa, "sources": r.sources}} for _, r in places.iterrows()]}))
(OUT / "eval.json").write_text(json.dumps(ev, indent=1, default=str))
log("top 15:")
log(mines[keep[:12]].head(15).to_string())
