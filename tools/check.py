"""
Re-check IceWave's published numbers from the files committed in this repo, and write site/checks.json.

    python tools/check.py

What it checks (each one prints, and lands in checks.json for the page):

  1. training   What the 40 east "fossil" records are, and how many separate places they come from.
  2. lithology  Whether lith_score was measured the same way at fossil records and at random background
                points. (It wasn't: every background point got one fixed default.)
  3. zeros      Fossil records and targets whose terrain values are exactly zero, and whether those
                targets sit on a perfectly level patch of the elevation model (how 3DEP draws water).
  4. retest     Leave-one-out the way notebook 07 did it, then leaving out whole places, with and
                without lith_score. Random forests use the notebook's settings, with 200 trees
                instead of 500 so this runs in a few minutes (the counts move by a record or two).
  5. tpi        The "valley floor" claim: how many valley-floor targets are on level water patches,
                and how well TPI on its own separates fossil places from background.
  6. e02        How far target E02 is from the Coyote Canyon mammoth site, and where E02 ranks in
                the final model.

Inputs are in data/, plus site/targets.geojson from tools/build.py (run that first). tools/osm.py
(run once, in CI) adds what OpenStreetMap maps at each target and where the Coyote Canyon site is;
if its file is missing, those parts are skipped.
"""
import json
from pathlib import Path

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENUS, km  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

PLACE_KM = 10            # records closer than this (single linkage) count as one place
TREES = 200
RF = dict(n_estimators=TREES, max_depth=6, min_samples_leaf=3, class_weight="balanced", random_state=42, n_jobs=-1)

def places(lat, lon, limit=PLACE_KM):
    """Single-linkage groups: records within `limit` km of each other (directly or in a chain) are one place."""
    from scipy.cluster.hierarchy import fcluster, linkage
    lat, lon = np.asarray(lat), np.asarray(lon)
    if len(lat) < 2:
        return np.ones(len(lat), int)
    xy = np.c_[lat * 111.2, lon * 111.2 * np.cos(np.radians(lat))]
    return fcluster(linkage(xy, "single"), limit, "distance")


