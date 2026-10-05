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

## Parameter payload (FM Drum: decoded for ONE preset only)

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

For the calibration preset these 30 offsets decode exactly, with no
ambiguity, and the order matches the device's own page layout. **They do not
generalise** -- see "What does not work" below.

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

## Content hash (solved)

The device validates payload integrity and refuses an upload it does not
like with `Content hash mismatch`. The hash is:

```
CRC-32, seeded 0xffffffff, over payload[32 : len-12]
stored big-endian at payload[len-12 : len-8]
```

Verified against six presets taken off the device: every stored value matches
the computed one. Elektroid's own `elektron_crc()` uses the same seed, which
is what suggested it after plain CRC-32 failed.

The footer is the last 16 bytes:

| bytes | meaning |
|---|---|
| `[-16:-12]` | zero padding |
| `[-12:-8]` | content hash (above) |
| `[-8:-4]` | `payload_length - 43` |
| `[-4:]` | constant marker `aa a1 da aa` |

There is also a length field at payload offset 34 holding
`payload_length - 51`.

Resealing after an edit makes the device **accept** the upload. That part
works.

## What does not work

Writing parameters by absolute offset. Evidence:

- An upload of a 271-byte payload came back from the device as **266 bytes**.
  The device parses and re-serialises a preset on save rather than storing
  the bytes verbatim.
- Payload length varies widely between presets: 247, 266, 271, 285, 296,
  302, 334 bytes observed.
- A structural search for the block -- 16-bit words with a zero high byte --
  finds it in no preset except the calibration one, and even there lands two
  bytes off. The high byte is not reliably zero: at offset 84 it is 0x2E.

Taken together the payload is probably tagged or variable-length, not a flat
array. The 30 offsets are an accurate description of one file, not of the
format.

`apply_parameters` therefore refuses any payload whose length differs from
the calibrated 271 bytes, and `save_current_as_preset` reads back what the
device actually stored and reports whether the parameters survived, rather
than trusting an accepted upload.

## Writing parameters: what the probes established

Single-variable uploads to a scratch slot, each one verified by downloading
what the device stored.

**The round trip is lossless.** Uploading a preset byte-for-byte as the
device supplied it returns the same 271 bytes with exactly one byte changed:
offset 24, which behaves as a save counter. So any other difference is
attributable to the edit, and the body is not re-encoded in general. An
earlier version of this document concluded the opposite; that was wrong.

**A non-zero write lands exactly.** Changing one parameter byte to a non-zero
value returns the same length with that byte changed and nothing else moved
(bar the CRC, which the device recomputes). The offsets are correct.

**A zero costs one byte.** Writing 0 into a parameter returns a payload one
byte shorter, with everything after that point shifted. Zeros are stored
compactly rather than as a full 16-bit word. This is what made the first
attempt fail: the patch contained five zero values and the device returned a
payload exactly five bytes shorter.

**Substituting 1 for 0 is not sufficient.** Writing all 30 values with zeros
replaced by 1 landed 26 of 30, including the whole of page 1, which had never
worked before. Four drifted: ph_c came back as 0 despite being sent as 1, and
the three parameters after it shifted by one slot -- consistent with ph_c
being normalised to 0 and then stored compactly. So some parameters constrain
or normalise their value, and a normalised 0 re-triggers the compaction.

### State

- 26 of 30 FM DRUM parameters are writable today.
- The remaining few need one probe sweep each: write every value across the
  parameter's range, see which are stored verbatim and which normalise.
- At roughly fifteen seconds per probe this is bounded work, and the harness
  does it reliably: upload, download, compare.

### Method that worked

Change exactly one thing per upload and verify against what the device
stored. Five hypotheses were tested and rejected by inspection alone
(checksum location, trailing footer hash, stored-deflate framing, zlib in the
payload, wholesale re-encoding). None survived contact. The single-variable
probe found the mechanism in two uploads.

## What works today

- Download, back up, copy and clear presets and projects on the device.
- Read a device-produced preset's parameters at the calibrated payload length.
- Compute and reseal the content hash, so an edited preset is accepted.
- Write non-zero parameter values, verified by read-back.
- `apply_parameters` refuses an uncalibrated payload length, and
  `save_current_as_preset` reports whether the parameters actually survived
  rather than trusting an accepted upload.

For keeping a sound, the patch store remains the reliable route: it replays
the values over CC in about a second.
