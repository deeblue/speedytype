# Combined Gemini Investigation Report

Date: 2026-07-12

## API budget and execution

- Part A target: add five valid candidate repeated-input samples (historical candidate baseline: 1 valid) and run six current/candidate production-model dimension pairs. Budget: 17 successful calls plus at most three failed single attempts.
- Part B target: 17 unique `*_final.wav` files selected from both real-voice corpora after excluding take copies. Budget: 17 Whisper calls and 17 successful Gemini calls.
- Actual Part A: 19 Gemini attempts, 17 valid and two HTTP 503 responses. Candidate repeated-input testing added 5/5 number-preserving valid samples.
- Actual Part B: 17 Whisper calls succeeded. Gemini used 18 attempts for 17 valid outputs; one HTTP 429 was recorded, then the saved STT output was reused after the rate-limit interval.
- Total Gemini attempts: 37. API failures are excluded from semantic rates.

## Part A: prompt comparison

Historical and new repeated-input evidence:

| Prompt | Valid samples | Numbers preserved | Notes |
|---|---:|---:|---|
| Current, historical `gemini-3.5-flash` | 10 | 10/10 | Six earlier valid samples plus four valid samples from 2026-07-11 |
| Candidate, historical + new `gemini-3.5-flash` | 6 | 6/6 | One historical valid sample plus five new valid samples; two new 503s excluded |

Production-model (`gemini-3.1-flash-lite`) dimension check:

| Dimension | Current | Candidate | Result |
|---|---|---|---|
| Garbled repeated numbers | `測試。` | `123 test` | Candidate preserves the number; current reproduces the loss |
| Self-correction | `我們下週三要開會。` | Same | Both pass |
| Filler removal and key terms | `請 TPE 團隊今天同步 BIOS 狀態。` | Same | Both pass |
| List formatting | Three numbered items | Three numbered items | Both preserve all three items and format them as a list |
| Natural stutter | `我們下週三要開會。` | Same | Both remove only the stutter |
| Chinese number sequence | `測試 1、2、3、4` | Same | Both preserve all numbers |

Decision: adopt the candidate number/repeated-content rule. It fixes a reproduced production-model failure, has six valid repeated-input samples on the historical comparison model, and shows no regression in the other five dimensions.

## Part B: raw STT versus current polishing

`Corrected-away` means the named term appears only in the speaker's abandoned clause and should not appear in the final output under self-correction rule 2.

| Corpus / segment | Script target | Raw Whisper | Gemini polished | Classification |
|---|---|---|---|---|
| R1-03 | Keep `BJ 團隊` | `請 BJ 團隊確認 USB 相容性` | `請 BJ 團隊確認 USB 相容性。` | STT correct; LLM correct |
| R1-05 | Remove initial `API`; keep `BJ 團隊` | `文件先給 TPE 團隊 不對,先給 BJ 團隊確認術語` | `文件先給 BJ 團隊確認術語。` | STT already omitted abandoned API clause; LLM self-correction correct |
| R1-07 | Keep `BJ 團隊` | `TPE 團隊, BJ 團隊和 QA 需要在 NPI 會議前完成風險整理` | Same terms, normalized punctuation | STT correct; LLM correct |
| R1-08 | Keep `API` | Raw contains `把API測試結果寄給QA和TPE團隊` | List item retains `API` | STT correct; LLM correct |
| R1-09 | Remove initial `BJ 團隊` | Raw already begins with corrected `TPE 團隊` | Polished retains only corrected TPE instruction | STT collapsed self-correction correctly; LLM correct |
| R1-10 | Keep `API` | Keyword list contains `NPI` instead of `API` | Polished retains `NPI` | STT error (`API` -> `NPI`); no LLM over-correction |
| R2-02 | Keep `BJ 團隊` | `usb 相信先給 bj 團隊確認` | `USB 相關事項請先交由 BJ 團隊確認。` | STT target correct case-insensitively; LLM corrects casing |
| R2-03 | Keep `API` | `請把API規格同步給TPE團隊` | `請將 API 規格同步給 TPE 團隊。` | STT correct; LLM correct |
| R2-06 | Keep `BJ 團隊` | Raw contains `BJ 團隊` | Polished contains `BJ 團隊` | STT correct; LLM correct |
| R2-07 | Keep `API` | `AVM測試失敗...` | Polished retains `AVM` | STT error (`API` -> `AVM`); no LLM over-correction |
| R2-09 | Remove initial `BJ 團隊` | Raw contains `我本來想請 BJ 團隊...` then corrected TPE clause | Polished keeps only `TPE 團隊` | Correct self-correction; prior metric falsely counted missing BJ as an error |
| R2-10 | Remove initial `API` | Raw contains `API 文件,不對,應該先寄 NPI...` | Polished keeps only `NPI Checklist` | Correct self-correction; prior metric falsely counted missing API as an error |
| R2-11 | Keep `API` and `BJ 團隊` | Raw contains both | Polished list contains both | STT correct; LLM correct |
| R2-12 | Keep `BJ 團隊` | Raw contains `BJ 團隊` | Polished list contains `BJ 團隊` | STT correct; LLM correct |
| R2-13 | Keep `API` | Raw contains `API 變更` | Polished list contains `API 變更` | STT correct; LLM correct |
| R2-15 | Keep `API` and `BJ 團隊` | Raw contains both | Polished list contains both | STT correct; LLM correct |
| R2-16 | Keep `API` | Raw keyword list contains `API` | Polished list contains `API` | STT correct; LLM correct |

Final intended target-term counts across both corpora:

| Term | Final intended occurrences | STT correct | LLM final correct | STT-correct then LLM-wrong |
|---|---:|---:|---:|---:|
| `API` | 8 | 6 | 6 | 0 |
| `BJ 團隊` | 8 | 8 | 8 | 0 |
| Combined | 16 | 14 | 14 | 0/14 (0.0%) |

Conclusion: the LLM over-correction hypothesis is not supported. Both final-output errors were already present in raw STT. The earlier `API` 71.4% / `BJ 團隊` 83.3% contradiction was partly an evaluation artifact: the denominator included one corrected-away occurrence of each term. A defensive future refinement to rule 4 can still say not to replace a plausible existing proper noun without clear contextual evidence, but this corpus provides no direct failure requiring that change now.
