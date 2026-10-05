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

## Parameter payload (FM Drum: decoded)

Payload length varies by machine: 334 bytes for a WAVETONE/FM TONE preset,
271 bytes for an FM DRUM one. Structure:

- `ac 11 d3 03` at offset 0 — magic or format version.
- An ASCII version-like string (`0059`) near offset 11.
- `be ef ba ce` at offset 0x28 — a marker.
- The preset name repeated as ASCII at offset 0x34.
- 110 zero bytes, 109 distinct values, 39 bytes above 0x7F, so this is raw
  binary rather than the 7-bit-safe encoding used on the wire.

## The parameter block

Parameters are a contiguous array of **16-bit words**, one per parameter, with
the 7-bit MIDI value in the **odd (second) byte** of each word:

```
offset 85 + (n * 2)  ->  parameter n
```

For FM DRUM the order matches the device's own page layout exactly, and all
30 parameters were located with no ambiguity:

| offset | parameter | | offset | parameter |
|---|---|---|---|---|
| 85 | tune | | 115 | mod2 |
| 87 | stim | | 117 | hold |
| 89 | sdep | | 119 | tran |
| 91 | fold | | 121 | base |
| 93 | algo | | 123 | wdth |
| 95 | fdbk | | 125 | ndec |
| 97 | op_c | | 127 | nlev |
| 99 | op_ab | | 129 | tlev |
| 101 | dec1 | | 131 | dec |
| 103 | end1 | | 133 | lev |
| 105 | ratio1 | | 135 | ph_c |
| 107 | mod1 | | 137 | nrst |
| 109 | dec2 | | 139 | nrm |
| 111 | end2 | | 141 | nhld |
| 113 | ratio2 | | 143 | gran |

Note `fold` precedes `algo` and `ratio1` follows `end1`, which is not the
order the parameter maps in this repo list them in -- the payload follows the
device's page layout, not the CC numbering.

### How this was established

A calibration patch was sent over CC giving every parameter a distinct value,
saved on the device once, downloaded and unzipped. Each parameter was then
located by searching the payload for its known value. Restricting the search
to odd offsets inside the block removed every spurious match, including for
the 0/1 toggles whose values appear all over the file.

Worth repeating per machine: FM TONE, WAVETONE and SWARMER will have their
own orders and payload lengths. The same calibration method applies.

### Still unknown

- Bytes before offset 85: a header carrying magic (`ac 11 d3 03`), a marker
  (`be ef ba ce`), a version-like ASCII string and the preset name.
- Whether the even byte of each word is ever non-zero, i.e. whether any
  parameter exceeds 7 bits in storage.
- The filter, amp, FX and LFO blocks, which were part of the same calibration
  but have not yet been located.

## What this unlocks

Writing a preset file into a slot needs no interaction with the device
(`DATA_WRITE_*` in the protocol, `upload` in Elektroid), so once the payload
can be generated, saving a sound is fully automatable. Committing live
parameter state has no MIDI equivalent -- slot-to-RAM exists, RAM-to-slot does
not -- but authoring a file sidesteps that entirely.
