# Digitone II preset format (`.dn2pst`)

Observed by downloading a preset off the device with `elektroid-cli`. Enough
is known to author the container and metadata; the parameter block is not yet
decoded.

## Container

A ZIP archive (`PK\x03\x04`). A 691-byte preset file contained:

| entry | size | contents |
|---|---|---|
| `manifest.json` | 269 B | plain JSON metadata |
| `<preset name>` | 334 B | binary parameter payload |

The payload entry is named after the preset, and `manifest.json` names it in
its `Payload` field.

## manifest.json

Plain, legible JSON — fully authorable:

```json
{
  "FormatVersion": "1.0",
  "ProductType": ["43"],
  "Payload": "<preset name>",
  "FileType": "Sound",
  "FirmwareVersion": "1.11",
  "MetaInfo": { "Tags": ["DEEP", "LEAD"] }
}
```

`ProductType` 43 is the Digitone II, matching Elektroid's device table.
`FileType` is `Sound` for a preset. Tags are the ones shown on the device.

## Parameter payload (not yet decoded)

334 bytes for one Sound. Structure visible so far:

- `ac 11 d3 03` at offset 0 — magic or format version.
- An ASCII version-like string (`0059`) near offset 11.
- `be ef ba ce` at offset 0x28 — a marker.
- The preset name repeated as ASCII at offset 0x34.
- 110 zero bytes, 109 distinct values, 39 bytes above 0x7F, so this is raw
  binary rather than the 7-bit-safe encoding used on the wire.

## How to decode it

The cheap route needs one preset saved on the device whose parameter values
are already known, which makes the payload a Rosetta Stone:

1. Send a patch over CC, so every value is known (see the patch store).
2. Save it on the device, download it, unzip it.
3. Locate each parameter by searching the payload for its known value.
4. Verify by synthesising a modified preset, uploading it to a spare slot,
   loading it and auditioning: the measured sound must match what the bytes
   claim. The audio loop is the test harness.

Ambiguity is expected where several parameters share a value, so vary a few
deliberately to unique values before saving.

## What this unlocks

Writing a preset file into a slot needs no interaction with the device
(`DATA_WRITE_*` in the protocol, `upload` in Elektroid), so once the payload
can be generated, saving a sound is fully automatable. Committing live
parameter state has no MIDI equivalent -- slot-to-RAM exists, RAM-to-slot does
not -- but authoring a file sidesteps that entirely.
