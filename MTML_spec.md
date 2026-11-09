# MTML — Music Text Markup Language
**Text-based music notation format for AI generation → MIDI**
Version 1.0

---

## Overview

MTML is a hierarchical, human-readable text format designed to represent complete or partial musical compositions. It is optimized for generation by LLMs and for automatic conversion to MIDI.

**Core principles:**
- Every line starts with a keyword (no grammatical ambiguity)
- Parameters are `key=value` pairs
- Any unrecognized field is silently ignored (extensible)
- Comments (`#`) are allowed anywhere

---

## Global structure

An MTML file is made of nested blocks in this canonical order:

```
@SONG       ← (1) A single mandatory global block
  @TRACK    ← (N) One or more tracks
    @BAR    ← (M) One or more bars per track
      N / CHORD / CC / REST   ← events
```

---

## 1. `@SONG` block — Global header

Declares the global parameters of the composition. **Mandatory, unique, on the first line.**

```
@SONG tempo=<bpm> time=<num>/<den> key=<key> ppq=<ticks> [bars=<n>] [title="<text>"]
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tempo` | integer | yes | Beats per minute (e.g. `120`) |
| `time` | fraction | yes | Time signature (e.g. `4/4`, `3/4`, `6/8`) |
| `key` | string | yes | Key (e.g. `Cmaj`, `Amin`, `F#maj`, `Bbmin`) |
| `ppq` | integer | yes | Ticks per quarter note (resolution). Recommended value: `480` |
| `bars` | integer | no | Total number of bars (informative) |
| `title` | string | no | Title of the composition |

### Example

```
@SONG tempo=120 time=4/4 key=Cmaj ppq=480 bars=8 title="Study in C"
```

---

## 2. `@TRACK` block — Instrument track

Declares a MIDI track. **One `@TRACK` per instrument.** Tracks are independent and played simultaneously.

```
@TRACK id=<identifier> ch=<1-16> program=<0-127> [name="<text>"] [vol=<0-127>] [pan=<0-127>]
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | yes | Unique track identifier (e.g. `piano`, `bass`, `drums`) |
| `ch` | integer 1–16 | yes | MIDI channel. **Channel 10 is reserved for GM percussion** |
| `program` | integer 0–127 | yes | GM program number (instrument). See GM table below |
| `name` | string | no | Name displayed in the DAW |
| `vol` | integer 0–127 | no | Initial volume (CC7). Default: `100` |
| `pan` | integer 0–127 | no | Panning (CC10). Center: `64`, left: `0`, right: `127` |

### Common GM programs

| Program | Instrument | Program | Instrument |
|---------|------------|---------|------------|
| `0` | Acoustic Grand Piano | `32` | Acoustic Bass |
| `25` | Acoustic Guitar (steel) | `33` | Electric Bass (finger) |
| `40` | Violin | `48` | String Ensemble 1 |
| `56` | Trumpet | `73` | Flute |
| `0` (ch=10) | GM Percussion | — | — |

### Example

```
@TRACK id=piano ch=1 program=0 name="Grand Piano" vol=90 pan=64
@TRACK id=bass ch=2 program=32 name="Fingered Bass" vol=85 pan=40
@TRACK id=drums ch=10 program=0 name="Drums" vol=100 pan=64
```

---

## 3. `@BAR` block — Bar

Groups the events of one bar. **Contained in a `@TRACK`.**

```
@BAR <number> [chord=<symbol>] [time=<num>/<den>]
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `<number>` | integer | yes | Bar number, starts at `1` |
| `chord` | string | no | Reference chord of the bar (e.g. `Cmaj`, `G7`, `Dm7`, `F#dim`) |
| `time` | fraction | no | Local time signature (if different from `@SONG`) |

### Example

```
@BAR 1 chord=Cmaj
@BAR 5 chord=G7 time=3/4
```

---

## 4. Events — Notes and rests

### 4.1 Note: `N`

Single note event.

```
N <pitch> <duration> <velocity> [options]
```

#### Pitch

Format: `<note><accidental><octave>`

- Notes: `C D E F G A B`
- Accidentals: `#` (sharp), `b` (flat). No double accidentals.
- Octave: integer, `C4` = middle C (MIDI 60)

Valid examples: `C4`, `F#3`, `Bb5`, `G2`, `A#4`, `Eb6`

#### Duration

Symbolic values (expressed in quarter notes):

