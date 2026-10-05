# Elektron MCP

A Model Context Protocol (MCP) server that allows Claude and other MCP-compatible LLMs to interact with and control Elektron synthesizers via MIDI.

#### If you have a Moog Sub37/Subsequent37, check out our dedicated MCP server for it at [moog-sub37-mcp](https://github.com/zerubeus/moog-sub37-mcp).

#### A web-based version of this MCP server can be found at [senthgenie.com](https://www.synthgenie.com/). (You can ask for API key for free on discord)

#### If you want help or would like to contribute to development, please join our [Discord community](https://discord.gg/ZFuSuegBMS).

# Prompt examples

```
"Use Digitone MCP to design an evolving dark pad using the Wavetone machine on track 1."
"Use Digitone MPC to design a Dark thick pad using Wavetone machine on track 1."
```

Only Wavetone machine is supported for now, other machines will be added soon, stay tuned!

## Features

- [x] Complete MIDI control interface for the Elektron Digitone synthesizer
- [x] Structured controllers for all Digitone sound engines:
  - [x] Wavetone (waveshaping synthesis)
  - [ ] FM Tone (FM synthesis)
  - [ ] FM Drum (percussive FM synthesis)
  - [ ] Swarmer (unison/swarm synthesis)
- [x] Comprehensive parameter control for:
  - [x] All filter types
    - [x] MultiMode
    - [ ] Lowpass4
    - [ ] Equalizer
    - [ ] LegacyLpHp
    - [ ] CombMinus
    - [ ] CombPlus
    - [ ] BaseWidth
  - [x] Amplitude and envelope settings
  - [x] Effects processing (delay, reverb, chorus, bit reduction, etc.)
  - [x] LFOs control
- [x] MCP server exposing all synth parameters as tools for LLMs
- [x] Type-safe parameter validation using Pydantic
- [x] Modular architecture for easy extension to other Elektron devices

## Fork additions

This fork extends upstream from one machine to the whole instrument, and adds
a closed sound-design loop.

**Full parameter coverage.** All 184 parameters are reachable: FM Drum, FM
Tone, Swarmer and Wavetone, all seven filter types, amp, fx and LFO 1-3.
Each section gets one batch tool (`set_fm_drum(track, gran=78, nlev=110)`)
generated from the parameter maps, so a patch is one call rather than thirty.
Values can be given as raw MIDI or in device units (`units="display"` turns
`tune=24` into +24 semitones), optionally over 14-bit NRPN.

**It can hear itself.** The Digitone II is a 2-channel USB audio input, so
`audition` triggers a note, captures the result and returns descriptors --
spectral centroid, band energies, spectral flatness (noise versus tone), T20
decay, onset count. `score_against_reference` scores a patch against a WAV
using a multi-resolution log-STFT distance, which makes automated patch
matching possible.

**Playback.** `play_note`, `hold_note`/`release_note`, `play_sequence` (with
optional per-step parameter jitter), `all_notes_off`, `set_program`. Upstream
had no way to trigger a note at all.

**Patches.** `snapshot_patch`, `recall_patch`, `diff_patches`,
`morph_patches`, `mutate_patch`. These work from what the server has sent,
since the Digitone does not report values back.

**MIDI learn.** `start_midi_capture` / `get_captured_midi` report which CC or
NRPN a control emits, mapped back to the parameter maps. Needs `Send CC/NRPN`
enabled in the Digitone's MIDI config.

### Known limits

- Machine selection has no MIDI CC, so choosing FM DRUM on a track is a
  manual step on the device.
- Patch snapshots cover what this server sent, not anything changed on the
  hardware.
- LFO3's modulation destination enum is missing from the data maps (test
  marked xfail); LFO1 and LFO2's are present but unverified against the manual.
- Onset counting is reliable for percussive material and approximate for
  sustained sounds.

### Bugs fixed from upstream

- FM Tone operator B's envelope used operator A's CC numbers (48-51), so
  setting B silently moved A. Corrected to 52-55.
- Nested parameters were registered only as groups, while the controllers
  address them as `A.atk` -- every nested FM Tone setter raised.
- The test suite asserted `nrpn_lsb` as a string after a refactor made it an
  int; 22 of 24 tests were failing.

## Demo

Watch Claude control the Elektron Digitone synthesizer in real-time:

[![Claude controlling Elektron Digitone](https://img.youtube.com/vi/EXf6lOTjla8/0.jpg)](https://www.youtube.com/watch?v=EXf6lOTjla8)

## Installation and Usage

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) for package management
- An Elektron Digitone connected via USB
- Claude Desktop app (for full integration)

### Installing Dependencies

uv is mandatory for this project so start by installing it:

#### For macOS:

```bash
brew install uv
```

#### For Windows:

Follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/)

### 3. Installing with Claude Desktop

To use with Claude AI, add the MCP server configuration in Claude Desktop:

⚠️ **Important**: You don't need to clone the repository or install the packages, all you need is to add the MCP server configuration to your claude_desktop_config.json file the MPC server is already published on pypi.

Go to Claude > Settings > Developer > Edit Config > claude_desktop_config.json to include the following:

```json
{
  "mcpServers": {
    "Digitone 2": {
      "command": "uvx",
      "args": ["elektron-mcp"]
    }
  }
}
```

## Architecture

- **Base Controllers**: Common functionality abstracted into base classes
- **Specialized Controllers**: Dedicated controllers for each synth engine and module
- **MCP Tools**: Direct interface between LLMs and the synth's parameters
- **MIDI Interface**: Reliable communication with Digitone hardware

## Implementation Details

This library uses:

- **FastMCP**: For exposing synth controls to LLMs
- **Pydantic models**: For data validation, serialization, and type safety
- **mido**: For MIDI communication

## Use Cases

- Allow Claude and other LLMs to create and modify sounds on the Digitone
- Programmatically control Digitone parameters for automated sound design
- Bridge between AI-generated music and hardware synthesis

## Future Extensions

- Support for additional Elektron devices (Analog Four, Octatrack, etc.)
- Pattern sequencing and automation
- Sound preset management
- Additional synthesis parameters
