#!/usr/bin/env python3
"""
Combine sweep reports into one verdict per parameter.

A parameter is verified if any pass heard it change. That is not
double-dipping: the baseline that makes one parameter audible can mask
another -- turning an LFO's depth up to reveal its waveform leaves the
depth itself near its limit -- so each pass sees a different subset, and
the union is the evidence.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--still", action="store_true",
                    help="list only what no pass has verified")
    ap.add_argument("--by-address", action="store_true",
                    help="count distinct CC and NRPN addresses rather than "
                         "parameters. This is the meaningful figure: the "
                         "machines share their CC numbers, so an "
                         "unverified machine parameter is usually an "
                         "address already verified under another name")
    args = ap.parse_args()

    best = {}
    for path in args.reports:
        with open(path) as handle:
            report = json.load(handle)
        label = report.get("settings", {}).get("profile", "?")
        # Descriptor moves are only evidence against the floor measured in
        # the same run. A verdict recorded before the harness passed those
        # thresholds through used looser fallbacks and over-reports, so the
        # recorded deltas are re-judged here.
        floors = (report.get("noise_floor", {})
                  .get("descriptor_thresholds") or {})
        for row in report["results"]:
            real = {
                label_: delta
                for label_, delta in (row.get("changed") or {}).items()
                if delta > floors.get(label_, float("inf"))
            }
            if real and row.get("verdict") != "RESPONDS":
                row = {**row, "verdict": "RESPONDS",
                       "evidence": "descriptors", "changed": real}
            key = f"{row['section']}.{row['param']}"
            prior = best.get(key)
            better = (
                prior is None
                or (row["verdict"] == "RESPONDS"
                    and prior["verdict"] != "RESPONDS")
                or (row["verdict"] == prior["verdict"]
                    and row.get("distance", 0) > prior.get("distance", 0))
            )
            if better:
                best[key] = {**row, "pass": label}

    verified = {k: v for k, v in best.items() if v["verdict"] == "RESPONDS"}
    remaining = {k: v for k, v in best.items() if v["verdict"] != "RESPONDS"}

    if args.still:
        for key in sorted(remaining):
            print(key)
        return 0

    if args.by_address:
        from elektron_mcp.digitone.data.sections import (
            FX_CHANNEL_SECTIONS, SECTIONS,
        )

        def address(section, spec):
            role = "fx" if section in FX_CHANNEL_SECTIONS else "track"
            if "cc_msb" in spec:
                return f"{role} CC {int(spec['cc_msb'])}"
            return (f"{role} NRPN {int(spec['nrpn_lsb'])}"
                    f":{int(spec['nrpn_msb'])}")

        claims, verified_addr = {}, set()
        for section, params in SECTIONS.items():
            for ident, spec in params.items():
                key = f"{section}.{ident}"
                addr = address(section, spec)
                claims.setdefault(addr, []).append(key)
                if key in verified:
                    verified_addr.add(addr)
        print(f"{len(verified_addr)}/{len(claims)} distinct addresses "
              f"verified against hardware")
        print("\nnot verified:")
        for addr in sorted(set(claims) - verified_addr):
            names = claims[addr]
            shown = ", ".join(names[:3])
            more = " ..." if len(names) > 3 else ""
            print(f"  {addr:18s} {shown}{more}")
        return 0

    print(f"{len(verified)}/{len(best)} parameters verified against audio")
    sections = {}
    for key, row in best.items():
        sections.setdefault(row["section"], []).append(row)
    for name in sorted(sections):
        rows = sections[name]
        got = sum(1 for r in rows if r["verdict"] == "RESPONDS")
        print(f"  {name:22s} {got:3d}/{len(rows)}")

    if remaining:
        print(f"\nnot yet heard to change ({len(remaining)}):")
        for key in sorted(remaining):
            row = remaining[key]
            print(f"  {key:38s} d={row.get('distance', 0):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
