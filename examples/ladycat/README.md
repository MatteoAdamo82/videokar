# ladycat

The track videokar was built against, kept here as the real-world test case.
`ladycat.mp3` is the author's own Suno-generated song and is not distributed
with the repo — the integration tests skip when it is absent.

## What this example is good for

It is not a clean case, which is the point.

**Stacked harmonies defeat the aligner, and the lyrics say so.** The first
chorus is tagged `[Chorus - wide, stacked harmonies, wall of guitars]`, and that
is exactly where alignment falls apart. Between roughly 50s and 64s the
character-level scores collapse to 0.01-0.02, an order of magnitude below the
0.19 median for the track: demucs hands back a chord of simultaneous voices
rather than one, and a model trained on a single speaker has almost nothing to
match. Measured against a Whisper transcript of the stem, the chorus lines in
that stretch land three to four seconds early and one is smeared across nine
seconds, while the lines on either side are correct to within a few hundred
milliseconds.

This is the case `videokar check` exists to surface and `videokar fix` exists to
repair. It does not get better by feeding the aligner more context: an earlier
version of `lyrics.txt` was missing the fourth chorus phrase, and restoring it
moved the errors around without removing them.

**The sections repeat.** Four "Two purrs and then she's gone" across the song is
exactly the case where transcription-only tools collapse the repeats into one.

**There is a second voice, and stage directions.** Every parenthesised line is
an answering vocal. `[higher harmony]` and `[all voices]` sit inside the chorus
and must not be mistaken for section headers, and `[Soft Intro]`,
`[Instrumental]` and `[Fade-Outro]` are sections with no lines at all.

## Reference numbers

Measured on an M3 Pro, torch 2.13, demucs 4.1: 200 words over 36 lines.

| stage | time | device |
| --- | --- | --- |
| separation (htdemucs), first run | ~40s | mps |
| separation, cached | instant | — |
| alignment (MMS_FA, 180s track) | ~6s | mps + cpu |

The first alignment of all also pays a one-off 1.2 GB model download. Eight of
the thirty-six lines come back flagged, all of them in or next to the two
choruses.
