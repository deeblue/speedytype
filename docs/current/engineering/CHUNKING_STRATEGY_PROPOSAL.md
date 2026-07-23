# SpeedyType Chunking Strategy Proposal

Status: proposal, not production architecture.

This document compares Deepgram and DeepL Voice stream-boundary behavior only
as a segmentation-design reference. It does not propose replacing
SpeedyType's production STT path with a streaming API.

## Scope

SpeedyType's accepted production path remains:

```text
durable WAV -> validated lossless FLAC -> complete-file whisper-1 JSON
```

The question here is narrower: can stream-oriented providers teach us better
ways to choose chunk boundaries when SpeedyType needs chunking for experiments,
future background pre-processing, or recordings that exceed a complete-file
provider limit?

## Current SpeedyType Chunking Baseline

`speedytype/chunking.py` already has the right basic shape:

- frame-level RMS analysis;
- adaptive noise floor;
- silence enter/exit hysteresis;
- minimum, preferred, and maximum chunk lengths;
- silence cuts when available;
- forced cuts only when no usable silence exists;
- small context overlap for natural cuts and larger overlap for forced cuts.

Current defaults:

```text
min_chunk_seconds = 15
preferred_chunk_seconds = 25
max_chunk_seconds = 45
minimum_silence_seconds = 0.6
natural_cut_context_seconds = 0.2
forced_cut_overlap_seconds = 1.5
analysis_frame_ms = 20
```

The weaknesses are not the presence of silence-aware chunking, but the lack of
a richer boundary model:

- every detected silence is treated similarly;
- pause duration is static rather than adapted to speech rate and noise;
- a forced cut is time-based, not boundary-quality-based;
- merge validation happens after transcription, not during boundary selection;
- the planner does not distinguish provisional boundaries from committed
  utterance boundaries.

## Deepgram Boundary Model

Deepgram separates several concepts that are easy to conflate:

- `is_final`: a transcript span has reached a final textual form.
- `speech_final`: endpointing has detected a natural end of speech after a
  pause.
- `UtteranceEnd`: a separate end-of-utterance event based on gaps after final
  words.

The useful design lesson is not "use Deepgram streaming"; it is the separation
between:

```text
text stability != utterance boundary
```

For SpeedyType, this maps to:

- a chunk may be safe enough to transcribe;
- but the cut may still not be a safe semantic/utterance boundary;
- therefore chunk finalization should depend on boundary confidence, not only
  elapsed time.

## DeepL Voice Boundary Model

DeepL Voice exposes a concluded/tentative distinction:

- concluded segments are fixed and appended once;
- tentative segments are provisional and may be replaced as more context
  arrives.

The useful design lesson is:

```text
commit only stable segments; keep edge context provisional
```

For SpeedyType, this argues against treating the last words near a chunk edge
as immediately authoritative. A chunking system should preserve a small
uncommitted tail around uncertain boundaries and only commit it once the next
chunk confirms continuity.

## Proposed SpeedyType Boundary Model

Introduce a local boundary score for every candidate cut:

```text
boundary_score =
  silence_duration_score
  + silence_depth_score
  + distance_to_preferred_chunk_score
  + post_boundary_speech_restart_score
  - forced_cut_penalty
  - high_energy_edge_penalty
```

Candidate boundary classes:

| Class | Meaning | Handling |
|---|---|---|
| `concluded` | Strong acoustic pause, low edge energy, speech restarts cleanly | Cut with no or minimal overlap |
| `tentative` | Pause exists but is short, noisy, or near speech edge | Cut allowed, retain provisional overlap |
| `forced` | No acceptable pause before max duration | Cut at max, retain larger overlap and require merge validation |

This borrows Deepgram's endpointing/utterance distinction and DeepL's
concluded/tentative distinction, but applies them locally to WAV segmentation.

## Concrete Planner Changes

### 1. Replace "silence exists" with scored silence candidates

Current planner picks the silence nearest the preferred duration. The revised
planner should score all candidate silences between min and max duration.

Inputs:

- silence duration;
- silence RMS relative to nearby speech RMS;
- cut distance from `preferred_chunk_seconds`;
- energy in the 200 ms before and after the cut;
- whether speech resumes clearly after the cut.

Expected effect:

- avoid weak noisy pauses;
- prefer deeper natural pauses even if they are slightly farther from the
  preferred duration;
