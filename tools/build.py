"""
Build the page's data in site/ from the committed model outputs (and this week's PBDB check).

    python tools/build.py

Writes
  site/targets.geojson  the 42 targets (17 west, 25 east), with what the re-check found at each:
                        zero terrain values, a level patch on the elevation model, OpenStreetMap water,
                        TPI, the v3 and final-v4 ranks, and the close-up panel if there is one
  site/known.geojson    the fossil records the two models were trained on
  site/panels/E##.jpg   the 20 terrain close-ups from notebook 05, as web-sized JPEGs
  site/live.json        what PBDB lists now that the model never saw, and anything within 10 km of a target
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENUS, km  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
SITE = ROOT / "site"
(SITE / "panels").mkdir(parents=True, exist_ok=True)
NEAR_KM = 10
NEW_KM = 1


def level_patch(rank, lat, lon):
    """Area (km²) around the target where the 3DEP surface is within 1 cm of the target's own height.
    Elevation models flatten lakes, reservoirs and wide rivers to a single level, so a large level
    patch means the target is on water."""
    f = D / "lidar" / f"E{rank:02d}_dtm.tif"
    if not f.exists():
        return {}
    import rasterio
    from scipy import ndimage
    with rasterio.open(f) as s:
        z = s.read(1).astype(float)
        r, c = s.index(lon, lat)
        cell = abs(s.res[0]) * 111.32 * abs(s.res[1]) * 111.32 * math.cos(math.radians(lat))   # km²
    lab, _ = ndimage.label(np.abs(z - z[r, c]) < 0.01)
    return {"elev_m": round(float(z[r, c]), 2), "level_km2": round(float((lab == lab[r, c]).sum() * cell), 2)}


def fc(feats):
    return {"type": "FeatureCollection", "features": feats}


def pt(lon, lat, props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": props}


# ── targets ──────────────────────────────────────────────────────────────
tg = pd.read_csv(D / "model" / "icewave_v3_top50_lidar.csv")
fin = pd.read_csv(D / "model" / "icewave_v4_final_top50.csv")
osm_file = D / "checks" / "osm_targets.json"
osm = json.loads(osm_file.read_text()) if osm_file.exists() else {}
v4 = fin[fin.ecoregion == "east"].sort_values("comp_v4_final_norm", ascending=False).reset_index(drop=True)
v4rank = {int(r["rank"]): i + 1 for i, r in v4.iterrows()}
v3rank = {}
for eco in ("west", "east"):
    s = tg[tg.ecoregion == eco].sort_values("composite_norm", ascending=False).reset_index(drop=True)
    v3rank |= {int(r["rank"]): i + 1 for i, r in s.iterrows()}

try:
    from PIL import Image
except ImportError:
    Image = None
targets = []
for _, r in tg.iterrows():
    rank = int(r["rank"])
    east = r.ecoregion == "east"
    tid = f"{'E' if east else 'W'}{rank:02d}"
    p = {"id": tid, "rank": rank, "eco": r.ecoregion, "v3_score": round(float(r.composite_norm), 3),
         "v3_rank": v3rank[rank], "lith_score": float(r.lith_score),
         "zero_terrain": bool(r.slope == 0 and r.aspect == 0 and r.tri == 0)}
    if east:
        p["v4_rank"] = v4rank.get(rank)
        p["v4_score"] = round(float(fin.loc[fin["rank"] == rank, "comp_v4_final_norm"].iloc[0]), 3)
    if not np.isnan(r.get("tpi_15m", np.nan)):
        p["tpi_m"] = round(float(r.tpi_15m), 1)
    if east:
        p |= level_patch(rank, r.latitude, r.longitude)
    if str(rank) in osm:
        p["osm"] = osm[str(rank)]
    png = ROOT / "outputs" / f"lidar_{tid}.png"
    if png.exists() and Image is not None:
        jpg = SITE / "panels" / f"{tid}.jpg"
        if not jpg.exists() or jpg.stat().st_mtime < png.stat().st_mtime:
            im = Image.open(png).convert("RGB")
            im.thumbnail((1600, 1600))
            im.save(jpg, quality=82, optimize=True)
        p["panel"] = f"panels/{tid}.jpg"
    targets.append(pt(r.longitude, r.latitude, p))
(SITE / "targets.geojson").write_text(json.dumps(fc(targets)))

# ── known: the training records ──────────────────────────────────────────
pres = pd.read_csv(D / "pbdb" / "icewave_east_presence_features_v2.csv")
exp = pd.read_csv(D / "pbdb" / "icewave_east_expanded.csv")
known = []
for (_, r), (_, e) in zip(pres.iterrows(), exp.iterrows()):
    kind, big = GENUS.get(r.genus, (r.genus, None))
    known.append(pt(r.longitude, r.latitude, {
        "model": "east", "taxon": r.accepted_name, "genus": r.genus, "kind": kind, "large": big,
        "state": r.state_query, "lith_score": float(r.lith_score),
        "zero_terrain": bool(e.elevation == 0 and e.slope == 0 and e.tri == 0)}))
v2 = pd.read_csv(D / "model" / "icewave_v2_training.csv")
occ = pd.concat([pd.read_csv(D / "pbdb" / "icewave_occurrences.csv")[["taxon_name", "latitude", "longitude"]],
                 pd.read_csv(D / "merged" / "icewave_merged_occurrences.csv").rename(columns={"taxon": "taxon_name"})
                 [["taxon_name", "latitude", "longitude"]]])
west = v2[(v2.longitude <= -121.5) & (v2.presence == 1)].drop_duplicates(["latitude", "longitude"])
for _, r in west.iterrows():
    m = occ[(occ.latitude.round(5) == round(r.latitude, 5)) & (occ.longitude.round(5) == round(r.longitude, 5))]
    taxon = m.taxon_name.iloc[0] if len(m) else None
    known.append(pt(r.longitude, r.latitude, {"model": "west", "taxon": taxon, "lith_score": float(r.lith_score)}))
(SITE / "known.geojson").write_text(json.dumps(fc(known)))

# ── live: this week's PBDB check against what the model saw ─────────────
live_file = SITE / "pbdb_live.json"
prev_file = SITE / "live.json"
prev = json.loads(prev_file.read_text()) if prev_file.exists() else {}
live = {"near_km": NEAR_KM, "new_km": NEW_KM}
if live_file.exists():
    L = json.loads(live_file.read_text())
    recs = pd.DataFrame(L["records"])
    recs = recs.dropna(subset=["lat", "lng"])
    recs["lat"], recs["lng"] = recs.lat.astype(float), recs.lng.astype(float)
    recs["key"] = recs.lat.round(3).astype(str) + "_" + recs.lng.round(3).astype(str)
    locs = recs.groupby("key").agg(lat=("lat", "first"), lng=("lng", "first"), state=("state_query", "first"),
                                   n=("occurrence_no", "size"),
                                   taxa=("accepted_name", lambda s: sorted({str(x) for x in s if x == x})[:8])).reset_index()
    # Everything the model saw: east training records, the March 2026 east harvest, west training records.
    raw = pd.read_csv(D / "pbdb" / "icewave_east_expanded_raw.csv")
    seen = np.r_[np.c_[exp.latitude, exp.longitude], np.c_[raw.latitude, raw.longitude], np.c_[west.latitude, west.longitude],
                 np.c_[occ.latitude, occ.longitude]]
    dmin = np.array([km(a, b, seen[:, 0], seen[:, 1]).min() for a, b in zip(locs.lat, locs.lng)])
    locs["unseen"] = dmin > NEW_KM
    prev_keys = set(prev.get("locality_keys", []))
    new_week = [] if not prev_keys else [k for k in locs.key if k not in prev_keys]
    near = []
    for t in targets:
        lon, lat = t["geometry"]["coordinates"]
        d = km(lat, lon, locs.lat.to_numpy(), locs.lng.to_numpy())
        for i in np.where(d <= NEAR_KM)[0]:
            near.append({"target": t["properties"]["id"], "km": round(float(d[i]), 1), "key": locs.key[i],
                         "taxa": locs.taxa[i], "n": int(locs.n[i]), "in_training": not bool(locs.unseen[i])})
    unseen = locs[locs.unseen]
    live |= {
        "checked": L["checked"], "records": int(len(recs)), "localities": int(len(locs)),
        "by_state": recs.state_query.value_counts().to_dict(),
        "unseen_localities": int(len(unseen)),
        "unseen": [{"lat": round(r.lat, 4), "lng": round(r.lng, 4), "state": r.state, "n": int(r.n), "taxa": r.taxa}
                   for _, r in unseen.iterrows()],
        "near_targets": sorted(near, key=lambda x: x["km"]),
        "new_since_last_check": new_week,
        "locality_keys": sorted(locs.key),
    }
    print(f"live: {len(recs)} PBDB records at {len(locs)} localities; {len(unseen)} more than {NEW_KM} km from anything "
          f"the model saw; {len({n['target'] for n in near})} targets have a PBDB locality within {NEAR_KM} km; "
          f"{len(new_week)} new since the last check")
else:
    live["checked"] = None
    print("live: no site/pbdb_live.json yet (run tools/pbdb.py)")
prev_file.write_text(json.dumps(live, indent=0))
print(f"targets {len(targets)}, known {len(known)}, panels {len(list((SITE / 'panels').glob('*.jpg')))}")
