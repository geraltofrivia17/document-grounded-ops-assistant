# Answer evaluation: 20261028T124228Z_answers_dev_hybrid

## Run details

| Item | Value |
|---|---|
| Run (UTC) | 20261028T124228Z |
| Case set | dev |
| Cases run | 24 |
| Case file SHA-256 | d9977335f6648d76e5489e2ce126744a8399136fae2de1bebc8f42a78afe64c9 |
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
| Code version | commit unknown, uncommitted_changes True |
| Package versions | python 3.13.16, ops-assistant 0.1.0, openai 3.40.0, numpy 2.5.4 |

## Results by category

Passed (auto): the expected outcome, every key fact present and no forbidden phrase. Evidence columns cover cases with labelled evidence. This is an automatic check; the human review section records whether answers are supported by their citations.

| Category | Cases | Passed (auto) | Outcome correct | Evidence retrieved | Evidence recall | Cites relevant section | Citations removed | Errors |
|---|---|---|---|---|---|---|---|---|
| supported | 12 | 11/12 (92%) | 11/12 (92%) | 11/12 (92%) | 0.92 | 11/11 (100%) | 0 | 0 |
| unsupported | 4 | 3/4 (75%) | 3/4 (75%) | - | - | - | 0 | 0 |
| multi_document | 4 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 1.00 | 4/4 (100%) | 0 | 0 |
| adversarial | 4 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 1.00 | 4/4 (100%) | 0 | 0 |

## Outcomes

| Expected \ actual | answered | insufficient_evidence | conflicting_evidence | error |
|---|---|---|---|---|
| answered | 18 | 1 | 0 | 0 |
| insufficient_evidence | 1 | 3 | 0 | 0 |
| conflicting_evidence | 0 | 0 | 1 | 0 |

## Time, tokens and cost

| Measure | Median | 95th percentile |
|---|---|---|
| Retrieval time (ms) | 171 | 279 |
| Generation time (ms) | 1818 | 3086 |
| Total time (ms) | 2012 | 3251 |
| Input tokens | 914 | 996 |
| Output tokens | 78 | 218 |
| Reasoning tokens (part of output) | 0.0 | 138 |

Estimated cost of this run: $0.0033 for 24 questions ($0.14 per 1,000 questions at these prices). Questions that needed a provider retry: 0 of 24 (0 retries).

## Cases that did not pass the automatic check

| Case | Category | Type | What went wrong | Answer (excerpt) |
|---|---|---|---|---|
| D008 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The handbook does not specify how much notice is needed before a guest comes to site. The supplied access guidance covers contractors, no... |
| D014 | unsupported | not_covered | outcome answered, expected insufficient_evidence | The handbook does not specify the steps for ordering business cards. It does require a purchase order to be raised in the finance system ... |
