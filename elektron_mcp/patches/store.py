"""
Patch state tracking and storage.

The Digitone does not report its parameter values back, so the only way to
know what a track is set to is to remember what was sent. Every section tool
records into TRACK_STATE, which makes snapshot, recall, diff, morph and
mutate possible without reading the device.

A snapshot is therefore what this server set, not necessarily the whole sound:
anything changed on the hardware itself is invisible here. Recall is still
exact for the parameters it owns.
"""

import json
import random
import time
from pathlib import Path

PATCH_DIR = Path.home() / ".elektron-mcp" / "patches"


class TrackState:
    """Last value this server sent for every (track, section, parameter)."""

    def __init__(self):
        self._state: dict[int, dict[str, dict[str, int]]] = {}

    def record(self, track: int, section: str, values: dict[str, int]) -> None:
        sections = self._state.setdefault(track, {})
        sections.setdefault(section, {}).update(values)

    def get(self, track: int) -> dict[str, dict[str, int]]:
        return {s: dict(v) for s, v in self._state.get(track, {}).items()}

    def clear(self, track: int | None = None) -> None:
        if track is None:
            self._state.clear()
        else:
            self._state.pop(track, None)

    def parameter_count(self, track: int) -> int:
        return sum(len(v) for v in self._state.get(track, {}).values())


TRACK_STATE = TrackState()


def _path(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
    if not safe:
        raise ValueError(f"patch name {name!r} has no usable characters")
    return PATCH_DIR / f"{safe}.json"


def save(name: str, sections: dict, source_track: int, note: str = "") -> str:
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(name)
    payload = {
        "name": name,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_track": source_track,
        "note": note,
        "sections": sections,
    }
    path.write_text(json.dumps(payload, indent=2))
    return str(path)


def load(name: str) -> dict:
    path = _path(name)
    if not path.exists():
        raise FileNotFoundError(f"no patch named {name!r}")
    return json.loads(path.read_text())


def names() -> list[dict]:
    if not PATCH_DIR.exists():
        return []
    out = []
    for p in sorted(PATCH_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        out.append(
            {
                "name": d.get("name", p.stem),
                "saved_at": d.get("saved_at"),
                "source_track": d.get("source_track"),
                "note": d.get("note", ""),
                "parameters": sum(len(v) for v in d.get("sections", {}).values()),
            }
        )
    return out


def delete(name: str) -> bool:
    path = _path(name)
    if not path.exists():
        return False
    path.unlink()
    return True


def diff(a: dict, b: dict) -> dict:
    """Parameter-level difference between two snapshots' section maps."""
    out: dict[str, dict] = {}
    for section in sorted(set(a) | set(b)):
        pa, pb = a.get(section, {}), b.get(section, {})
        changed = {
            k: {"from": pa.get(k), "to": pb.get(k)}
            for k in sorted(set(pa) | set(pb))
            if pa.get(k) != pb.get(k)
        }
        if changed:
            out[section] = changed
    return out


def morph(a: dict, b: dict, amount: float) -> dict:
    """Interpolate between two snapshots.

    amount 0.0 returns a, 1.0 returns b. Parameters present in only one
    snapshot are taken as-is, since there is nothing to interpolate toward.
    """
    amount = max(0.0, min(1.0, amount))
    out: dict[str, dict] = {}
    for section in sorted(set(a) | set(b)):
        pa, pb = a.get(section, {}), b.get(section, {})
        merged = {}
        for k in sorted(set(pa) | set(pb)):
            if k in pa and k in pb:
                merged[k] = int(round(pa[k] + (pb[k] - pa[k]) * amount))
            else:
                merged[k] = pa.get(k, pb.get(k))
        out[section] = merged
    return out


def mutate(
    sections: dict,
    amount: float,
    only: list[str] | None = None,
    rng: random.Random | None = None,
) -> dict:
    """Random offsets around a snapshot.

    amount is the spread as a fraction of full range, so 0.1 is +/-12 MIDI
    units. `only` restricts mutation to named parameters, which is how you
    explore one dimension of a sound without disturbing the rest.
    """
    rng = rng or random.Random()
    spread = int(round(max(0.0, min(1.0, amount)) * 127))
    out: dict[str, dict] = {}
    for section, params in sections.items():
        out[section] = {
            k: (
                v
                if only is not None and k not in only
                else max(0, min(127, v + rng.randint(-spread, spread)))
            )
            for k, v in params.items()
        }
    return out
