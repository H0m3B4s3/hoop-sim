#!/usr/bin/env python3
"""Regenerate ``hoopsim/data/names.json`` from public-domain, frequency-ranked name data.

Sources (public-domain at the root):
  - Surnames: US Census Bureau "most common surnames", via fivethirtyeight's mirror
    (rank-ordered, so the top N are recognizable and reflect real-world spread/diversity).
  - First names: US SSA yearly baby names (boys), via hadley/data-baby-names (aggregated by
    total share across years, then the most common are kept).

We take the most common names, title-case them, then merge in the curated international flavor
names already present in names.json so stars like Doncic / Jokic / Giannis stay in the pool.

This is a one-off dev tool — the committed ``names.json`` is what the game actually reads. Note:
editing the name pool changes seed->league reproducibility (see ``hoopsim/gen/namegen.py``), so
regenerate deliberately and re-baseline golden-seed tests afterward.

Usage:  python tools/gen_names.py     (requires network access)
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.request
from collections import defaultdict
from typing import List

SURNAMES_URL = ("https://raw.githubusercontent.com/fivethirtyeight/data/master/"
                "most-common-name/surnames.csv")
FIRSTNAMES_URL = ("https://raw.githubusercontent.com/hadley/data-baby-names/master/"
                  "baby-names.csv")

N_FIRST = 600
N_LAST = 2500

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hoopsim", "data", "names.json")


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:        # noqa: S310 (trusted URLs)
        return resp.read().decode("utf-8")


def _titlecase(name: str) -> str:
    """Title-case a possibly ALL-CAPS name, handling Mc/O'/hyphen prefixes reasonably."""
    s = re.sub(r"(^|[ '\-])([a-z])", lambda m: m.group(1) + m.group(2).upper(),
               name.strip().lower())
    if s.startswith("Mc") and len(s) > 2:                        # Mcdonald -> McDonald
        s = "Mc" + s[2].upper() + s[3:]
    return s


def _is_clean(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", name))


def first_names() -> List[str]:
    weight: dict = defaultdict(float)
    for row in csv.DictReader(io.StringIO(_fetch(FIRSTNAMES_URL))):
        if row.get("sex") == "boy" and _is_clean(row["name"]):
            weight[row["name"]] += float(row["percent"])
    ranked = sorted(weight, key=lambda n: weight[n], reverse=True)
    return [_titlecase(n) for n in ranked[:N_FIRST]]


def last_names() -> List[str]:
    out: List[str] = []
    for row in csv.DictReader(io.StringIO(_fetch(SURNAMES_URL))):   # already rank-ordered
        name = row["name"]
        if name and name != "NULL" and _is_clean(name):
            out.append(_titlecase(name))
        if len(out) >= N_LAST:
            break
    return out


def _merge(primary: List[str], extra: List[str]) -> List[str]:
    """Keep ``primary`` order; append curated ``extra`` names not already present (case-insensitive)."""
    seen = {n.lower() for n in primary}
    merged = list(primary)
    for n in extra:
        if n.lower() not in seen:
            merged.append(n)
            seen.add(n.lower())
    return merged


def main() -> None:
    with open(DATA_PATH, encoding="utf-8") as fh:
        curated = json.load(fh)
    first = _merge(first_names(), curated.get("first", []))
    last = _merge(last_names(), curated.get("last", []))
    with open(DATA_PATH, "w", encoding="utf-8") as fh:
        json.dump({"first": first, "last": last}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {len(first)} first names, {len(last)} last names -> {DATA_PATH}")


if __name__ == "__main__":
    main()
