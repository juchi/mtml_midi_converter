# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Single-file Python tool converting MTML (Music Text Markup Language, a text music notation designed for LLM generation) into MIDI.

- `MTML_spec.md` — format specification v1.0. **Source of truth** for the format.
- `mtml_to_midi.py` — parser + MIDI writer + CLI. Only dependency: `mido`.

There are no tests, no packaging (`requirements.txt` / `pyproject.toml`) and no sample `.mtml` files in the repo yet.

## Commands

```bash
pip install mido
python mtml_to_midi.py input.mtml output.mid [--verbose]
```

Quick smoke test: the complete example in section 8 of `MTML_spec.md` is a valid input. On Windows, set `PYTHONIOENCODING=utf-8` if the console chokes on the `✓` printed on success.

## Architecture (`mtml_to_midi.py`)

Two stages, both pure functions:

1. **Parse** — `parse_mtml(text) -> (SongHeader, list[TrackDef])`
   - Line-by-line, keyword-driven (`@SONG`, `@TRACK`, `@BAR`, `N`, `CHORD`, `REST`, `CC`).
   - Comments: `#` only counts as a comment at line start or after whitespace, so `F#3` survives.
   - `key=value` params via `parse_kv` / `RE_KV` (supports quoted values).
   - Durations are converted to ticks at parse time (`parse_duration`), so `@SONG ppq=` must appear before events.
   - Channels are stored **0-based** in `TrackDef.channel` (spec uses 1–16).
   - `CHORD` is expanded into notes at parse time (`parse_chord_symbol` + `apply_voicing`, intervals in `CHORD_INTERVALS`).
   - `BarDef.events` holds *groups* (`list[MtmlEvent]`); events in one group are meant to start at the same position.
2. **Build** — `build_midi(song, tracks) -> mido.MidiFile`
   - Type 1 file: track 0 = tempo / time signature / title, then one track per `@TRACK`.
   - Events are collected as `(absolute_tick, message)`, sorted (note_off before note_on at equal ticks), then converted to delta times.
   - Bar start = `(bar.number - 1) * ticks_per_bar`; a group advances the cursor by its longest duration; `CC` uses its own `t<pos>` and does not advance the cursor.

`convert()` and `main()` are thin wrappers (public API + argparse CLI).

## Known bugs / gaps vs. the spec

Verify before relying on these; fix them only when asked.

- **Polyphony with `|` is broken**: `parse_line_events` returns one group per `|` segment and `parse_mtml` extends `bar.events` with all of them, so simultaneous notes are played sequentially (and overflow into the following bars). The groups from one line should be merged into a single group.
- **Ties across bars don't work**: the `tied` dict is reset for every bar and open ties are closed at bar end, so the spec example (`N C4 1 85 tie` → next bar `N C4 1 85`) retriggers the note.
- **Mixed time signatures**: bar start uses the *current* bar's length times `(number - 1)`, which is wrong once bars of different lengths coexist. Per-bar `time=` is also not emitted as a MIDI meta event.
- `@SONG key=` and `@BAR chord=` are parsed but unused (no `key_signature` meta).
- `REST` inside a `|` group, and notes longer than the bar, are not validated.
- `--verbose` sets DEBUG; WARNINGs are always shown, and the success message is itself logged as a WARNING.
- Unused `lsb` / `msb` variables in the pitch-bend code.

## Conventions

- Code, comments and documentation in English. Existing code comments and log messages are in French; translate them when touching that code rather than adding more French.
- Keep the lenient error strategy from spec section 9: warn and continue, never crash on bad input lines.
- Unknown keys/keywords must stay silently ignored (forward compatibility).
- When changing the format, update `MTML_spec.md` alongside the code.