- reduce boundary word splits.

### 2. Add an endpoint wait/lookahead model

Do not finalize a candidate cut the instant silence starts. Require a small
lookahead window after the silence to classify it:

```text
candidate pause starts
  -> wait/look ahead 300-800 ms
  -> if speech restarts cleanly: concluded boundary
  -> if not enough evidence: tentative boundary
```

For offline WAV this is just lookahead analysis. For future background
processing it maps naturally to a delayed commit.

### 3. Keep edge text provisional for tentative/forced cuts

For tentative and forced boundaries, chunk N should not fully own the final
edge words. Use overlap, but track it explicitly:

```text
chunk N committed body
chunk N provisional tail
chunk N+1 confirms or replaces the tail
```

This is the DeepL concluded/tentative idea applied to local chunk merging.

### 4. Use different overlap policies per boundary class

Suggested starting values:

| Boundary class | Overlap |
|---|---:|
| `concluded` | 0.0-0.2 s |
| `tentative` | 0.5-1.0 s |
| `forced` | 1.5-2.0 s |

This avoids the earlier failure mode where overlap was applied uniformly and
introduced duplicate or corrupted edge text.

### 5. Add boundary diagnostics before ASR

Every chunk plan should record:

- start/end sample index;
- boundary class;
- boundary score;
- silence duration;
- pre/post edge RMS;
- overlap seconds;
- reason for forced cuts.

This makes failed transcripts debuggable without replaying the experiment.

## Validation Gates

Do not accept a new chunking strategy on latency alone.

Required gates:

1. PCM conservation:
   - no dropped samples;
   - exact source coverage with declared overlaps only.
2. Boundary diagnostics:
   - no high-energy forced cut unless max duration required it;
   - every forced cut recorded.
3. Transcript quality:
   - for English fixtures: WER versus reference;
   - for Chinese fixtures: ordered coverage, missing sentences, number
     preservation, key-term recall, and human checklist.
4. Merge safety:
   - no new duplicate sentences;
   - no active-audio gaps above the existing threshold;
   - no unexplained abnormal text-density chunks.
5. Fallback:
   - any failed validation returns to complete-file `whisper-1` when the file
     is admissible.

## Experiment Plan

### Phase A — offline planner only

No API calls.

- Run current and scored planners on existing long fixtures.
- Compare chunk count, forced-cut count, overlap duration, and high-energy edge
  count.
- Produce a boundary report.

Pass condition:

- scored planner reduces weak/forced boundary count without increasing total
  overlap materially.

### Phase B — paid ASR comparison on existing fixtures

Use the same audio and same STT model as existing experiments.

Strategies:

1. current `plan_dynamic_chunks`;
2. scored boundary planner;
3. scored planner with tentative-tail merge.

Pass condition:

- quality is at or above current complete-file baseline floors;
- tail/request amplification is explicitly reported;
- any failure stops the experiment and preserves the report.

### Phase C — background-processing prototype only if Phase B passes

Do not replace production.

- Feed recorded audio blocks into the planner during capture.
- Commit only concluded chunks.
- Keep tentative/forced tail uncommitted.
- On stop, transcribe only the final uncommitted region when safe; otherwise
  complete-file fallback.

## Non-goals

- Do not switch production STT to Deepgram or DeepL Voice as part of this
  proposal.
- Do not remove durable WAV capture.
- Do not remove complete-file `whisper-1` fallback.
- Do not accept a chunked path that passes speed tests but fails quality gates.

## Recommendation

The next implementation should be a planner-only spike:

```text
add boundary scoring + diagnostics
compare against current planner without ASR cost
```

This is low risk and directly answers whether Deepgram/DeepL-style boundary
semantics can improve SpeedyType's chunking before any provider, API, or UI
change is considered.

## References

- Deepgram endpointing: https://developers.deepgram.com/docs/endpointing
- Deepgram endpointing and interim results:
  https://developers.deepgram.com/docs/understand-endpointing-interim-results
- Deepgram utterance end:
  https://developers.deepgram.com/docs/utterance-end
- DeepL Voice sessions:
  https://developers.deepl.com/docs/voice/understanding-voice-sessions
- DeepL Voice WebSocket streaming:
  https://developers.deepl.com/api-reference/voice/websocket-streaming
