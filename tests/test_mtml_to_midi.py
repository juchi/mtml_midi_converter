"""Conformance tests for mtml_to_midi.py against MTML_spec.md.

Expected values are derived by hand from the spec. Each test converts a small
MTML snippet and inspects the resulting MIDI messages at absolute ticks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import mtml_to_midi as m

ROOT = Path(__file__).resolve().parent.parent

SONG = "@SONG tempo=120 time=4/4 key=Cmaj ppq=480\n"
HDR = SONG + "@TRACK id=t ch=1 program=0\n@BAR 1\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build(text: str):
    song, tracks = m.parse_mtml(text)
    return m.build_midi(song, tracks)


def events(text: str, track: int = 1, types=("note_on", "note_off")) -> list[tuple]:
    """Absolute-tick events of one MIDI track, in file order."""
    out, tick = [], 0
    for msg in build(text).tracks[track]:
        tick += msg.time
        if msg.type not in types:
            continue
        if msg.type in ("note_on", "note_off"):
            kind = "off" if msg.type == "note_off" or msg.velocity == 0 else "on"
            out.append((tick, kind, msg.note))
        elif msg.type == "control_change":
            out.append((tick, "cc", msg.control, msg.value))
        elif msg.type == "pitchwheel":
            out.append((tick, "bend", msg.pitch))
        else:
            out.append((tick, msg))
    return out


def notes(text: str, track: int = 1) -> list[tuple[int, int, int]]:
    """Sorted (start, end, pitch) notes. Fails on retriggers or stuck notes."""
    open_notes: dict[int, int] = {}
    result = []
    for tick, kind, pitch in events(text, track):
        if kind == "on":
            assert pitch not in open_notes, f"note {pitch} retriggered at {tick}"
            open_notes[pitch] = tick
        else:
            assert pitch in open_notes, f"note_off without note_on for {pitch} at {tick}"
            result.append((open_notes.pop(pitch), tick, pitch))
    assert not open_notes, f"stuck notes: {open_notes}"
    return sorted(result)


def pitches(text: str) -> list[int]:
    return sorted(p for _, _, p in notes(text))


# ---------------------------------------------------------------------------
# 1. @SONG
# ---------------------------------------------------------------------------

def test_song_header():
    mid = build('@SONG tempo=100 time=3/4 key=Cmaj ppq=96 title="My song"\n'
                "@TRACK id=t ch=1 program=0\n@BAR 1\nN C4 1 80\n")
    meta = {msg.type: msg for msg in mid.tracks[0]}
    assert mid.ticks_per_beat == 96
    assert meta["set_tempo"].tempo == 600_000          # 100 BPM
    assert (meta["time_signature"].numerator, meta["time_signature"].denominator) == (3, 4)
    assert meta["track_name"].name == "My song"


# ---------------------------------------------------------------------------
# 2. @TRACK
# ---------------------------------------------------------------------------

def test_track_parameters():
    mid = build(SONG + '@TRACK id=b ch=2 program=32 name="Bass" vol=85 pan=40\n'
                "@BAR 1\nN C2 1 80\n")
    track = mid.tracks[1]
    assert track.name == "Bass"
    assert [x.program for x in track if x.type == "program_change"] == [32]
    assert [(x.control, x.value) for x in track if x.type == "control_change"] == [(7, 85), (10, 40)]
    assert {x.channel for x in track if hasattr(x, "channel")} == {1}


def test_track_volume_and_pan_defaults():
    track = build(HDR + "N C4 1 80\n").tracks[1]
    assert [(x.control, x.value) for x in track if x.type == "control_change"] == [(7, 100), (10, 64)]


def test_one_midi_track_per_mtml_track_plus_meta_track():
    text = HDR + "N C4 1 80\n@TRACK id=u ch=2 program=0\n@BAR 1\nN C4 1 80\n"
    assert len(build(text).tracks) == 3


# ---------------------------------------------------------------------------
# 4.1 Notes: pitch, duration, velocity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pitch, midi", [
    ("C4", 60), ("F#3", 54), ("Bb5", 82), ("G2", 43), ("A#4", 70), ("Eb6", 87), ("B1", 35),
])
def test_pitch(pitch, midi):
    assert pitches(HDR + f"N {pitch} 1 80\n") == [midi]


def test_invalid_pitch_is_skipped():
    assert notes(HDR + "N H4 1 80\nN C4 1 80\n") == [(0, 480, 60)]


@pytest.mark.parametrize("duration, ticks", [
    ("4", 1920), ("2", 960), ("1", 480), ("1/2", 240), ("1/4", 120),
    ("1/8", 60), ("1.5", 720), ("3/4", 360), ("t240", 240),
])
def test_duration(duration, ticks):
    assert notes(HDR + f"N C4 {duration} 80\n") == [(0, ticks, 60)]


def test_invalid_duration_defaults_to_quarter_note():
    assert notes(HDR + "N C4 abc 80\n") == [(0, 480, 60)]


@pytest.mark.parametrize("duration", ["t0", "0", "-1", "t-5"])
def test_zero_duration_defaults_to_quarter_note(duration):
    assert notes(HDR + f"N C4 {duration} 80\n") == [(0, 480, 60)]


def test_sequential_events_advance_cursor():
    assert notes(HDR + "N C4 1 80\nN D4 1/2 80\nN E4 1/2 80\nN F4 2 80\n") == [
        (0, 480, 60), (480, 720, 62), (720, 960, 64), (960, 1920, 65)]


def test_velocity_is_clamped():
    track = build(HDR + "N C4 1 200\n").tracks[1]
    assert [x.velocity for x in track if x.type == "note_on"] == [127]


# ---------------------------------------------------------------------------
# 4.1 Options: tie, bend, inline CC
# ---------------------------------------------------------------------------

def test_tie_within_bar():
    assert notes(HDR + "N C4 1 80 tie\nN C4 1 80\n") == [(0, 960, 60)]


def test_tie_chain_of_three_notes():
    assert notes(HDR + "N C4 1 80 tie\nN C4 1 80 tie\nN C4 1 80\n") == [(0, 1440, 60)]


def test_tie_across_bars():
    # Spec 4.1 example: the tied C4 at the end of bar 1 continues into bar 2.
    text = HDR + "N C4 3 80\nN C4 1 85 tie\n@BAR 2\nN C4 1 85\n"
    assert notes(text) == [(0, 1440, 60), (1440, 2400, 60)]


def test_tie_without_matching_next_note_ends_at_its_own_duration():
    assert notes(HDR + "N C4 1 80 tie\nN D4 1 80\n") == [(0, 480, 60), (480, 960, 62)]


def test_tie_followed_by_a_gap_is_not_continued():
    assert notes(HDR + "N C4 1 80 tie\nREST 1\nN C4 1 80\n") == [(0, 480, 60), (960, 1440, 60)]


def test_tie_on_a_whole_chord():
    text = HDR + "N C4 1 80 tie | N E4 1 80 tie\nN C4 1 80 | N E4 1 80\n"
    assert notes(text) == [(0, 960, 60), (0, 960, 64)]


def test_bend_at_note_start():
    assert events(HDR + "N E4 1 75 bend=+50\n", types=("pitchwheel",))[0] == (0, "bend", 2048)


def test_bend_is_reset_after_the_bent_note():
    assert events(HDR + "N E4 1 75 bend=+50\nN F4 1 75\n", types=("pitchwheel",)) == [
        (0, "bend", 2048), (480, "bend", 0)]


def test_consecutive_bent_notes_keep_their_own_bend():
    # The reset of the first note and the bend of the second share tick 480:
    # the reset must come first so the second note is bent.
    assert events(HDR + "N E4 1 75 bend=+50\nN F4 1 75 bend=-100\n", types=("pitchwheel",)) == [
        (0, "bend", 2048), (480, "bend", 0), (480, "bend", -4096), (960, "bend", 0)]


def test_inline_cc_at_note_start():
    ccs = events(HDR + "N C4 1 80\nN G3 2 90 cc7=64\n", types=("control_change",))
    assert ccs[-1] == (480, "cc", 7, 64)


# ---------------------------------------------------------------------------
# 4.1 Polyphony
# ---------------------------------------------------------------------------

def test_polyphony_notes_start_together():
    assert notes(HDR + "N C4 1 80 | N E4 1 75 | N G4 1 70\nN D4 1 80\n") == [
        (0, 480, 60), (0, 480, 64), (0, 480, 67), (480, 960, 62)]


def test_polyphony_cursor_advances_by_longest_duration():
    assert notes(HDR + "N C2 1 100 | N F#2 1/2 80\nN F#2 1/2 75\n") == [
        (0, 240, 42), (0, 480, 36), (480, 720, 42)]


# ---------------------------------------------------------------------------
# 4.2 CHORD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol, expected", [
    ("C", [60, 64, 67]), ("Cmaj", [60, 64, 67]), ("Amin", [69, 72, 76]), ("Am", [69, 72, 76]),
    ("G7", [67, 71, 74, 77]), ("Cmaj7", [60, 64, 67, 71]), ("Dm7", [62, 65, 69, 72]),
    ("Bdim", [71, 74, 77]), ("Eaug", [64, 68, 72]), ("Gsus2", [67, 69, 74]),
    ("Gsus4", [67, 72, 74]), ("C9", [60, 64, 67, 70, 74]), ("Cm9", [60, 63, 67, 70, 74]),
    ("Cmaj9", [60, 64, 67, 71, 74]), ("F#", [66, 70, 73]),
    ("C/E", [52, 60, 64, 67]), ("G7/B", [59, 67, 71, 74, 77]),
])
def test_chord_symbols(symbol, expected):
    assert pitches(HDR + f"CHORD {symbol} 1 80\n") == expected


@pytest.mark.parametrize("options, expected", [
    ("oct=3", [48, 52, 55]),
    ("voicing=open", [60, 67, 76]),     # third raised by an octave
    ("voicing=drop2", [52, 60, 67]),    # second voice from the top dropped by an octave
])
def test_chord_options(options, expected):
    assert pitches(HDR + f"CHORD C 1 80 {options}\n") == expected


def test_chord_duration_and_cursor():
    result = notes(HDR + "CHORD Dm7 2 75\nCHORD G7 2 78\n")
    assert {(start, end) for start, end, _ in result} == {(0, 960), (960, 1920)}


# ---------------------------------------------------------------------------
# 4.3 REST / 4.4 CC
# ---------------------------------------------------------------------------

def test_rest_advances_cursor():
    assert notes(HDR + "N C4 1 80\nREST 1/2\nN D4 1 80\n") == [(0, 480, 60), (720, 1200, 62)]


def test_cc_position_is_relative_to_bar_and_does_not_advance_cursor():
    text = HDR + "N C4 1 80\n@BAR 2\nCC 64 127 t0\nN C4 2 80\nCC 64 0 t480\n"
    assert events(text, types=("control_change",))[2:] == [(1920, "cc", 64, 127), (2400, "cc", 64, 0)]
    assert notes(text) == [(0, 480, 60), (1920, 2880, 60)]


# ---------------------------------------------------------------------------
# 5. Percussion / 6. Comments / 7. Parsing rules
# ---------------------------------------------------------------------------

def test_channel_10_maps_to_midi_channel_9():
    track = build(SONG + "@TRACK id=d ch=10 program=0\n@BAR 1\nN C2 1 100\n").tracks[1]
    assert {x.channel for x in track if hasattr(x, "channel")} == {9}


def test_comments_are_stripped_but_sharp_in_pitch_is_kept():
    assert notes(HDR + "# comment\nN F#4 1 80   # inline\n") == [(0, 480, 66)]


def test_unknown_keys_and_keywords_are_ignored():
    text = HDR.replace("program=0", "program=0 foo=bar") + "FOO 1 2\nN C4 1 80\n"
    assert notes(text) == [(0, 480, 60)]


def test_event_outside_bar_is_ignored():
    text = SONG + "@TRACK id=t ch=1 program=0\nN D4 1 80\n@BAR 1\nN C4 1 80\n"
    assert notes(text) == [(0, 480, 60)]


# ---------------------------------------------------------------------------
# 10. Bar positioning and time signatures
# ---------------------------------------------------------------------------

def test_bar_start_in_4_4():
    assert notes(HDR + "N C4 1 80\n@BAR 3\nN D4 1 80\n") == [(0, 480, 60), (3840, 4320, 62)]


def test_bar_start_in_3_4():
    text = "@SONG tempo=120 time=3/4 key=Cmaj ppq=480\n@TRACK id=t ch=1 program=0\n@BAR 2\nN C4 1 80\n"
    assert notes(text) == [(1440, 1920, 60)]


def test_mixed_time_signatures_accumulate_bar_lengths():
    text = HDR + "N C4 1 80\n@BAR 2 time=3/4\nN D4 1 80\n@BAR 3\nN E4 1 80\n"
    assert notes(text) == [(0, 480, 60), (1920, 2400, 62), (3360, 3840, 64)]


def test_time_signature_changes_are_written_to_meta_track():
    text = HDR + "N C4 1 80\n@BAR 2 time=3/4\nN D4 1 80\n@BAR 3\nN E4 1 80\n"
    sigs = [(tick, msg.numerator, msg.denominator)
            for tick, msg in events(text, track=0, types=("time_signature",))]
    assert sigs == [(0, 4, 4), (1920, 3, 4), (3360, 4, 4)]


def test_time_signature_is_shared_by_all_tracks():
    # Only the first track declares the 3/4 bar; the second track's bar 3 must line up.
    text = (HDR + "N C4 1 80\n@BAR 2 time=3/4\nN D4 1 80\n"
            "@TRACK id=u ch=2 program=0\n@BAR 3\nN E4 1 80\n")
    assert notes(text, track=2) == [(3360, 3840, 64)]


def test_consecutive_bars_with_the_same_local_signature_emit_a_single_change():
    text = HDR + "N C4 1 80\n@BAR 2 time=6/8\nN D4 1 80\n@BAR 3 time=6/8\nN E4 1 80\n"
    sigs = [(tick, msg.numerator, msg.denominator)
            for tick, msg in events(text, track=0, types=("time_signature",))]
    assert sigs == [(0, 4, 4), (1920, 6, 8)]
    assert notes(text)[-1] == (1920 + 1440, 1920 + 1440 + 480, 64)


# ---------------------------------------------------------------------------
# 9. Lenient error handling: invalid input must never crash the conversion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    pytest.param(HDR + "CC 200 10\nN C4 1 80\n", id="cc-number-over-127"),
    pytest.param(HDR + "N C4 1 80 cc7=300\n", id="inline-cc-value-over-127"),
    pytest.param(HDR + "N C4 1 80 cc300=1\n", id="inline-cc-number-over-127"),
    pytest.param(HDR.replace("program=0", "program=200") + "N C4 1 80\n", id="program-over-127"),
    pytest.param(HDR.replace("program=0", "program=0 vol=200 pan=-3") + "N C4 1 80\n",
                 id="vol-pan-out-of-range"),
    pytest.param(HDR.replace("ch=1", "ch=17") + "N C4 1 80\n", id="channel-17"),
    pytest.param(HDR.replace("ch=1", "ch=abc") + "N C4 1 80\n", id="channel-not-a-number"),
    pytest.param(HDR + "@BAR x\nN C4 1 80\n", id="bar-number-not-a-number"),
    pytest.param(HDR + "@BAR 0\nN C4 1 80\n", id="bar-number-zero"),
    pytest.param(HDR + "CHORD C 1 80 oct=abc\n", id="chord-octave-not-a-number"),
    pytest.param(HDR.replace("tempo=120", "tempo=fast") + "N C4 1 80\n", id="tempo-not-a-number"),
    pytest.param(HDR.replace("tempo=120", "tempo=0") + "N C4 1 80\n", id="tempo-zero"),
    pytest.param(HDR.replace("ppq=480", "ppq=x") + "N C4 1 80\n", id="ppq-not-a-number"),
    pytest.param(HDR.replace("time=4/4", "time=4/3") + "N C4 1 80\n", id="time-denominator-not-power-of-2"),
    pytest.param(HDR + "@BAR 2 time=x/4\nN C4 1 80\n", id="bar-time-not-a-number"),
])
def test_invalid_input_does_not_crash(text, tmp_path):
    build(text).save(tmp_path / "out.mid")


def test_out_of_range_track_values_are_clamped_or_defaulted():
    track = build(SONG + "@TRACK id=t ch=17 program=200 vol=200 pan=-3\n@BAR 1\nN C4 1 80\n").tracks[1]
    assert [x.program for x in track if x.type == "program_change"] == [127]
    assert [(x.control, x.value) for x in track if x.type == "control_change"] == [(7, 127), (10, 0)]
    assert {x.channel for x in track if hasattr(x, "channel")} == {0}   # ch=17 -> default ch=1


def test_invalid_cc_number_is_ignored_and_value_clamped():
    text = HDR + "CC 200 10\nCC 11 300\nN C4 1 80 cc300=1 cc1=999\n"
    assert events(text, types=("control_change",))[2:] == [(0, "cc", 11, 127), (0, "cc", 1, 127)]


@pytest.mark.parametrize("bar_line", ["@BAR x", "@BAR 0", "@BAR"])
def test_invalid_bar_number_ignores_the_bar_and_its_events(bar_line):
    assert notes(HDR + f"N C4 1 80\n{bar_line}\nN D4 1 80\n") == [(0, 480, 60)]


def test_invalid_song_values_fall_back_to_defaults():
    mid = build("@SONG tempo=0 time=4/3 key=Cmaj ppq=x\n@TRACK id=t ch=1 program=0\n@BAR 1\nN C4 1 80\n")
    meta = {msg.type: msg for msg in mid.tracks[0]}
    assert mid.ticks_per_beat == 480
    assert meta["set_tempo"].tempo == 500_000          # 120 BPM
    assert (meta["time_signature"].numerator, meta["time_signature"].denominator) == (4, 4)


def test_invalid_chord_octave_defaults_to_4():
    assert pitches(HDR + "CHORD C 1 80 oct=abc\n") == [60, 64, 67]


# ---------------------------------------------------------------------------
# End-to-end: the complete example of spec section 8
# ---------------------------------------------------------------------------

def test_spec_example_end_to_end(tmp_path):
    text = (ROOT / "examples" / "simple_study.mtml").read_text(encoding="utf-8")
    mid = m.convert(text, tmp_path / "out.mid")
    assert len(mid.tracks) == 3
    piano, bass = notes(text, 1), notes(text, 2)
    assert max(end for _, end, _ in piano) == 8 * 1920
    assert max(end for _, end, _ in bass) == 8 * 1920
    # Final C major chord of the piano, bar 8, whole note
    assert [n for n in piano if n[0] == 7 * 1920] == [
        (13440, 15360, 60), (13440, 15360, 64), (13440, 15360, 67)]
    assert round(mid.length, 1) == 19.2   # 32 beats at 100 BPM
