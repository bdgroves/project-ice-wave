"""
Weekly: ask the Paleobiology Database for every Pleistocene vertebrate occurrence in the five states
IceWave covers (the same query notebook 04 ran in March 2026), and write site/pbdb_live.json.

tools/build.py compares it with what the model was trained on, so the page says plainly when PBDB
lists a place the model never saw, and when anything turns up near one of the targets.

    python tools/pbdb.py
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATES = ["Washington", "Oregon", "Nevada", "Idaho", "Montana"]
BASE = "https://paleobiodb.org/data1.2/occs/list.json?"
KEEP = ("occurrence_no", "collection_no", "identified_name", "accepted_name", "accepted_rank", "class", "order",
        "family", "genus", "early_interval", "late_interval", "max_ma", "min_ma", "lng", "lat", "state", "county",
        "formation", "ref_author", "ref_pubyr", "geogscale", "latlng_precision")

recs, urls = [], []
for st in STATES:
    url = BASE + urllib.parse.urlencode({"state": st, "interval": "Pleistocene", "base_name": "Vertebrata",
                                         "show": "coords,loc,class,ref,acc", "vocab": "pbdb", "limit": "all"})
    urls.append(url)
    req = urllib.request.Request(url, headers={"User-Agent": "IceWave (github.com/bdgroves/project-ice-wave)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        js = json.loads(r.read())
    got = [{k: x.get(k) for k in KEEP if x.get(k) is not None} | {"state_query": st} for x in js.get("records", [])]
    recs += got
    print(f"PBDB {st}: {len(got)} Pleistocene vertebrate occurrences")
    time.sleep(1)

out = {"checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "sources": urls, "records": recs}
(ROOT / "site").mkdir(exist_ok=True)
(ROOT / "site" / "pbdb_live.json").write_text(json.dumps(out, indent=0, ensure_ascii=False))
print(f"PBDB: {len(recs)} records in all")