| Value | Name | Relative duration |
|-------|------|-------------------|
| `4` | Whole note | 4 quarter notes |
| `2` | Half note | 2 quarter notes |
| `1` | Quarter note | 1 quarter note |
| `1/2` | Eighth note | 1/2 quarter note |
| `1/4` | Sixteenth note | 1/4 quarter note |
| `1/8` | Thirty-second note | 1/8 quarter note |
| `1.5` | Dotted quarter note | 1.5 quarter notes |
| `3/4` | Dotted eighth note | 3/4 quarter note |

Or in absolute ticks: `t240` (= 1/2 quarter note at 480 PPQ)

#### Velocity

Integer `0–127`. Indicative references:
- `pp` → `30–40` | `p` → `50–60` | `mp` → `65–75`
- `mf` → `80–90` | `f` → `100–110` | `ff` → `115–127`

#### Optional options

| Option | Description | Example |
|--------|-------------|---------|
| `tie` | Ties this note to the next one (same pitch) | `N C4 1 80 tie` |
| `bend=<cents>` | Pitch bend in cents (−200 to +200) | `N E4 1 75 bend=+50` |
| `cc<n>=<val>` | Inline Control Change on this note | `N G3 2 90 cc7=64` |

#### Simultaneous notes (polyphony)

Several notes played at the same time are separated by `|` on the same line:

```
N C4 1 80 | N E4 1 75 | N G4 1 70
```

#### Full example

```
@BAR 1 chord=Cmaj
  N C4 1   80 | N E4 1   75 | N G4 1   70
  N D4 1/2 70
  N E4 1/2 68
  N C4 1   85 tie
@BAR 2 chord=Cmaj
  N C4 1   85
```

---

### 4.2 Chord: `CHORD`

Automatically generates a chord from its symbol. The parser derives the notes using the standard voicing (root position, octave 4 by default).

```
CHORD <symbol> <duration> <velocity> [voicing=<type>] [oct=<n>]
```

#### Supported chord symbols

| Suffix | Type | Example |
|--------|------|---------|
| *(none)* | Major | `C`, `F#` |
| `maj` | Major | `Cmaj` |
| `min` or `m` | Minor | `Amin`, `Am` |
| `7` | Dominant 7th | `G7` |
| `maj7` | Major 7th | `Cmaj7` |
| `m7` | Minor 7th | `Dm7` |
| `dim` | Diminished | `Bdim` |
| `aug` | Augmented | `Eaug` |
| `sus2` / `sus4` | Suspended | `Gsus4` |
| `9`, `m9`, `maj9` | 9th | `C9` |
| `/X` | Specific bass note | `G7/B`, `C/E` |

#### Options

| Option | Values | Description |
|--------|--------|-------------|
| `voicing` | `close` (default), `open`, `drop2` | Voice layout |
| `oct` | integer | Octave of the root (default: `4`) |

#### Example

```
@BAR 3 chord=Dm7
  CHORD Dm7 2 75
  CHORD G7  2 78
```

---

### 4.3 Rest: `REST`

```
REST <duration>
```

Example:

```
REST 1/2
```

---

### 4.4 Control Change: `CC`

Sends a MIDI Control Change message, positioned in ticks within the bar.

```
CC <number> <value> [t<position>]
```

- `<position>`: position in ticks from the start of the bar (default: `t0`)

#### Common CCs

| No. | Name |
|-----|------|
| `1` | Modulation wheel |
| `7` | Volume |
| `10` | Pan |
| `11` | Expression |
| `64` | Sustain pedal (0=off, 127=on) |

#### Example

```
@BAR 4
  CC 64 127 t0
  N C4 2 80
  CC 64 0 t480
```

---

## 5. GM Percussion (channel 10)

On channel 10, the pitch does not designate a pitch but a percussion sound:

| MIDI pitch | MTML note | Percussion |
|------------|-----------|------------|
| 35 | `B1` | Acoustic Bass Drum |
| 36 | `C2` | Bass Drum 1 |
| 38 | `D2` | Acoustic Snare |
| 42 | `F#2` | Closed Hi-Hat |
| 46 | `Bb2` | Open Hi-Hat |
| 49 | `C#3` | Crash Cymbal 1 |
| 51 | `Eb3` | Ride Cymbal 1 |

#### Basic groove example

```
@TRACK id=drums ch=10 program=0 name="Drums"
  @BAR 1
    N C2  1   100 | N F#2 1/2 80
    N F#2 1/2 75
    N D2  1   95  | N F#2 1/2 80
    N F#2 1/2 75
```

