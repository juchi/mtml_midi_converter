"""Known spec violations of the current implementation.

Each listed test is expected to fail (strict xfail): fixing a bug makes its
test pass, which pytest reports as an error until it is removed from this list.
"""

import pytest

KNOWN_BUGS = {
    'test_zero_duration_defaults_to_quarter_note[t0]',
    'test_zero_duration_defaults_to_quarter_note[0]',
    'test_zero_duration_defaults_to_quarter_note[-1]',
    'test_zero_duration_defaults_to_quarter_note[t-5]',
    'test_tie_chain_of_three_notes',
    'test_tie_across_bars',
    'test_tie_without_matching_next_note_ends_at_its_own_duration',
    'test_tie_followed_by_a_gap_is_not_continued',
    'test_bend_is_reset_after_the_bent_note',
    'test_consecutive_bent_notes_keep_their_own_bend',
    'test_mixed_time_signatures_accumulate_bar_lengths',
    'test_time_signature_changes_are_written_to_meta_track',
    'test_time_signature_is_shared_by_all_tracks',
    'test_consecutive_bars_with_the_same_local_signature_emit_a_single_change',
    'test_invalid_input_does_not_crash[cc-number-over-127]',
    'test_invalid_input_does_not_crash[inline-cc-value-over-127]',
    'test_invalid_input_does_not_crash[inline-cc-number-over-127]',
    'test_invalid_input_does_not_crash[program-over-127]',
    'test_invalid_input_does_not_crash[vol-pan-out-of-range]',
    'test_invalid_input_does_not_crash[channel-17]',
    'test_invalid_input_does_not_crash[channel-not-a-number]',
    'test_invalid_input_does_not_crash[bar-number-not-a-number]',
    'test_invalid_input_does_not_crash[bar-number-zero]',
    'test_invalid_input_does_not_crash[chord-octave-not-a-number]',
    'test_invalid_input_does_not_crash[tempo-not-a-number]',
    'test_invalid_input_does_not_crash[tempo-zero]',
    'test_invalid_input_does_not_crash[ppq-not-a-number]',
    'test_invalid_input_does_not_crash[time-denominator-not-power-of-2]',
    'test_invalid_input_does_not_crash[bar-time-not-a-number]',
    'test_out_of_range_track_values_are_clamped_or_defaulted',
    'test_invalid_cc_number_is_ignored_and_value_clamped',
    'test_invalid_bar_number_ignores_the_bar_and_its_events[@BAR x]',
    'test_invalid_bar_number_ignores_the_bar_and_its_events[@BAR 0]',
    'test_invalid_bar_number_ignores_the_bar_and_its_events[@BAR]',
    'test_invalid_song_values_fall_back_to_defaults',
    'test_invalid_chord_octave_defaults_to_4',
}


def pytest_collection_modifyitems(items):
    for item in items:
        if item.name in KNOWN_BUGS:
            item.add_marker(pytest.mark.xfail(strict=True, reason="known bug"))
