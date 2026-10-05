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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--still", action="store_true",
                    help="list only what no pass has verified")
    args = ap.parse_args()

    best = {}
    for path in args.reports:
        with open(path) as handle:
            report = json.load(handle)
        label = report.get("settings", {}).get("profile", "?")
        for row in report["results"]:
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
