"""
mtml_to_midi.py
MTML v1.0 → MIDI converter
Dependency: mido  (pip install mido)
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Optional

import mido

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.WARNING)
log = logging.getLogger("mtml")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOTE_NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Intervals (semitones from the root) for each chord quality
CHORD_INTERVALS: dict[str, list[int]] = {
    "maj":  [0, 4, 7],
    "min":  [0, 3, 7],
    "7":    [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "m7":   [0, 3, 7, 10],
    "dim":  [0, 3, 6],
    "aug":  [0, 4, 8],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
    "9":    [0, 4, 7, 10, 14],
    "m9":   [0, 3, 7, 10, 14],
    "maj9": [0, 4, 7, 11, 14],
}

# Regex to parse a pitch (e.g. C4, F#3, Bb5)
RE_PITCH = re.compile(r"^([A-G])(#|b)?(\d+)$")

# Regex to parse a duration (e.g. 1, 1/2, 1.5, 4, t240)
RE_DURATION = re.compile(r"^(t\d+|\d+(?:[./]\d+)?)$")

# Regex for key=value parameters (handles quoted values)
RE_KV = re.compile(r'(\w+)=(?:"([^"]*)"|([\S]+))')


# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SongHeader:
    tempo: int = 120
    time_num: int = 4
    time_den: int = 4
    key: str = "Cmaj"
    ppq: int = 480
    bars: Optional[int] = None
    title: str = ""


@dataclass
class TrackDef:
    id: str = ""
    channel: int = 0          # MIDI channel 0-based internally
    program: int = 0
    name: str = ""
    volume: int = 100
    pan: int = 64
    bars: list["BarDef"] = field(default_factory=list)


@dataclass
class BarDef:
    number: int = 1
    chord: str = ""
    time_num: Optional[int] = None
    time_den: Optional[int] = None
    events: list["MtmlEvent"] = field(default_factory=list)


@dataclass
class MtmlEvent:
    """Generic event: note, REST, CC."""
    kind: str          # "note" | "rest" | "cc"
    # For "note"
    midi_note: int = 0
    duration_ticks: int = 0
    velocity: int = 80
    tie: bool = False
    bend_cents: int = 0
    inline_cc: list[tuple[int, int]] = field(default_factory=list)
    # For "cc"
    cc_num: int = 0
    cc_val: int = 0
    cc_pos_ticks: int = 0      # position relative to the bar start


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_kv(tokens: list[str]) -> dict[str, str]:
    """Extract key=value pairs from a list of tokens."""
    result: dict[str, str] = {}
    raw = " ".join(tokens)
    for m in RE_KV.finditer(raw):
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else m.group(3)
        result[key] = val
    return result


def parse_int(value: Optional[str], default: Optional[int], what: str) -> Optional[int]:
    """Parse an integer, logging a warning and returning `default` if invalid."""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        log.warning("Invalid %s: %s, defaulting to %s", what, value, default)
        return default


def clamp_7bit(value: int, what: str) -> int:
    """Clamp a value to the MIDI data byte range 0–127, with a warning if needed."""
    clamped = max(0, min(127, value))
    if clamped != value:
        log.warning("%s out of range [0-127]: %d, clamped to %d", what, value, clamped)
    return clamped


def parse_time_signature(s: str) -> Optional[tuple[int, int]]:
    """Parse "num/den" (den must be a power of 2). Return None with a warning if invalid."""
    parts = s.split("/")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        num, den = int(parts[0]), int(parts[1])
        if num >= 1 and den >= 1 and den & (den - 1) == 0:
            return num, den
    log.warning("Invalid time signature: %s, ignored", s)
    return None


def parse_duration(s: str, ppq: int) -> int:
    """
    Convert an MTML duration to ticks.
    Examples: "1" → ppq, "1/2" → ppq//2, "4" → ppq*4, "t240" → 240
    Invalid, zero or negative durations default to a quarter note.
    """
    s = s.strip()
    try:
        if s.startswith("t"):
            ticks = int(s[1:])
        else:
            frac = Fraction(s)
            # Very short positive durations still last at least one tick
            ticks = max(1, int(frac * ppq)) if frac > 0 else 0
    except (ValueError, ZeroDivisionError):
        ticks = 0
    if ticks <= 0:
        log.warning("Invalid duration: %s, defaulting to a quarter note", s)
        return ppq
    return ticks


def pitch_to_midi(pitch_str: str) -> Optional[int]:
    """
    Convert an MTML pitch (e.g. C4, F#3, Bb5) to a MIDI note number.
    C4 = 60.
    """
    m = RE_PITCH.match(pitch_str.strip())
    if not m:
        log.warning("Invalid pitch: %s", pitch_str)
        return None
    note_name, accidental, octave_str = m.group(1), m.group(2), m.group(3)
    base = NOTE_NAMES[note_name]
    if accidental == "#":
        base += 1
    elif accidental == "b":
        base -= 1
    midi = (int(octave_str) + 1) * 12 + base
    if not 0 <= midi <= 127:
        log.warning("MIDI pitch out of range [0-127]: %s → %d", pitch_str, midi)
        return None
    return midi


def clamp_velocity(v: int) -> int:
    return max(0, min(127, v))


def parse_chord_symbol(symbol: str, octave: int = 4) -> tuple[Optional[int], list[int]]:
    """
    Parse a chord symbol and return (bass_midi, [midi_notes]).
    E.g.: "Cmaj" → (None, [60, 64, 67])
        "G7/B" → (59, [67, 71, 74, 77])
    """
    # Specific bass note (slash chord)
    bass_midi: Optional[int] = None
    slash_idx = symbol.rfind("/")
    if slash_idx > 0:
        bass_str = symbol[slash_idx + 1:]
        symbol_main = symbol[:slash_idx]
        # The bass is one octave below
        bass_pitch = pitch_to_midi(bass_str + str(octave - 1))
        bass_midi = bass_pitch
    else:
        symbol_main = symbol

    # Root
    root_match = re.match(r"^([A-G][#b]?)", symbol_main)
    if not root_match:
        log.warning("Invalid chord symbol: %s", symbol)
        return None, []

    root_str = root_match.group(1)
    root_midi = pitch_to_midi(root_str + str(octave))
    if root_midi is None:
        return None, []

    quality_str = symbol_main[len(root_str):]

    # Quality normalization
    quality_map = {
        "":     "maj",
        "maj":  "maj",
        "M":    "maj",
        "m":    "min",
        "min":  "min",
        "7":    "7",
        "maj7": "maj7",
        "M7":   "maj7",
        "m7":   "m7",
        "min7": "m7",
        "dim":  "dim",
        "°":    "dim",
        "aug":  "aug",
        "+":    "aug",
        "sus2": "sus2",
        "sus4": "sus4",
        "9":    "9",
        "m9":   "m9",
        "maj9": "maj9",
    }
    quality = quality_map.get(quality_str)
    if quality is None:
        log.warning("Unknown chord quality: '%s', defaulting to major", quality_str)
        quality = "maj"

    intervals = CHORD_INTERVALS[quality]
    notes = [root_midi + i for i in intervals]
    # Drop out-of-range notes
    notes = [n for n in notes if 0 <= n <= 127]
    return bass_midi, notes


def apply_voicing(notes: list[int], voicing: str) -> list[int]:
    """Apply a voicing to a sorted list of notes."""
    notes = sorted(notes)
    if voicing == "open":
        # Raise the third by one octave
        if len(notes) >= 2:
            notes[1] += 12
        notes = sorted(notes)
    elif voicing == "drop2":
        # Drop the second voice from the top by one octave
        if len(notes) >= 2:
            notes[-2] -= 12
        notes = sorted(notes)
    return notes


# ---------------------------------------------------------------------------
# Parser MTML
# ---------------------------------------------------------------------------

def parse_note_token_group(tokens: list[str], ppq: int) -> list[MtmlEvent]:
    """
    Parse a group of tokens describing an N note:
    N <pitch> <duration> <velocity> [options]
    Return a list containing a single MtmlEvent.
    """
    if len(tokens) < 4:
        log.warning("Incomplete N event: %s", tokens)
        return []

    # tokens[0] == "N"
    pitch_str = tokens[1]
    dur_str   = tokens[2]
    vel_str   = tokens[3]
    options   = tokens[4:]

    midi_note = pitch_to_midi(pitch_str)
    if midi_note is None:
        return []

    duration_ticks = parse_duration(dur_str, ppq)

    try:
        velocity = clamp_velocity(int(vel_str))
    except ValueError:
        log.warning("Invalid velocity: %s, defaulting to 80", vel_str)
        velocity = 80

    tie = "tie" in options
    bend_cents = 0
    inline_cc: list[tuple[int, int]] = []

    for opt in options:
        if opt == "tie":
            continue
        bend_m = re.match(r"bend=([+-]?\d+)", opt)
        if bend_m:
            bend_cents = int(bend_m.group(1))
            continue
        cc_m = re.match(r"cc(\d+)=(\d+)", opt)
        if cc_m:
            cc_num = int(cc_m.group(1))
            if cc_num > 127:
                log.warning("Invalid CC number: %d, ignored", cc_num)
                continue
            inline_cc.append((cc_num, clamp_7bit(int(cc_m.group(2)), "CC value")))
            continue

    return [MtmlEvent(
        kind="note",
        midi_note=midi_note,
        duration_ticks=duration_ticks,
        velocity=velocity,
        tie=tie,
        bend_cents=bend_cents,
        inline_cc=inline_cc,
    )]


def parse_line_events(line: str, ppq: int) -> list[list[MtmlEvent]]:
    """
    Parse an event line, handling polyphony (|).
    Return one group per '|' segment; the caller merges them into a single
    simultaneous group.
    """
    # Split on '|' (and surrounding whitespace); '#' and 'b' in pitches are unaffected
    groups_raw = re.split(r'\s*\|\s*', line)
    groups: list[list[MtmlEvent]] = []
    for grp in groups_raw:
        tokens = grp.split()
        if not tokens:
            continue
        keyword = tokens[0].upper()
        if keyword == "N":
            evts = parse_note_token_group(tokens, ppq)
            if evts:
                groups.append(evts)
        elif keyword == "CHORD":
            grp_evts = parse_chord_line(tokens, ppq)
            if grp_evts:
                groups.append(grp_evts)
        elif keyword == "REST":
            dur = parse_duration(tokens[1], ppq) if len(tokens) > 1 else ppq
            groups.append([MtmlEvent(kind="rest", duration_ticks=dur)])
        elif keyword == "CC":
            evt = parse_cc_line(tokens, ppq)
            if evt:
                groups.append([evt])
        else:
            log.warning("Unknown keyword on event line: %s", keyword)
    return groups


def parse_chord_line(tokens: list[str], ppq: int) -> list[MtmlEvent]:
    """CHORD <symbole> <duration> <velocity> [voicing=X] [oct=N]"""
    if len(tokens) < 4:
        log.warning("Incomplete CHORD: %s", tokens)
        return []

    symbol   = tokens[1]
    dur_str  = tokens[2]
    vel_str  = tokens[3]
    kv       = parse_kv(tokens[4:])

    voicing = kv.get("voicing", "close")
    octave  = parse_int(kv.get("oct"), 4, "chord octave")

    bass_midi, notes = parse_chord_symbol(symbol, octave)
    notes = apply_voicing(notes, voicing)

    if not notes:
        return []

    duration_ticks = parse_duration(dur_str, ppq)
    try:
        velocity = clamp_velocity(int(vel_str))
    except ValueError:
        velocity = 80

    events: list[MtmlEvent] = []
    if bass_midi is not None:
        events.append(MtmlEvent(
            kind="note",
            midi_note=bass_midi,
            duration_ticks=duration_ticks,
            velocity=velocity,
        ))
    for n in notes:
        events.append(MtmlEvent(
            kind="note",
            midi_note=n,
            duration_ticks=duration_ticks,
            velocity=velocity,
        ))
    return events


def parse_cc_line(tokens: list[str], ppq: int) -> Optional[MtmlEvent]:
    """CC <num> <val> [t<pos>]"""
    if len(tokens) < 3:
        log.warning("Incomplete CC: %s", tokens)
        return None
    try:
        cc_num = int(tokens[1])
        cc_val = clamp_7bit(int(tokens[2]), "CC value")
    except ValueError:
        log.warning("Invalid CC: %s", tokens)
        return None
    if not 0 <= cc_num <= 127:
        log.warning("Invalid CC number: %d, ignored", cc_num)
        return None

    cc_pos = 0
    if len(tokens) > 3 and tokens[3].startswith("t"):
        try:
            cc_pos = int(tokens[3][1:])
        except ValueError:
            pass

    return MtmlEvent(kind="cc", cc_num=cc_num, cc_val=cc_val, cc_pos_ticks=cc_pos)


def parse_mtml(text: str) -> tuple[SongHeader, list[TrackDef]]:
    """
    Parse a complete MTML text.
    Return (SongHeader, [TrackDef]).
    """
    song = SongHeader()
    tracks: list[TrackDef] = []
    current_track: Optional[TrackDef] = None
    current_bar:   Optional[BarDef]   = None

    for raw_line in text.splitlines():
        # Strip comments: # is comment only when preceded by whitespace or at line start
        line = re.sub(r"(?:^|(?<=\s))#.*$", "", raw_line).strip()
        if not line:
            continue

        tokens = line.split()
        keyword = tokens[0].upper()

        # ---- @SONG ----
        if keyword == "@SONG":
            kv = parse_kv(tokens[1:])
            song.tempo    = parse_int(kv.get("tempo"), 120, "tempo")
            song.ppq      = parse_int(kv.get("ppq"), 480, "ppq")
            song.key      = kv.get("key", "Cmaj")
            song.title    = kv.get("title", "")
            song.bars     = parse_int(kv.get("bars"), None, "bar count")
            if song.tempo <= 0:
                log.warning("Invalid tempo: %d, defaulting to 120", song.tempo)
                song.tempo = 120
            if song.ppq <= 0:
                log.warning("Invalid ppq: %d, defaulting to 480", song.ppq)
                song.ppq = 480
            if "time" in kv:
                signature = parse_time_signature(kv["time"])
                if signature:
                    song.time_num, song.time_den = signature

        # ---- @TRACK ----
        elif keyword == "@TRACK":
            kv = parse_kv(tokens[1:])
            ch_1based = parse_int(kv.get("ch"), 1, "channel")
            if not 1 <= ch_1based <= 16:
                log.warning("Invalid channel: %d, defaulting to 1", ch_1based)
                ch_1based = 1
            current_track = TrackDef(
                id       = kv.get("id", f"track{len(tracks)}"),
                channel  = ch_1based - 1,   # MIDI 0-based
                program  = clamp_7bit(parse_int(kv.get("program"), 0, "program"), "program"),
                name     = kv.get("name", ""),
                volume   = clamp_7bit(parse_int(kv.get("vol"), 100, "volume"), "volume"),
                pan      = clamp_7bit(parse_int(kv.get("pan"), 64, "pan"), "pan"),
            )
            tracks.append(current_track)
            current_bar = None

        # ---- @BAR ----
        elif keyword == "@BAR":
            if current_track is None:
                log.warning("@BAR without a preceding @TRACK, ignored")
                continue
            kv = parse_kv(tokens[2:])
            bar_num = parse_int(tokens[1] if len(tokens) > 1 else None, None, "bar number")
            if bar_num is None or bar_num < 1:
                # The bar number is mandatory: ignore the bar and its events
                log.warning("Invalid or missing bar number: %s, bar ignored", line)
                current_bar = None
                continue
            bar = BarDef(number=bar_num, chord=kv.get("chord", ""))
            if "time" in kv:
                signature = parse_time_signature(kv["time"])
                if signature:
                    bar.time_num, bar.time_den = signature
            current_track.bars.append(bar)
            current_bar = bar

        # ---- Events (N, CHORD, REST, CC) ----
        elif keyword in ("N", "CHORD", "REST", "CC"):
            if current_bar is None:
                log.warning("Event '%s' outside of a @BAR, ignored", keyword)
                continue
            groups = parse_line_events(line, song.ppq)
            # All '|'-separated segments of one line start at the same position,
            # so they are merged into a single simultaneous group.
            merged = [evt for grp in groups for evt in grp]
            if merged:
                current_bar.events.append(merged)  # type: ignore[arg-type]

        else:
            log.debug("Line ignored (unknown keyword): %s", line)

    return song, tracks


# ---------------------------------------------------------------------------
# MIDI conversion
# ---------------------------------------------------------------------------

def bar_layout(song: SongHeader, tracks: list[TrackDef]) -> tuple[dict[int, int], list[tuple[int, int, int]]]:
    """
    Compute the song-wide bar layout.

    A `time=` on a @BAR applies to that bar only (local signature); other bars
    use the @SONG signature. The signature of a bar is shared by all tracks:
    if tracks disagree, the first declaration wins.

    Returns:
        (bar number → absolute start tick, [(tick, numerator, denominator)] of
        each time signature change, starting at tick 0)
    """
    default = (song.time_num, song.time_den)
    declared: dict[int, tuple[int, int]] = {}
    last_bar = 1
    for track in tracks:
        for bar in track.bars:
            last_bar = max(last_bar, bar.number)
            if bar.time_num and bar.time_den:
                signature = (bar.time_num, bar.time_den)
                if declared.setdefault(bar.number, signature) != signature:
                    log.warning("Conflicting time signature %d/%d for bar %d in track '%s', ignored",
                                *signature, bar.number, track.id)

    starts: dict[int, int] = {}
    changes: list[tuple[int, int, int]] = []
    tick = 0
    for number in range(1, last_bar + 1):
        num, den = declared.get(number, default)
        if not changes or changes[-1][1:] != (num, den):
            changes.append((tick, num, den))
        starts[number] = tick
        tick += int(Fraction(num, den) * 4 * song.ppq)
    return starts, changes


def tempo_to_microseconds(bpm: int) -> int:
    return int(60_000_000 / bpm)


def bend_cents_to_midi(cents: int) -> int:
    """
    Convert cents to a 14-bit MIDI pitch bend value (0–16383, center 8192).
    Range: ±200 cents = ±2 semitones (standard sensitivity).
    """
    clamped = max(-200, min(200, cents))
    # 8192 = center, 8192/200 ≈ 40.96 units per cent
    value = 8192 + int(clamped * 40.96)
    return max(0, min(16383, value))


def build_midi(song: SongHeader, tracks: list[TrackDef]) -> mido.MidiFile:
    mid = mido.MidiFile(type=1, ticks_per_beat=song.ppq)
    bar_starts, signature_changes = bar_layout(song, tracks)

    # Track 0: tempo, time signatures + global metadata
    meta_track = mido.MidiTrack()
    mid.tracks.append(meta_track)
    if song.title:
        meta_track.append(mido.MetaMessage("track_name", name=song.title, time=0))
    meta_track.append(mido.MetaMessage("set_tempo", tempo=tempo_to_microseconds(song.tempo), time=0))
    prev_tick = 0
    for tick, num, den in signature_changes:
        meta_track.append(mido.MetaMessage("time_signature",
            numerator=num, denominator=den, time=tick - prev_tick))
        prev_tick = tick
    meta_track.append(mido.MetaMessage("end_of_track", time=0))

    for track_def in tracks:
        midi_track = mido.MidiTrack()
        mid.tracks.append(midi_track)
        ch = track_def.channel

        # Track name
        if track_def.name:
            midi_track.append(mido.MetaMessage("track_name", name=track_def.name, time=0))

        # Program + initial CCs (time=0)
        midi_track.append(mido.Message("program_change", channel=ch,
                                        program=track_def.program, time=0))
        midi_track.append(mido.Message("control_change", channel=ch,
                                        control=7, value=track_def.volume, time=0))
        midi_track.append(mido.Message("control_change", channel=ch,
                                        control=10, value=track_def.pan, time=0))

        # Build the message list as (absolute tick, message)
        abs_messages: list[tuple[int, mido.Message]] = []

        def note_off(tick: int, note: int) -> None:
            abs_messages.append((tick, mido.Message(
                "note_off", channel=ch, note=note, velocity=0)))

        # Pending ties, kept across bars: pitch → end tick of the tied note,
        # i.e. where the continuation note must start.
        open_ties: dict[int, int] = {}

        for bar in track_def.bars:
            bar_start_abs = bar_starts[bar.number]
            cursor = 0   # position relative to the bar start (ticks)

            for event_or_group in bar.events:
                # Normalize: each item of bar.events is either an MtmlEvent
                # or a list of MtmlEvent (polyphonic group)
                if isinstance(event_or_group, list):
                    group: list[MtmlEvent] = event_or_group
                else:
                    group = [event_or_group]

                max_dur = 0

                for evt in group:
                    abs_pos = bar_start_abs + cursor

                    if evt.kind == "rest":
                        max_dur = max(max_dur, evt.duration_ticks)
                        continue

                    if evt.kind == "cc":
                        cc_abs = bar_start_abs + evt.cc_pos_ticks
                        abs_messages.append((cc_abs, mido.Message(
                            "control_change", channel=ch,
                            control=evt.cc_num, value=evt.cc_val)))
                        continue

                    # kind == "note"
                    # Pitch bend applies to this note only: reset it when the note ends.
                    # Bend is channel-wide, so it also affects notes sounding with it.
                    if evt.bend_cents != 0:
                        bend_val = bend_cents_to_midi(evt.bend_cents)
                        abs_messages.append((abs_pos, mido.Message(
                            "pitchwheel", channel=ch,
                            pitch=bend_val - 8192)))  # mido expects -8192..8191
                        abs_messages.append((abs_pos + evt.duration_ticks, mido.Message(
                            "pitchwheel", channel=ch, pitch=0)))

                    # Inline CC
                    for cc_num, cc_val in evt.inline_cc:
                        abs_messages.append((abs_pos, mido.Message(
                            "control_change", channel=ch,
                            control=cc_num, value=cc_val)))

                    note_end = abs_pos + evt.duration_ticks

                    # A pending tie on this pitch is continued only if this note
                    # starts exactly where the tied note ends; otherwise the tied
                    # note is closed at its own end (or here, if this note overlaps it).
                    tie_end = open_ties.pop(evt.midi_note, None)
                    if tie_end is not None and tie_end != abs_pos:
                        note_off(min(tie_end, abs_pos), evt.midi_note)
                        tie_end = None

                    if tie_end is None:
                        abs_messages.append((abs_pos, mido.Message(
                            "note_on", channel=ch,
                            note=evt.midi_note, velocity=evt.velocity)))

                    if evt.tie:
                        open_ties[evt.midi_note] = note_end
                    else:
                        note_off(note_end, evt.midi_note)

                    max_dur = max(max_dur, evt.duration_ticks)

                cursor += max_dur

        # Tied notes never continued end at their own duration
        for note, tie_end in open_ties.items():
            note_off(tie_end, note)

        # Sort by absolute tick, note_off before note_on at the same tick
        def sort_key(item: tuple[int, mido.Message]) -> tuple[int, int]:
            tick, msg = item
            prio = 0 if msg.type == "note_off" else 1
            return (tick, prio)

        abs_messages.sort(key=sort_key)

        # Convert to delta times
        prev_tick = 0
        for abs_tick, msg in abs_messages:
            delta = abs_tick - prev_tick
            midi_track.append(msg.copy(time=delta))
            prev_tick = abs_tick

        midi_track.append(mido.MetaMessage("end_of_track", time=0))

    return mid


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert(mtml_text: str, output_path: str | Path, verbose: bool = False) -> mido.MidiFile:
    """
    Parse MTML text and write a MIDI file.

    Args:
        mtml_text:   MTML content as a string.
        output_path: Path of the .mid file to create.
        verbose:     If True, enable DEBUG logs.

    Returns:
        The generated MidiFile object.
    """
    if verbose:
        log.setLevel(logging.DEBUG)

    song, tracks = parse_mtml(mtml_text)

    if not tracks:
        raise ValueError("No track found in the MTML file.")

    mid = build_midi(song, tracks)
    mid.save(str(output_path))
    log.warning("MIDI written: %s (%d tracks, tempo=%d BPM, PPQ=%d)",
                output_path, len(tracks), song.tempo, song.ppq)
    return mid


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="MTML v1.0 → MIDI converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python mtml_to_midi.py composition.mtml output.mid
  python mtml_to_midi.py composition.mtml output.mid --verbose
        """,
    )
    parser.add_argument("input",  help="Source .mtml file")
    parser.add_argument("output", help="Output .mid file")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show debug logs")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    try:
        mid = convert(text, args.output, verbose=args.verbose)
        duration_sec = mid.length
        print(f"✓ {args.output} — {len(mid.tracks)-1} track(s), "
              f"duration ≈ {duration_sec:.1f}s")
    except Exception as exc:
        print(f"Conversion error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
