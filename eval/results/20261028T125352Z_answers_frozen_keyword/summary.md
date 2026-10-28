# Answer evaluation: 20261028T125352Z_answers_frozen_keyword

## Run details

| Item | Value |
|---|---|
| Run (UTC) | 20261028T125352Z |
| Case set | frozen |
| Cases run | 60 |
| Case file SHA-256 | 73d9b0f6b1f1a7a7b34d0d17bed9b61a1feee35ebaa3d2779316ad9989b6ed09 |
| Provider | openai |
| Model reported by the API | gpt-6-luna |
| Reasoning effort | not sent |
| Retrieval | keyword |
| Passages per question | 5 |
| Chunking | strategy section, max_words 160, overlap_words 40 |
| Embedding model | None |
| Documents in force on | 2026-10-01 |
| Corpus fingerprint | 1b62a68bc1b2a3df |
| Prices checked | 2026-10-28 |
| Code version | commit 61317ad0104a8bcaa5b03c0a31f9592f44a420c0, uncommitted_changes False |
| Package versions | python 3.13.16, ops-assistant 0.1.0, openai 3.40.0, numpy 2.5.4 |

## Results by category

Passed (auto): the expected outcome, every key fact present and no forbidden phrase. Evidence columns cover cases with labelled evidence. This is an automatic check; the human review section records whether answers are supported by their citations.

| Category | Cases | Passed (auto) | Outcome correct | Evidence retrieved | Evidence recall | Cites relevant section | Citations removed | Errors |
|---|---|---|---|---|---|---|---|---|
| supported | 30 | 21/30 (70%) | 22/30 (73%) | 22/30 (73%) | 0.73 | 22/22 (100%) | 0 | 0 |
| unsupported | 10 | 10/10 (100%) | 10/10 (100%) | - | - | - | 0 | 0 |
| multi_document | 10 | 9/10 (90%) | 10/10 (100%) | 10/10 (100%) | 0.90 | 10/10 (100%) | 0 | 0 |
| adversarial | 10 | 10/10 (100%) | 10/10 (100%) | 9/9 (100%) | 1.00 | 9/9 (100%) | 0 | 0 |

## Outcomes

| Expected \ actual | answered | insufficient_evidence | conflicting_evidence | error |
|---|---|---|---|---|
| answered | 39 | 8 | 0 | 0 |
| insufficient_evidence | 0 | 11 | 0 | 0 |
| conflicting_evidence | 0 | 0 | 2 | 0 |

## Time, tokens and cost

| Measure | Median | 95th percentile |
|---|---|---|
| Retrieval time (ms) | 0.3 | 0.4 |
| Generation time (ms) | 1831 | 3249 |
| Total time (ms) | 1831 | 3249 |
| Input tokens | 908 | 996 |
| Output tokens | 86 | 188 |
| Reasoning tokens (part of output) | 0.0 | 104 |

Estimated cost of this run: $0.0085 for 60 questions ($0.14 per 1,000 questions at these prices). Questions that needed a provider retry: 0 of 60 (0 retries).

## Cases that did not pass the automatic check

| Case | Category | Type | What went wrong | Answer (excerpt) |
|---|---|---|---|---|
| F002 | supported | rule_application | outcome insufficient_evidence, expected answered | The policy requires an itemised receipt for claims over £10, but it does not say whether a receipt is needed for an £8 taxi fare. |
| F003 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | Claims must be genuine business expenses, supported by evidence, and approved before payment. The handbook passages provided do not speci... |
| F006 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The handbook passage provided gives an allowance of up to £25 per night for an evening meal when staying away overnight on business, but ... |
| F011 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The handbook passages provided do not say when you must notify your boss that you are ill. They only explain what sickness evidence is re... |
| F014 | supported | paraphrase | missing "15 minutes"; retrieved 0 of 1 evidence sections | This is a P1 (critical) incident because the depot cannot dispatch. The Service Desk assigns the priority when the incident is logged, bu... |
| F016 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The handbook passages provided do not specify when a lessons-learned meeting must be held after a critical outage. |
| F024 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The handbook passages provided do not say how quickly you must report a lost work computer or whom to contact. |
| F026 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The handbook passages provided do not specify how long CVs from unsuccessful applicants may be kept. |
| F030 | supported | paraphrase | outcome insufficient_evidence, expected answered; retrieved 0 of 1 evidence sections | The handbook does not specify how long it takes to settle a vendor’s bill once approved. It says supplier approval usually takes 10 worki... |
| F045 | multi_document | two_documents | missing "3 years"; retrieved 1 of 2 evidence sections | The sources do not specify how long IT incident tickets are kept. A P1 post-incident review meeting must take place within 5 working days... |
