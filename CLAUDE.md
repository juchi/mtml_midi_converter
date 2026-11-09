# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Single-file Python tool converting MTML (Music Text Markup Language, a text music notation designed for LLM generation) into MIDI.

- `MTML_spec.md` — format specification v1.0. **Source of truth** for the format.
- `mtml_to_midi.py` — parser + MIDI writer + CLI. Only runtime dependency: `mido`.
- `tests/test_mtml_to_midi.py` — pytest conformance suite against the spec.
- `examples/simple_study.mtml` — the complete example of spec section 8 (also used by the end-to-end test).

## Commands

```bash
pip install -r requirements-dev.txt          # mido + pytest
python -m pytest                             # run the test suite (config in pytest.ini)
python mtml_to_midi.py input.mtml output.mid [--verbose]
```

On Windows, set `PYTHONIOENCODING=utf-8` if the console chokes on the `✓` printed on success.

## Architecture (`mtml_to_midi.py`)

Two stages, both pure functions:

1. **Parse** — `parse_mtml(text) -> (SongHeader, list[TrackDef])`
   - Line-by-line, keyword-driven (`@SONG`, `@TRACK`, `@BAR`, `N`, `CHORD`, `REST`, `CC`).
   - Comments: `#` only counts as a comment at line start or after whitespace, so `F#3` survives.
   - `key=value` params via `parse_kv` / `RE_KV` (supports quoted values).
   - Durations are converted to ticks at parse time (`parse_duration`), so `@SONG ppq=` must appear before events.
   - Channels are stored **0-based** in `TrackDef.channel` (spec uses 1–16).
   - `CHORD` is expanded into notes at parse time (`parse_chord_symbol` + `apply_voicing`, intervals in `CHORD_INTERVALS`).
   - `BarDef.events` holds *groups* (`list[MtmlEvent]`): all `|`-separated events of one line form one group and start at the same position.
2. **Build** — `build_midi(song, tracks) -> mido.MidiFile`
   - `bar_layout()` computes song-wide bar start ticks and time signature changes, shared by all tracks.
   - Type 1 file: track 0 = title / tempo / time signature changes, then one track per `@TRACK`.
   - Events are collected as `(absolute_tick, message)`, sorted (note_off before anything else at equal ticks, otherwise stable), then converted to delta times.
   - A group advances the cursor by its longest duration; `CC` uses its own `t<pos>` and does not advance the cursor.

`convert()` and `main()` are thin wrappers (public API + argparse CLI).

## Interpretation choices (where the spec is silent)

- **Ties**: a `tie` note is extended by the next note of the same pitch only if that note starts exactly at the tied note's end (works across bars and in chains). Otherwise the tied note ends at its own duration.
- **Pitch bend** applies to its note only: a reset to center is emitted when the note ends. Bend is channel-wide in MIDI, so it also affects other notes sounding at the same time.
- **`@BAR time=`** applies to that bar only, then the `@SONG` signature resumes. A bar's signature is shared by all tracks; on conflict, the first declaration wins (with a warning).
- **Invalid values** (spec section 9): out-of-range program / vol / pan / CC values are clamped to 0–127; invalid channel, tempo, ppq or chord octave fall back to defaults; invalid CC numbers are ignored; a missing, non-numeric or < 1 bar number ignores the bar and its events; zero, negative or invalid durations default to a quarter note.

## Known gaps vs. the spec

- `@SONG key=` and `@BAR chord=` are parsed but unused (no `key_signature` meta).
- Bar overflow (events longer than the bar) is not validated: they spill into the next bar.
- `--verbose` sets DEBUG; WARNINGs are always shown, and the success message is itself logged as a WARNING.

## Conventions

- Code, comments, log messages and documentation in English.
- Keep the lenient error strategy from spec section 9: warn and continue, never crash on bad input lines.
- Unknown keys/keywords must stay silently ignored (forward compatibility).
- When changing the format, update `MTML_spec.md` alongside the code.
- Every behavior change comes with a test in `tests/test_mtml_to_midi.py`; expected values are derived from the spec, not from the current output.