---

## 6. Comments

The `#` character at the start or in the middle of a line introduces a comment that is ignored during parsing.

```
# This is a comment
@BAR 1 chord=Cmaj  # inline comment
  N C4 1 80        # middle C, forte
```

---

## 7. Parsing rules

1. **Mandatory keyword at the start of a line** (after optional whitespace): `@SONG`, `@TRACK`, `@BAR`, `N`, `CHORD`, `REST`, `CC`
2. **Empty lines are ignored**
3. **Comments are ignored** (from `#` to end of line)
4. **Unknown keys are silently ignored** (forward compatibility)
5. **Canonical order**: `@SONG` → `@TRACK` → `@BAR` → events
6. **Polyphony**: `|` separates simultaneous notes on the same line; they share the same start position and their declared durations
7. **Position within the bar**: events follow each other sequentially, the current position advancing by the duration of each event (or by the maximum in the case of `|` polyphony)

---

## 8. Full example

```
# MTML example — 8 bars, 2 instruments
@SONG tempo=100 time=4/4 key=Cmaj ppq=480 bars=8 title="Simple study"

@TRACK id=piano ch=1 program=0 name="Grand Piano" vol=88 pan=64

  @BAR 1 chord=Cmaj
    N C4 1 80 | N E4 1 75 | N G4 1 70
    N C4 1 85

  @BAR 2 chord=G7
    N G3 1 78 | N B3 1 74 | N D4 1 70 | N F4 1 66
    N G3 1 80

  @BAR 3 chord=Amin
    N A3 1 76 | N C4 1 72 | N E4 1 70
    N A3 1 78

  @BAR 4 chord=F
    N F3 1 75 | N A3 1 70 | N C4 1 68
    N F3 1 77

  @BAR 5 chord=Cmaj
    N C4 1/2 82 | N E4 1/2 78
    N D4 1/2 75
    N E4 1/2 78
    N C4 1   85

  @BAR 6 chord=G7
    N G4 1/2 80
    N F4 1/2 76
    N D4 1/2 73
    N B3 1   79

  @BAR 7 chord=Amin
    N A3 2 78 | N C4 2 74 | N E4 2 70
    REST 2

  @BAR 8 chord=Cmaj
    N C4 4 90 | N E4 4 85 | N G4 4 80

@TRACK id=bass ch=2 program=32 name="Fingered Bass" vol=85 pan=40

  @BAR 1 chord=Cmaj
    N C2 1 100
    N C2 1 95

  @BAR 2 chord=G7
    N G1 1 98
    N G1 1 95

  @BAR 3 chord=Amin
    N A1 1 97
    N A1 1 93

  @BAR 4 chord=F
    N F1 1 98
    N C2 1 95

  @BAR 5 chord=Cmaj
    N C2 1 100
    N E2 1/2 90
    N G2 1/2 88

  @BAR 6 chord=G7
    N G1 1   100
    N D2 1/2 90
    N F2 1/2 88

  @BAR 7 chord=Amin
    N A1 2 98
    N E2 2 92

  @BAR 8 chord=Cmaj
    N C2 4 100
```

---

## 9. Errors and recovery

The parser must adopt a **lenient recovery** strategy:

- **Unrecognized line** → warning logged, line ignored, parsing continues
- **Missing required parameter** → default value if possible, otherwise the block is ignored
- **Invalid pitch** → note ignored, warning
- **Invalid duration** → duration = `1` (quarter note) by default, warning
- **Velocity outside [0-127]** → clamped to `0` or `127`

---

## 10. Conversion to MIDI ticks

```
ticks = duration_value × ppq

Examples at ppq=480:
  Whole note (4)      → 4 × 480 = 1920 ticks
  Half note (2)       → 2 × 480 = 960 ticks
  Quarter note (1)    → 1 × 480 = 480 ticks
  Eighth note (1/2)   → 0.5 × 480 = 240 ticks
  Sixteenth (1/4)     → 0.25 × 480 = 120 ticks
```

The absolute position of an event in the MIDI file = `(bar - 1) × ticks_per_bar + position_in_bar`

```
ticks_per_bar = (num / den) × 4 × ppq
Example 4/4 at ppq=480: (4/4) × 4 × 480 = 1920 ticks per bar
Example 3/4 at ppq=480: (3/4) × 4 × 480 = 1440 ticks per bar
```

---

*End of the MTML v1.0 specification*
