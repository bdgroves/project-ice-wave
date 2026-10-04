"""
Run once (in CI; the result is committed): ask OpenStreetMap what is mapped at each target and at
each training record, and where the Coyote Canyon mammoth site is. Writes data/checks/osm_targets.json.

  - for each target: any water area it sits inside (lake, reservoir, river), with its name; any named
    river or canal within 100 m; and any protected area (a wilderness, a park)
  - for each training record: the state or province it falls in
  - Coyote Canyon: South Clodfelter Road, the site's address (McBones Research Center), south of Kennewick

    python tools/osm.py            # skips if the file exists; --refresh to redo
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
OUT = D / "checks" / "osm_targets.json"
OVP = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
       "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
UA = {"User-Agent": "IceWave re-check (github.com/bdgroves/project-ice-wave)"}

if OUT.exists() and "--refresh" not in sys.argv:
    print(f"{OUT.relative_to(ROOT)} exists; --refresh to redo")
    sys.exit(0)


def overpass(q):
    for u in OVP:
        for attempt in range(2):
            try:
                req = urllib.request.Request(u, data=urllib.parse.urlencode({"data": q}).encode(), headers=UA)
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read())
            except Exception as e:  # noqa: BLE001
                print(f"  {u}: {e}")
                time.sleep(15)
    raise SystemExit("Overpass didn't answer")


def tagged(elements):
    """Split one combined answer back into per-point lists, using the 'make mark' separators."""
    out, cur = {}, None
    for e in elements:
        if e["type"] == "mark":
            cur = e["tags"]["id"]
            out[cur] = []
        elif cur is not None:
            out[cur].append(e.get("tags", {}))
    return out


tg = pd.read_csv(D / "model" / "icewave_v3_top50.csv")
q = ["[out:json][timeout:600];"]
for _, r in tg.iterrows():
    q.append(f'make mark id="{int(r["rank"])}"; out;')
    q.append(f'is_in({r.latitude:.6f},{r.longitude:.6f})->.a;'
             'area.a[~"^(natural|water|waterway|landuse|leisure|boundary)$"~"^(water|lake|reservoir|river|riverbank|'
             'basin|national_park|protected_area|nature_reserve)$"]; out tags;')
res = tagged(overpass("\n".join(q))["elements"])
# Rivers are often mapped only as a centre line, which is_in can't see: take named waterways within 100 m.
time.sleep(10)
q = ["[out:json][timeout:600];"]
for _, r in tg.iterrows():
    q.append(f'make mark id="{int(r["rank"])}"; out;')
    q.append(f'way(around:100,{r.latitude:.6f},{r.longitude:.6f})[waterway~"^(river|canal|stream)$"]; out tags;')
ways = tagged(overpass("\n".join(q))["elements"])
targets = {}
for k, tags in res.items():
    water = next((t for t in tags if t.get("natural") == "water" or t.get("landuse") in ("reservoir", "basin")
                  or t.get("waterway") == "riverbank" or "water" in t), None)
    prot = next((t for t in tags if t.get("boundary") in ("national_park", "protected_area") or t.get("leisure") == "nature_reserve"), None)
    targets[k] = {"water": None if water is None else (water.get("name") or water.get("water") or "water"),
                  "water_kind": None if water is None else (water.get("water") or water.get("landuse") or water.get("natural")),
                  "protected": None if prot is None else prot.get("name"),
                  "waterway": next((w.get("name") or w.get("waterway") for w in ways.get(k, []) if w.get("name")),
                                   next((w.get("waterway") for w in ways.get(k, [])), None))}
    print(f"#{k}: {targets[k]}")

# Which state or province is each training record in?
recs = pd.concat([pd.read_csv(D / "pbdb" / "icewave_east_expanded.csv")[["latitude", "longitude"]],
                  pd.read_csv(D / "model" / "icewave_v2_training.csv").query("presence == 1")[["latitude", "longitude"]]]
                 ).drop_duplicates().reset_index(drop=True)
q = ["[out:json][timeout:600];"]
for i, r in recs.iterrows():
    q.append(f'make mark id="{r.latitude:.6f},{r.longitude:.6f}"; out;')
    q.append(f'is_in({r.latitude:.6f},{r.longitude:.6f})->.a; area.a[boundary=administrative][admin_level=4]; out tags;')
time.sleep(10)
admin = {k: (v[0].get("name:en") or v[0].get("name")) if v else None for k, v in tagged(overpass("\n".join(q))["elements"]).items()}
print("records by state/province:", pd.Series(admin).value_counts(dropna=False).to_dict())

# Coyote Canyon Mammoth Site: S Clodfelter Rd, Kennewick (McBones). Take the road, and anything named for the site.
time.sleep(10)
cc = overpass("""[out:json][timeout:120];
(way["highway"]["name"~"Clodfelter"](46.0,-119.4,46.25,-119.0);
 nwr["name"~"Coyote Canyon|McBones|Mammoth",i](46.0,-119.4,46.25,-119.0););
out center tags;""")["elements"]
named = [e for e in cc if "Clodfelter" not in e.get("tags", {}).get("name", "")]
for e in cc:
    c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
    print("  coyote canyon candidate:", e["type"], e["id"], e.get("tags", {}).get("name"), c)
site = None
for want in ("mammoth site", "mcbones"):                  # the site itself, not Mammoth Drive or the canyon
    for e in named:
        if site is None and want in e.get("tags", {}).get("name", "").lower():
            c = e.get("center") or {"lat": e["lat"], "lon": e["lon"]}
            site = {"lat": round(c["lat"], 4), "lon": round(c["lon"], 4), "source": f"OpenStreetMap {e['type']} {e['id']}",
                    "name": e["tags"]["name"]}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(targets | {"records_admin": admin, "coyote_canyon": site,
                                     "coyote_canyon_candidates": [{"type": e["type"], "id": e["id"], "name": e.get("tags", {}).get("name"),
                                                                   **(e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")})} for e in cc]},
                          indent=1))
print(f"wrote {OUT.relative_to(ROOT)}")
