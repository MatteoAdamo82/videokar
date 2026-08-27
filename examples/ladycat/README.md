# ladycat

The track videokar was built against, kept here as the real-world test case.
`ladycat.mp3` is the author's own Suno-generated song and is not distributed
with the repo — the integration tests skip when it is absent.

## What this example is good for

It is not a clean case, which is the point. Three things about it exercise the
parts of the pipeline that a tidy track would not:

**The lyrics and the audio disagree.** `lyrics.txt` gives the first chorus three
lines:

```
Two purrs and then she's gone
Two purrs and then she's gone
I leave the bowl outside
```

Whisper, run over the demucs vocal stem, hears four phrases between 56s and 72s:
two "Two purrs", then "I leave the bowl outside", then "Two purrs" again. Suno
repeated a line that the written lyrics do not contain.

A forced aligner has to place every word somewhere, so it covers the difference
by stretching one line across roughly ten seconds and cramming the rest. That
region is what `videokar check` should light up, and what `videokar fix` is for.
Adding the missing line by hand does not rescue it either: the acoustic model
scores that whole stretch around 0.01, an order of magnitude below the rest of
the track, so it has no real evidence to align against whatever it is given.

**The sections repeat.** Four "Two purrs and then she's gone" across the song is
exactly the case where transcription-only tools collapse the repeats into one.

**There is a second voice.** Every parenthesised line is an answering vocal,
which is what the separate `paren` styling exists for.

## Reference numbers

Measured on an M3 Pro, torch 2.13, demucs 4.1:

| stage | time | device |
| --- | --- | --- |
| separation (htdemucs), first run | ~40s | mps |
| separation, cached | instant | — |
| alignment (MMS_FA, 180s track, 194 words) | ~6s | mps + cpu |

The first alignment of all also pays a one-off 1.2 GB model download.
