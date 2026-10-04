# 🦣 Project IceWave

<p align="center">
  <img src="assets/icewave_flag.png" width="520" alt="Project IceWave flag: a green mammoth in a circle over blue waves, on navy, white and green bands"/>
</p>

<p align="center">
  <b>Where might the Ice Age's big animals be buried in the Northwest?</b><br>
  A random-forest model of where Pleistocene fossils turn up in Washington, Oregon, Nevada, Idaho and Montana, the places it pointed to, and an honest re-check of how far to trust it.
</p>

**[→ The page: brooksgroves.com/project-ice-wave](https://brooksgroves.com/project-ice-wave/)**

---

## The idea

Between roughly 18,000 and 15,000 years ago, Glacial Lake Missoula broke through its ice dam again and again, and floods poured across eastern Washington. Mammoths, bison, camels and horses were caught in them and buried where the water slowed and dropped its silt. The [Coyote Canyon Mammoth Site](https://www.mcbones.org/) south of Kennewick, excavated since 2008, is one of those places.

IceWave gathered Pleistocene vertebrate records from the Paleobiology Database (PBDB) and iDigBio, described the ground at each one (elevation, slope, aspect, ruggedness, topographic position and a rock score from the USGS State Geologic Map Compilation), and trained random forests to score other ground by how alike it looks: one model west of the Cascades (west of -121.5°) and one east of them.

## Rechecked, October 2026

I came back to this project and re-checked its headline numbers from the files in this repo ([`tools/check.py`](tools/check.py), which writes [`site/checks.json`](site/checks.json)). None of them survives, and the old README overstated all of them. I've kept it in the git history; the corrections are part of the record.

| What the README said | What the files show |
|---|---|
| **E02 "blind validation":** the #1 east target "called its shot" at the McBones Coyote Canyon mammoth dig, "at the predicted pixel" | E02 is **69 km** from the Coyote Canyon Mammoth Site, in the Yakima Valley, on a 1.1 km² patch that the elevation model has flattened to a single level, which is how it draws ponds, wetlands and rivers. The dig has run since 2008 (the bones were found in 1999), so it wasn't blind. Notebook 05 printed "[VALIDATED]" beside whichever target came first in the list. The final model (v4) ranks E02 **23rd of 25**. |
| **East v4: leave-one-out recall 36/40 (90%)** | Every random background point was given the same rock score, 0.5, instead of a lookup on the geologic map; none of the 40 fossil records has 0.5. So "rock score ≠ 0.5" means "fossil", perfectly. The re-check reproduces it the notebook's way (37/40 with today's scikit-learn). Take the rock score out and leave out whole places, and the model finds 10 of 28 places it hadn't seen only by also flagging 18% of random ground: **AUC 0.65**, where 0.5 is a coin toss. |
| **East v3: AUC 0.846**; "at 30 m resolution nearly every east target showed slope = 0, TRI = 0" | The 30 m elevation grid didn't reach Montana. All 18 Montana records and 5 in Idaho, **23 of the 40**, went into training with elevation, slope, aspect and ruggedness all exactly 0, and the model learned that zeros mean fossils. In the landscape, zero slope and zero ruggedness is what water looks like. **All six** top east targets have all-zero terrain, and all 10 zero-terrain targets with close-ups sit on dead-level water surfaces: Snake River reservoirs (E03 Lake Bryan, E04 Lower Granite Lake), Bear Lake (E16), Waptus Lake in the Alpine Lakes Wilderness (E21). E30 is on Lake Wallula, the Columbia. |
| **LiDAR TPI: 13 of 20 east targets "confirmed valley floor"** | By the notebook's own threshold (TPI < −5 m) it's 12, and **8 of those 12** are water surfaces: a river is the bottom of its valley. On its own TPI doesn't separate fossil places from background at all (AUC 0.51). The "LiDAR" is USGS 3DEP elevation fetched at about 14 m. |
| **West AUC 0.890 ± 0.105** | The west model had the same rock-score shortcut (background all 0.4; 22 of 31 fossil records differ). Leaving out whole places it scores AUC 0.85 with the rock score and **0.63 on terrain alone**, where it finds 11 of 19 places but flags 34% of random ground. Six of its 31 records, filed under Washington, are in British Columbia. |
| **West training data** | 6 of the west model's 31 records aren't fossils at all: they're museum specimens of modern animals (iDigBio "PreservedSpecimen", in mammal collections), including a horse, bison and elk from Seattle's Woodland Park Zoo and elk collected in the Hoh valley in 1915. The harvest never asked iDigBio for fossils only. Listed in [`data/checks/modern_records.json`](data/checks/modern_records.json). |
| **"Pleistocene megafauna"** | 16 of the east model's 40 records aren't big animals: a gull, a chub, a horned lizard, a snapping turtle, a beaver, a fox, a cottontail, a human, and rodents. 18 of the 40 are from Montana, which has none of the targets; Washington, which has most of them, has 5. |

**What still holds:** the idea. The floods really did bury big animals in the Columbia Basin, and Coyote Canyon shows it. The PBDB and iDigBio harvest across five states is real and reusable, and the re-check is reproducible. What IceWave doesn't have is a target worth driving to. **The targets are a record of what went wrong, not a field guide.** Several are in the middle of a river or a reservoir.

## Where to look instead: Washington's pits

Washington's best-known Ice Age finds all came out of someone's dig: the Coyote Canyon mammoth from a rock pit south of Kennewick (1999), the Sequim mastodon from a farm pond dug with a backhoe (1977), the Wenas Creek mammoth from road building near Selah (2005), a mammoth tusk from a Seattle apartment excavation (2014). So instead of guessing at terrain, IceWave now lists where the digging is happening.

[`tools/v5/quarries.py`](tools/v5/quarries.py) takes every active surface-mine permit in Washington (WA DNR) and looks up what each pit is cut into on the state's 1:100,000 geologic map. Of 859 pits, **478 are in Ice Age ground**: 117 in outburst-flood deposits, 25 in loess, 10 in lake and bog deposits, 326 in glacial deposits. 292 are in bedrock, mostly Columbia River basalt. The Coyote Canyon pit (Mahaffey Rock Pit #1) is one of the 25 on loess; that's a check of the rules, not a test, since I wrote them knowing it. The script runs every Monday and lists any **new permits**, because a new pit in Ice Age ground is the time to ask the operator to watch for bone.

The output is [`data/v5/quarries.csv`](data/v5/quarries.csv), with recorded Ice Age finds (PBDB and iDigBio, fossil specimens only) in `data/v5/finds.geojson`. These are working pits on private or leased land: don't go in. If a machine turns up bone, stop, photograph it where it lies, and call the [Burke Museum](https://www.burkemuseum.org/).

## The page

[`index.html`](index.html) is the project's page, served by GitHub Pages: a map of the training records and the 42 targets coloured by what's actually there, the re-check, a targets table, the 20 terrain close-ups, and the real mammoth. It reads only the files in [`site/`](site/):

| Script | Writes | When |
|---|---|---|
| [`tools/pbdb.py`](tools/pbdb.py) | `site/pbdb_live.json`: every Pleistocene vertebrate PBDB lists in the five states (the same query notebook 04 ran) | Mondays, by GitHub Actions |
| [`tools/osm.py`](tools/osm.py) | `data/checks/osm_targets.json`: the water, rivers and protected areas OpenStreetMap maps at each target, the state or province of each training record, and the Coyote Canyon site's outline | once; the answer is committed |
| [`tools/build.py`](tools/build.py) | `site/targets.geojson`, `site/known.geojson`, `site/panels/`, and `site/live.json` (PBDB places the model never saw, and anything within 10 km of a target) | after each PBDB check |
| [`tools/v5/quarries.py`](tools/v5/quarries.py) | `data/v5/`: Washington's active pits by the ground they cut, and new permits since last week | Mondays |
| [`tools/check.py`](tools/check.py) | `site/checks.json`: the re-check above (random forests with the notebooks' settings, 200 trees instead of 500 so it runs in a few minutes; scikit-learn pinned at 1.9.1, because the counts shift by a record or two between versions) | after each PBDB check |

The first PBDB check (October 4, 2026) found 539 records, the same count notebook 04 harvested, at 69 places; 9 of them, mostly marine fish on the southern Oregon coast, are more than 1 km from anything IceWave learned from.

```bash
pixi run -e site pbdb      # or: python tools/pbdb.py
pixi run -e site build
pixi run -e site check
pixi run -e site serve     # then open http://localhost:8000
```

## The notebooks

The models were built in Jupyter (`pixi run lab`). The 30 m elevation mosaic, slope rasters and the SGMC geology are git-ignored, so the notebooks need them re-downloaded.

| Notebook | What |
|---|---|
| `01_pbdb_harvester`, `01b_idigbio_harvester`, `01c_merge_and_enrich` | PBDB and iDigBio records for eight large-mammal genera in WA, OR and NV |
| `02_terrain_analysis` | 30 m elevation, slope, aspect and ruggedness at the records |
| `03_ml_model`, `03b_ml_model_v2`, `03c_ml_model_v2_split` | v1 and v2 random forests; v2 split at the Cascades (-121.5°) |
| `04_east_model_improvement` | v3 east: every Pleistocene vertebrate in five states, 40 records with terrain |
| `05_lidar_terrain_analysis` | 3DEP close-ups at about 14 m and TPI for 20 east targets |
| `06_east_model_v4_tpi`, `07_east_model_v4_proper_auc` | v4 east: TPI added; a new background grid; leave-one-out |

The field reports in `outputs/` (PDF, KMZ, GPX) are kept as history. They carry the old claims, and the KMZ and GPX waypoints include the targets on water.

## Data

| Source | What |
|---|---|
| [PBDB](https://paleobiodb.org) | Pleistocene vertebrate occurrences in WA, OR, NV, ID and MT (checked weekly) |
| [iDigBio](https://www.idigbio.org) | museum specimen records for the same genera |
| USGS 3DEP | 30 m elevation for the models; about 14 m for the close-ups |
| [USGS SGMC](https://www.usgs.gov/data/state-geologic-map-compilation-sgmc-conterminous-united-states) | lithology for the rock score (not included; over 1 GB) |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | water and place names for the re-check |

## What's next

IceWave needs rebuilding, not tuning:

- Measure every input the same way at fossil records and background points: one elevation source, and a real geologic-map lookup at both.
- Mask out water before scoring, so a flattened river can never be a target.
- Train on the animals it's meant to find, and drop records whose coordinates are only a county centroid.
- Test by leaving out whole places, as `tools/check.py` does, and report that number.
- Score the whole landscape, then see where places the model never saw, like Coyote Canyon, land.

## If you go

Vertebrate fossils on federal land can only be collected under a permit (Paleontological Resources Preservation Act). Much of the Columbia Basin, the Willamette Valley and Puget Sound is private land, so ask before you walk. If you find bone, leave it in place, photograph it with something for scale, note where it is, and tell the landowner or land agency, or a museum such as the Burke in Seattle. Coyote Canyon is an active, permitted dig on private land; see it on a [McBones tour](https://www.mcbones.org/).

---

<p align="center"><sub>Project IceWave · Brooks Groves · <a href="https://brooksgroves.com">brooksgroves.com</a> · sequel to <a href="https://github.com/bdgroves/project-paleowave">PaleoWave</a></sub></p>