def retest(df, feats):
    """Leave-one-record-out (notebook 07's test) and leave-one-place-out, presence-only recall at 0.5."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score
    X, y, g = df[feats].to_numpy(float), df["presence"].to_numpy(), df["place"].to_numpy()
    pres = np.where(y == 1)[0]
    rec = []
    for i in pres:
        tr = np.ones(len(y), bool)
        tr[i] = False
        rec.append(RandomForestClassifier(**RF).fit(X[tr], y[tr]).predict_proba(X[[i]])[0, 1])
    # Leave each place out in turn, along with an equal share of the background points.
    pl = np.unique(g[pres])
    bg = np.where(y == 0)[0]
    share = np.random.default_rng(0).integers(0, len(pl), len(bg))
    prob = np.zeros(len(y))
    for k, G in enumerate(pl):
        te = g == G
        te[bg[share == k]] = True
        prob[te] = RandomForestClassifier(**RF).fit(X[~te], y[~te]).predict_proba(X[te])[:, 1]
    pp = prob[pres]
    by_place = pd.Series(pp).groupby(g[pres]).max()
    return {
        "features": feats,
        "records": int(len(pres)), "places": int(len(pl)),
        "record_loo_found": int((np.array(rec) > 0.5).sum()),
        "place_out_records_found": int((pp > 0.5).sum()),
        "place_out_places_found": int((by_place > 0.5).sum()),
        "place_out_auc": round(float(roc_auc_score(y, prob)), 3),
        "background_flagged": round(float((prob[y == 0] > 0.5).mean()), 3),
    }


out = {"place_km": PLACE_KM, "trees": TREES}
osm_file = D / "checks" / "osm_targets.json"
osm = json.loads(osm_file.read_text()) if osm_file.exists() else {}

# ── 1. training ──────────────────────────────────────────────────────────
pres = pd.read_csv(D / "pbdb" / "icewave_east_presence_features_v2.csv")
bg = pd.read_csv(D / "pbdb" / "icewave_east_background_v2.csv")
pres["place"] = places(pres.latitude, pres.longitude)
kinds = pres.genus.map(lambda g: GENUS.get(g, (g, None)))
big = kinds.map(lambda k: k[1])
out["training"] = {
    "east_records": int(len(pres)), "east_places": int(pres.place.nunique()),
    "biggest_place": int(pres.place.value_counts().iloc[0]),
    "large_mammals": int((big == True).sum()),                         # noqa: E712
    "not_large_mammals": int((big == False).sum()),                    # noqa: E712
    "small": sorted({k[0] for k, b in zip(kinds, big) if b is False}),
    "by_state": pres.state_query.value_counts().to_dict(),
    "background": int(len(bg)),
}
v2 = pd.read_csv(D / "model" / "icewave_v2_training.csv")
west = v2[v2.longitude <= -121.5].copy()
wp = west.presence == 1
west["place"] = 0
west.loc[wp, "place"] = places(west.loc[wp, "latitude"], west.loc[wp, "longitude"])
west.loc[~wp, "place"] = -1 - np.arange((~wp).sum())
out["training"]["west_records"] = int(wp.sum())
out["training"]["west_places"] = int(west.loc[wp, "place"].nunique())
adm = osm.get("records_admin", {})
if adm:
    def where(df):
        return pd.Series([adm.get(f"{a:.6f},{b:.6f}") for a, b in zip(df.latitude, df.longitude)]).value_counts().to_dict()
    out["training"]["east_by_osm_state"] = where(pres)
    out["training"]["west_by_osm_state"] = where(west[wp])
print("1. training:", out["training"])

# ── 2. lithology ─────────────────────────────────────────────────────────
expanded = pd.read_csv(D / "pbdb" / "icewave_east_expanded.csv")
out["lithology"] = {
    "east_v4": {"background_values": sorted(bg.lith_score.unique().tolist()),
                "presence_values": sorted(pres.lith_score.unique().tolist()),
                "presence_at_background_value": int(pres.lith_score.isin(bg.lith_score.unique()).sum())},
    "east_v3": {"background_value": 0.4,     # notebook 04, cell "Background points": bg_df['lith_score'] = 0.4
                "presence_not_default": int((expanded.lith_score != 0.4).sum())},
    "west": {"background_values": sorted(west.loc[~wp, "lith_score"].unique().tolist()),
             "presence_not_default": int((west.loc[wp, "lith_score"] != 0.4).sum()), "presence": int(wp.sum())},
}
print("2. lithology:", out["lithology"])

# ── 3. zeros ─────────────────────────────────────────────────────────────
tg = pd.read_csv(D / "model" / "icewave_v3_top50_lidar.csv")
east = tg[tg.ecoregion == "east"].copy()
zero_t = (east.slope == 0) & (east.aspect == 0) & (east.tri == 0)
zero_p = (expanded.elevation == 0) & (expanded.slope == 0) & (expanded.aspect == 0) & (expanded.tri == 0)
gj = json.loads((SITE / "targets.geojson").read_text())     # written by tools/build.py
targets = [f["properties"] | {"lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0]}
           for f in gj["features"]]
ev = [t for t in targets if t["eco"] == "east"]
ev_v3 = sorted(ev, key=lambda t: t["v3_rank"])
top6 = [t["id"] for t in ev_v3[:6]]
lvl = [t for t in ev if t.get("level_km2", 0) >= 0.05]
out["zeros"] = {
    "presence_all_zero": int(zero_p.sum()), "presence": int(len(expanded)),
    "presence_all_zero_states": expanded.loc[zero_p, "state_query"].value_counts().to_dict(),
    "east_targets": int(len(east)), "targets_all_zero": int(zero_t.sum()),
    "top6_east": top6, "top6_all_zero": int(sum(t["zero_terrain"] for t in ev_v3[:6])),
    "targets_with_dtm": int(sum("level_km2" in t for t in ev)),
    "zero_targets_with_dtm": int(sum("level_km2" in t and t["zero_terrain"] for t in ev)),
    "zero_targets_on_level_patch": int(sum(t["zero_terrain"] for t in lvl)),
    "level_targets": [{"id": t["id"], "elev_m": t["elev_m"], "level_km2": t["level_km2"]} for t in lvl],
}
if osm:
    water = [t["id"] for t in ev if t.get("osm", {}).get("water") or t.get("osm", {}).get("waterway")]
    out["zeros"]["osm_water"] = water
print("3. zeros:", {k: v for k, v in out["zeros"].items() if k != "level_targets"})

# ── 4. retest ────────────────────────────────────────────────────────────
for x in (pres, bg):
    x["tpi_15m"] = x["tpi_15m"].fillna(0)             # notebook 07 fills missing TPI with 0
bg["place"] = -1 - np.arange(len(bg))
dd = pd.concat([pres.assign(presence=1), bg.assign(presence=0)], ignore_index=True)
T = ["elevation", "slope", "aspect", "tri"]
out["retest"] = {
    "east_as_built": retest(dd, T + ["lith_score", "tpi_15m"]),
    "east_without_lith": retest(dd, T + ["tpi_15m"]),
    "east_tpi_only": retest(dd, ["tpi_15m"]),
    "west_as_built": retest(west, T + ["lith_score"]),
    "west_terrain_only": retest(west, T),
}
for k, v in out["retest"].items():
    print(f"4. {k}: record-LOO {v['record_loo_found']}/{v['records']}; whole places left out: "
          f"{v['place_out_places_found']}/{v['places']} places ({v['place_out_records_found']} records), "
          f"AUC {v['place_out_auc']}, background flagged {v['background_flagged']:.0%}")

# ── 5. tpi ───────────────────────────────────────────────────────────────
withtpi = [t for t in ev if "tpi_m" in t and "level_km2" in t]
vf = [t for t in withtpi if t["tpi_m"] < -5]                 # notebook 05's "VALLEY FLOOR" threshold
out["tpi"] = {
    "targets_with_tpi": len(withtpi), "valley_floor": len(vf),
    "valley_floor_on_level_patch": sum(t.get("level_km2", 0) >= 0.05 for t in vf),
    "valley_floor_ids": [t["id"] for t in vf],
    "presence_median": round(float(pres.tpi_15m.median()), 1), "background_median": round(float(bg.tpi_15m.median()), 1),
    "tpi_only_auc": out["retest"]["east_tpi_only"]["place_out_auc"],
}
print("5. tpi:", out["tpi"])

# ── 6. e02 ───────────────────────────────────────────────────────────────
cc = osm.get("coyote_canyon")                 # from tools/osm.py: the "Coyote Canyon Mammoth Site" outline in OpenStreetMap
e02 = next(t for t in targets if t["rank"] == 2)
near = pres.assign(d=km(e02["lat"], e02["lon"], pres.latitude, pres.longitude)).sort_values("d").iloc[0]
out["e02"] = {
    "lat": e02["lat"], "lon": e02["lon"], "coyote_canyon": cc,
    "km_to_coyote_canyon": round(float(km(e02["lat"], e02["lon"], cc["lat"], cc["lon"])), 1) if cc else None,
    "v3_rank_east": 1, "v4_rank_east": e02.get("v4_rank"), "east_targets": len(ev),
    "level_km2": e02.get("level_km2"), "elev_m": e02.get("elev_m"), "osm": e02.get("osm"),
    "nearest_training_km": round(float(near.d), 1), "nearest_training": f"{GENUS.get(near.genus, (near.genus,))[0]} ({near.genus})",
    "dig_began": "2008 (quarry find 1999)",
}
print("6. e02:", out["e02"])

# ── 7. modern animals in the training data ───────────────────────────────
mod_file = D / "checks" / "modern_records.json"
if mod_file.exists():
    mod = json.loads(mod_file.read_text())["records"]
    wp_ = west[wp]
    hits = [r for r in mod if ((wp_.latitude.round(4) == round(r["lat"], 4)) & (wp_.longitude.round(4) == round(r["lon"], 4))).any()]
    out["modern"] = {"west_records": int(len(wp_)), "modern": len(hits), "records": hits}
    print("7. modern:", len(hits), "of", len(wp_), "west training records are modern museum specimens")

(SITE / "checks.json").write_text(json.dumps(out, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print("wrote site/checks.json")
