# Answer evaluation: 20261028T125111Z_answers_frozen_embedding

## Run details

| Item | Value |
|---|---|
| Run (UTC) | 20261028T125111Z |
| Case set | frozen |
| Cases run | 60 |
| Case file SHA-256 | 73d9b0f6b1f1a7a7b34d0d17bed9b61a1feee35ebaa3d2779316ad9989b6ed09 |
| Provider | openai |
| Model reported by the API | gpt-6-luna |
| Reasoning effort | not sent |
| Retrieval | embedding |
| Passages per question | 5 |
| Chunking | strategy section, max_words 160, overlap_words 40 |
| Embedding model | text-embedding-3-small |
| Documents in force on | 2026-10-01 |
| Corpus fingerprint | 1b62a68bc1b2a3df |
| Prices checked | 2026-10-28 |
| Code version | commit 61317ad0104a8bcaa5b03c0a31f9592f44a420c0, uncommitted_changes False |
| Package versions | python 3.13.16, ops-assistant 0.1.0, openai 3.40.0, numpy 2.5.4 |

## Results by category

Passed (auto): the expected outcome, every key fact present and no forbidden phrase. Evidence columns cover cases with labelled evidence. This is an automatic check; the human review section records whether answers are supported by their citations.

| Category | Cases | Passed (auto) | Outcome correct | Evidence retrieved | Evidence recall | Cites relevant section | Citations removed | Errors |
|---|---|---|---|---|---|---|---|---|
| supported | 30 | 30/30 (100%) | 30/30 (100%) | 30/30 (100%) | 1.00 | 30/30 (100%) | 0 | 0 |
| unsupported | 10 | 10/10 (100%) | 10/10 (100%) | - | - | - | 0 | 0 |
| multi_document | 10 | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) | 0.90 | 10/10 (100%) | 0 | 0 |
| adversarial | 10 | 10/10 (100%) | 10/10 (100%) | 9/9 (100%) | 1.00 | 9/9 (100%) | 0 | 0 |

## Outcomes

| Expected \ actual | answered | insufficient_evidence | conflicting_evidence | error |
|---|---|---|---|---|
| answered | 47 | 0 | 0 | 0 |
| insufficient_evidence | 0 | 11 | 0 | 0 |
| conflicting_evidence | 0 | 0 | 2 | 0 |

## Time, tokens and cost

| Measure | Median | 95th percentile |
|---|---|---|
| Retrieval time (ms) | 165 | 272 |
| Generation time (ms) | 2283 | 4310 |
| Total time (ms) | 2453 | 4476 |
| Input tokens | 914 | 1110 |
| Output tokens | 88 | 226 |
| Reasoning tokens (part of output) | 11 | 116 |

Estimated cost of this run: $0.0088 for 60 questions ($0.15 per 1,000 questions at these prices). Questions that needed a provider retry: 0 of 60 (0 retries).

## Cases that did not pass the automatic check

No automatic failures.

## Human review

| Category | Reviewed | Correct | Partly correct | Supported by citations | Partly supported |
|---|---|---|---|---|---|
| supported | 30/30 (100%) | 29/30 (97%) | 1/30 (3%) | 30/30 (100%) | 0/30 (0%) |
| unsupported | 10/10 (100%) | 10/10 (100%) | 0/10 (0%) | 1/1 (100%) | 0/1 (0%) |
| multi_document | 10/10 (100%) | 10/10 (100%) | 0/10 (0%) | 9/10 (90%) | 1/10 (10%) |
| adversarial | 10/10 (100%) | 10/10 (100%) | 0/10 (0%) | 9/9 (100%) | 0/9 (0%) |

Automatic check agrees with the reviewer on 59/60 (98%) of reviewed cases.
