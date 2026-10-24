# Synthetic text and screenshot memory cases

Inspired by xiaowu0162/LongMemEval-V2 at 2cc8c54.

Use only inside an owner-requested memory evaluation. Create local synthetic cases;
do not download or redistribute benchmark questions, histories or screenshots.

1. Design a small matched history and question across static recall, changed state,
   workflow knowledge, environment gotchas and false premises. Include a visual fact
   that matters, such as a changed toggle or a warning shown only in a screenshot.
2. Compare text-only history, screenshot-bearing history and combined text/image
   history. Also separate text-only questions from screenshot questions when relevant.
   Hold the underlying facts, question and reader/context limits fixed; mark a case
   unmatched if text and image convey different information. Include conflicting or
   unreadable image cases whose correct result is uncertainty, not invented detail.
3. Retain visual evidence in the existing authorized evidence sink: synthetic source
   image identity/hash, relevant frame or crop, visible fact, time/order and matching
   text span. Preserve enough context to interpret the crop and any state changes.
4. Keep gold answers, case labels, assessment notes and benchmark metadata outside
   retrieval inputs. For image-question tasks, do not leak the gold as alt text,
   filenames or an OCR annotation unavailable in the declared condition. Record any
   preprocessing and ensure it does not silently change a screenshot-only condition.
5. Compare no-memory and candidate-memory for each supported modality on the same
   cases. Record retrieved text/image identities, supported answers, false-premise
   handling, latency and unreadable evidence. Missing image support is unevaluated;
   OCR-only behavior is not proof of image retrieval. Main reviews the trade-offs.

This adds no memory backend, runner or live replay authority. Synthetic results
support only the tested conditions; visual polish and judge agreement are advisory.
