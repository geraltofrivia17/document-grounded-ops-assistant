# Decision log

Each entry records a decision, the alternatives considered and the evidence behind it. Later entries can overrule earlier ones; nothing is edited after the fact.

## 2026-10-28: OpenAI as the model provider, behind an interface

**Decision:** OpenAI for generation (Responses API) and embeddings, behind `llm/base.py` so that another provider can be added as one module.
**Why:** It is one of the providers most often named in UK AI engineering adverts, and its models are also offered through Azure. The interface keeps the answering pipeline and the tests independent of any one SDK.
**Alternatives:** Anthropic Claude (equally suitable technically), and a local model (no cost per call, but much slower on CPU and a large dependency).

## 2026-10-28: OpenAI embeddings rather than a local sentence-transformer

**Decision:** `text-embedding-3-small`.
**Why:** A local model adds a large dependency to the Docker image and has to be downloaded at build time. At the published price of about $0.02 per million tokens, embedding the whole handbook costs a tiny fraction of a cent, and the cache means each chunk is embedded once.
**Trade-off:** Embedding and hybrid retrieval need network access and a key. Keyword retrieval, the tests and CI do not.

## 2026-10-28: NumPy array instead of a vector database

**Decision:** Hold normalised vectors in one array and rank with a matrix product.
**Why:** The corpus is about a hundred chunks, so a brute-force search is one matrix-vector product, and the query's embedding call dominates the search time (the retrieval report measures search time per mode). A database would add a service to run and configure with no benefit at this size.
**Revisit when:** The corpus reaches tens of thousands of chunks, or filtering by metadata at query time is needed.

## 2026-10-28: BM25 implemented in the project, with stemming

**Decision:** Okapi BM25 (k1 = 1.5, b = 0.75) in about sixty lines, Snowball English stemming, and a short stopword list that keeps negations such as "not" and "without".
**Why:** BM25 is the baseline the other methods are judged against, so it should be fully visible and fair. Without stemming, "returned" would not match "return", which would make the baseline weaker than it needs to be.

## 2026-10-28: Effective-document rule with a fixed as-of date

**Decision:** Superseded and future-dated versions are excluded at load time, and the date is fixed in settings (1 October 2026).
**Why:** Excluding them before indexing means no later step can leak an old rule, and the tests can prove it. A fixed date keeps the evaluation reproducible: the travel policy version that takes effect on 1 January 2027 would otherwise change answers depending on the day of the run.
**Trade-off:** Questions about history ("what was the old mileage rate?") cannot be answered. That is acceptable for an assistant that answers what applies now.

## 2026-10-28: Section-bounded chunks by default, windows as the comparison

**Decision:** Chunks stay within one numbered section, splitting a section only if it is longer than 160 words. Fixed windows of 80 to 320 words that cross sections are compared in the retrieval experiment.
**Why:** Sections in this handbook are short and self-contained, so a section is a natural unit and keeps each citation precise. Windows give the model more context per chunk at the cost of more input tokens and less precise citations. The experiment measures both.

## 2026-10-28: Structured outputs plus citation checks in code

**Decision:** A strict JSON schema for the reply, followed by code that removes any cited id that is unknown or was not supplied, and that rejects an `answered` reply left with no valid citation.
**Why:** The schema guarantees the shape of the reply, not that its citations are real. Rejecting an uncited answer is safer than showing it: the client receives `answer_not_verifiable` and can retry or escalate.
**Not covered by these checks:** whether a real, supplied passage actually supports the claim. That is measured by human review in the evaluation.

## 2026-10-28: Three outcomes; conflicts are reported, not resolved

**Decision:** `answered`, `insufficient_evidence` and `conflicting_evidence`. When two documents in force disagree, the assistant states both and cites both.
**Why:** Picking one would be a policy decision that belongs to the document owners. Reporting the conflict is also how it gets fixed.

## 2026-10-28: Skip the model when nothing matches

**Decision:** With keyword retrieval, a question that shares no term with any chunk returns `insufficient_evidence` without calling the model.
**Why:** No call is needed to decline a question the handbook has no words for. Embedding retrieval always returns its nearest chunks, so this shortcut only applies to keyword mode.

## 2026-10-28: Failures are categorised and kept apart from abstentions

**Decision:** Each failure has a category, an HTTP status and a stage (see [architecture.md](architecture.md)). An abstention is a normal 200 response.
**Why:** A client must be able to tell "try again later" from "the handbook does not say". The SDK retries once on connection errors, 408, 409, 429 and 5xx, with a 30-second timeout per attempt. A run of the evaluation stops at once on a missing key, a rejected key or exhausted credit, because every following call would fail the same way.

## 2026-10-28: Questions are not logged

**Decision:** Logs record the question's length, not its text.
**Why:** Staff questions can include personal details, such as sickness. The retrieved and cited chunk ids are enough to investigate a bad answer.

