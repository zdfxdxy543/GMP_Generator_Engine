"""Generate a controller_loop_ids-style JSON from a controller core structure.

Reads `controller_core_structure.json`, applies the mech normalization from the
exporter, and writes `controller_loop_ids_from_core.json` with single-property
entries and names/ids normalized (speed/position -> mech, position wins).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import controller_core_structure_exporter as core_exporter
import controller_loop_id_exporter as id_exporter


def canonical_id_for(name: str) -> str:
    name = (name or "").lower()
    canonical = id_exporter.CANONICAL_LOOP_IDS.get(name)
    if canonical:
        return canonical
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"loop_custom_{digest}"


def pick_property_from_original(original_blocks: list[dict[str, Any]], block_name: str) -> str:
    # Look in original blocks to decide if this loop was originally position or speed
    low = (block_name or "").lower()
    if "position" in low:
        return "position"
    if "speed" in low:
        return "speed"

    # fallback to library mapping by name
    props = id_exporter.LOOP_PROPERTY_LIBRARY.get(block_name)
    if props:
        return props[0]
    return f"{block_name}_input"


def main(requirement: str | None = None) -> int:
    base = Path(__file__).with_name("controller_core_structure.json")
    loop_ids_out = Path(__file__).with_name("controller_loop_ids_from_core.json")

    if not base.exists():
        print(f"missing {base}")
        return 2

    original = json.loads(base.read_text(encoding="utf-8"))

    # Apply the same mech-normalization used by exporter
    normalized = core_exporter._normalize_mechanical_structure(json.loads(json.dumps(original)))

    selected: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for blk in normalized.get("blocks") or []:
        name = str(blk.get("name") or "").strip()
        if not name or not name.endswith("_loop"):
            continue
        lname = name.lower()
        if lname in seen_names:
            continue
        seen_names.add(lname)

        cid = canonical_id_for(lname)

        # Determine property based on the original blocks: prefer position if present
        prop = pick_property_from_original(original.get("blocks") or [], name)

        selected.append({"id": cid, "name": lname, "properties": [prop]})

    # Keep deterministic ordering using existing exporter ordering rules
    selected.sort(key=lambda item: (id_exporter.LOOP_ORDER_RANK.get(item["name"], 99), item["id"]))

    # Resolve requirement precedence: CLI > controller_loop_ids.json > core structure requirement
    if requirement and requirement.strip():
        req_text = requirement.strip()
    else:
        try:
            req_text = json.loads(Path(__file__).with_name("controller_loop_ids.json").read_text(encoding="utf-8")).get("requirement")
        except Exception:
            req_text = original.get("requirement") or ""

    out = {
        "requirement": req_text,
        "language": "en",
        "selected_loops": selected,
    }

    loop_ids_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {loop_ids_out}")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate controller_loop_ids from core structure.")
    parser.add_argument("--requirement", type=str, help="Optional requirement text to include in the output.")
    args = parser.parse_args()
    raise SystemExit(main(requirement=args.requirement))
