# MTML → MIDI Converter

Converts **MTML** (Music Text Markup Language) files into standard MIDI files.

MTML is a line-based, human-readable text format for music notation, designed to be easy for LLMs to generate and for a program to convert to MIDI. The full format is defined in [`MTML_spec.md`](MTML_spec.md).

## Requirements

- Python 3.10+
- [`mido`](https://mido.readthedocs.io/)

```bash
pip install mido
```

## Usage

### Command line

```bash
python mtml_to_midi.py input.mtml output.mid
python mtml_to_midi.py input.mtml output.mid --verbose   # also show debug logs
```

On success it prints the output path, the number of tracks and the approximate duration.

### As a library

```python
from mtml_to_midi import convert, parse_mtml, build_midi

# Text → .mid file in one call
mid = convert(mtml_text, "output.mid")

# Or step by step
song, tracks = parse_mtml(mtml_text)   # SongHeader, list[TrackDef]
mid = build_midi(song, tracks)         # mido.MidiFile
mid.save("output.mid")
```

## MTML at a glance

```
# Comments start with '#'
@SONG tempo=100 time=4/4 key=Cmaj ppq=480 title="Simple study"

@TRACK id=piano ch=1 program=0 name="Grand Piano" vol=88 pan=64
  @BAR 1 chord=Cmaj
    N C4 1 80 | N E4 1 75 | N G4 1 70   # simultaneous notes
    N C4 1 85
  @BAR 2
    CHORD G7 2 78 voicing=open          # chord built from its symbol
    REST 1
    CC 64 127 t0                        # control change at tick 0 of the bar

@TRACK id=drums ch=10 program=0 name="Drums"
  @BAR 1
    N C2 1 100 | N F#2 1/2 80
```

| Keyword  | Syntax                                                       |
|----------|--------------------------------------------------------------|
| `@SONG`  | `tempo= time= key= ppq= [bars=] [title=]` — once, first line |
| `@TRACK` | `id= ch=1-16 program=0-127 [name=] [vol=] [pan=]`            |
| `@BAR`   | `<number> [chord=] [time=]`                                  |
| `N`      | `<pitch> <duration> <velocity> [tie] [bend=±cents] [ccN=val]`|
| `CHORD`  | `<symbol> <duration> <velocity> [voicing=close\|open\|drop2] [oct=]` |
| `REST`   | `<duration>`                                                 |
| `CC`     | `<number> <value> [t<tick-in-bar>]`                          |

- **Pitch**: `C4` = MIDI 60, accidentals `#` / `b` (e.g. `F#3`, `Bb5`).
- **Duration**: in quarter notes (`4`, `2`, `1`, `1/2`, `1.5`, `3/4`…) or absolute ticks (`t240`).
- **Channel 10** is GM percussion: the pitch selects the drum sound.

Parsing is lenient: unknown keys and keywords are ignored, invalid values fall back to defaults with a warning. See the spec for every detail.

## Output

- MIDI type 1, resolution = `ppq`.
- Track 0 holds tempo, time signature and title; one MIDI track per `@TRACK` follows.
- Each track starts with its program change plus CC7 (volume) and CC10 (pan).

## Known limitations

- The `key` of `@SONG` and the `chord` of `@BAR` are parsed but not written to the MIDI file.
- Per-bar `time=` changes are not emitted as MIDI time-signature events.
- See [`CLAUDE.md`](CLAUDE.md) for implementation gaps relative to the spec.