## 2026-10-28: Paraphrased questions added before the first frozen run

**Decision:** 15 of the 30 supported frozen questions and 6 of the 12 supported development questions were rewritten in everyday wording, and the frozen set was re-frozen (`73d9b0f6b1f1...`).
**Why:** During development, keyword retrieval on the first version of the frozen set found the required section for every supported question. The questions had been written by the handbook's author and reused its vocabulary, so the retrieval comparison could not show anything. The rewrite was made before any model had answered a frozen question, and no frozen-set result has been used to choose a setting since.
**Effect:** Keyword-only retrieval now misses evidence on a number of supported frozen questions, which is what the comparison needs to be meaningful. The exact figures are in the published retrieval report.

## 2026-10-28: Five-second embedding timeout; retries and provider request ids recorded

**Evidence:** in the first development retrieval run (`20261028T123243Z_retrieval_dev_k5`), 18 of the 20 question-embedding calls took 146 to 228 ms and two took 30,681 ms and 30,774 ms. That matches the 30-second request timeout expiring and the SDK's automatic retry, after a 0.5-second backoff, then succeeding.
**Decision:** embeddings get their own timeout of 5 seconds (`embedding.timeout_seconds`), about twenty times the slowest normal call, so a stuck call is retried after seconds. Generation keeps 30 seconds, because answers took 3 to 6 seconds on the first live calls. Every response now reports the number of retries and OpenAI's request id, and the SDK's "Retrying request" log line is kept at INFO.
**Why:** a timeout set far above normal latency doesn't make a call more reliable; it only makes a failure slower. Without the retry count, a 30-second answer would look like slow retrieval rather than a hidden retry.

## 2026-10-28: Retrieval latency measured separately from ranking

**Problem found:** the first development retrieval run cached each question's embedding after its first use. Only the first configuration paid the API call, so later rows showed embedding and hybrid search times near 0 ms. Recall and ranking results were unaffected, but the latency columns understated what embedding retrieval costs.
**Decision:** the experiment now embeds each question once before ranking, times every call and reports that latency on its own line. The search-time columns then measure ranking alone. Answer runs embed each question live, as the service does, so their retrieval times include the API call. The on-disk query cache was removed.

## 2026-10-28: Embedding retrieval, section chunks and gpt-6-luna for the frozen run

**Evidence (development set only):**

| Run | Measure | Keyword | Embedding | Hybrid |
|---|---|---|---|---|
| `20261028T124026Z_retrieval_dev_k5` (section-160-40, 20 cases) | Hit@1 | 16/20 | 19/20 | 19/20 |
| | Hit@5 | 19/20 | 20/20 | 19/20 |
| | MRR | 0.86 | 0.97 | 0.95 |
| `..._answers_dev_<mode>` (24 cases) | Passed automatic check | 22/24 | 24/24 | 22/24 |
| | Median total time | 2,070 ms | 1,989 ms | 2,012 ms |
| | Cost of the run | $0.0033 | $0.0033 | $0.0033 |

Question embeddings cost a median 178.5 ms per question (95th percentile 373.2 ms, 20 calls, no retries).

**Decision:** embedding retrieval with section chunks (160 words, 40 overlap) and `gpt-6-luna`.
**Why:**
- Embeddings found the evidence that keyword search missed for D008 ("before a guest comes to site", which needs the visitor-registration rule). With the evidence missing, the model declined rather than invent an answer, which is the right behaviour, but a declined answerable question is still a failure.
- Hybrid did not improve on embeddings here: fusion gave keyword search's wrong top result equal weight, and D008 was missed again.
- Windows added no recall for embeddings (already 20/20 at hit@5) and sent the model three to five times as much text. Section-40-10 scored one case higher at hit@1 (20/20). One case in 20 is not enough to justify splitting sections that are already short.
- `gpt-6-luna` passed every development case at about $0.14 per 1,000 questions, so a larger model was not needed.

**Caveat:** the differences are one or two cases out of 20 or 24. The frozen set is the larger test.

**Open question noted, not tuned:** with keyword and hybrid retrieval, D014 ("How do I order business cards?") was answered from the general purchase-order rule instead of being declined. Rule 3 of the prompt allows answering the covered part of a question, so this is a boundary between a partial answer and a near miss. The prompt was not changed on the strength of one development case. The frozen near-miss cases (F038, F039) will show whether it matters.

## 2026-10-28: How the frozen set will be run (decided before running it)

- Code and configuration are committed first, so each `run.json` records the commit.
- The frozen set is run once with each retrieval mode. **Embedding is the reported configuration**; keyword and hybrid are reported only as comparisons, to show whether better retrieval leads to better answers.
- The retrieval experiment is run once on the frozen set with the same five chunkings.
- Nothing is changed after seeing frozen results. Any change prompted by them is logged here and evaluated on new development cases, never by re-running the frozen set and reporting the better result.
- The embedding run's answers are reviewed by hand before publishing.
