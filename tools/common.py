"""Shared by build.py and check.py."""
import numpy as np

# What each east training genus is, in plain words; True = a large mammal, the project's stated target.
GENUS = {
    "Mammuthus": ("mammoth", True), "Mammut": ("mastodon", True), "Camelops": ("camel", True),
    "Hemiauchenia": ("llama", True), "Bison": ("bison", True), "Bootherium": ("musk ox", True),
    "Euceratherium": ("shrub ox", True), "Paramylodon": ("ground sloth", True),
    "Megalonyx": ("ground sloth", True), "Equini": ("horse", True), "Equus": ("horse", True),
    "Cervus": ("elk", True), "Rangifer": ("caribou", True), "Ursus": ("bear", True),
    "Bos": ("cattle (Bos)", True), "Oreamnos": ("mountain goat", True), "Odocoileus": ("deer", True),
    "Antilocapra": ("pronghorn", True), "Arctodus": ("short-faced bear", True),
    "Chroicocephalus": ("gull", False), "Allophaiomys": ("vole", False), "Urocitellus": ("ground squirrel", False),
    "Phrynosoma": ("horned lizard", False), "Cynomys": ("prairie dog", False), "Sylvilagus": ("cottontail", False),
    "Vulpes": ("fox", False), "Castor": ("beaver", False), "Chelydra": ("snapping turtle", False),
    "Siphateles": ("chub (fish)", False), "Perognathinae": ("pocket mouse", False), "Thomomys": ("pocket gopher", False),
    "Homo": ("human", False),
}


def km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(np.asarray(lon2) - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))
