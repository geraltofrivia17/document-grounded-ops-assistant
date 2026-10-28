# Answer evaluation: 20261028T125711Z_answers_frozen_hybrid

## Run details

| Item | Value |
|---|---|
| Run (UTC) | 20261028T125711Z |
| Case set | frozen |
| Cases run | 60 |
| Case file SHA-256 | 73d9b0f6b1f1a7a7b34d0d17bed9b61a1feee35ebaa3d2779316ad9989b6ed09 |
| Provider | openai |
| Model reported by the API | gpt-6-luna |
| Reasoning effort | not sent |
| Retrieval | hybrid |
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
| supported | 30 | 27/30 (90%) | 28/30 (93%) | 28/30 (93%) | 0.93 | 28/28 (100%) | 0 | 0 |
| unsupported | 10 | 10/10 (100%) | 10/10 (100%) | - | - | - | 0 | 0 |
| multi_document | 10 | 9/10 (90%) | 10/10 (100%) | 10/10 (100%) | 0.95 | 10/10 (100%) | 0 | 0 |
| adversarial | 10 | 10/10 (100%) | 10/10 (100%) | 9/9 (100%) | 1.00 | 9/9 (100%) | 0 | 0 |

## Outcomes

| Expected \ actual | answered | insufficient_evidence | conflicting_evidence | error |
|---|---|---|---|---|
| answered | 45 | 2 | 0 | 0 |
| insufficient_evidence | 0 | 11 | 0 | 0 |
| conflicting_evidence | 0 | 0 | 2 | 0 |

## Time, tokens and cost

| Measure | Median | 95th percentile |
|---|---|---|
| Retrieval time (ms) | 183 | 226 |
| Generation time (ms) | 1687 | 3408 |
| Total time (ms) | 1868 | 3574 |
| Input tokens | 914 | 1089 |
| Output tokens | 78 | 226 |
| Reasoning tokens (part of output) | 0.0 | 94 |

Estimated cost of this run: $0.0085 for 60 questions ($0.14 per 1,000 questions at these prices). Questions that needed a provider retry: 0 of 60 (0 retries).

## Cases that did not pass the automatic check

| Case | Category | Type | What went wrong | Answer (excerpt) |
|---|---|---|---|---|
| F002 | supported | rule_application | outcome insufficient_evidence, expected answered | The policy requires an itemised receipt for claims over £10, but it does not say whether a receipt is needed for an £8 taxi fare. |
| F014 | supported | paraphrase | missing "15 minutes"; retrieved 0 of 1 evidence sections | This is a P1 (critical) incident because the depot cannot dispatch. The sources do not specify how quickly IT must pick up a P1 ticket. |
| F024 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The supplied handbook passages do not say how quickly you must report a lost work computer or who to tell. That reporting procedure is no... |
| F045 | multi_document | two_documents | missing "3 years"; retrieved 1 of 2 evidence sections | The handbook does not specify how long IT incident tickets are kept. A P1 post-incident review meeting must take place within 5 working d... |
