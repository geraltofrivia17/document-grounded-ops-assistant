# Evaluation method

The evaluation answers two separate questions:

1. **Retrieval:** are the passages needed to answer among those given to the model?
2. **Answers:** does the reply have the right outcome and the right facts, and do its citations support it?

They are measured separately, because a fluent answer can hide a retrieval miss and good retrieval can be wasted by a poor answer.

## Question sets

| File | Cases | Role |
|---|---|---|
| `eval/dev_cases.jsonl` | 24 (12 supported, 4 unsupported, 4 multi-document, 4 adversarial) | Choosing the retrieval configuration, checking the prompt, and finding failure modes |
| `eval/frozen_cases.jsonl` | 60 (30 supported, 10 unsupported, 10 multi-document, 10 adversarial) | Reporting only |

The two sets share no questions. The development conflict case uses a conflict (laptop replacement) that the frozen set doesn't use.

| Category | Subtypes |
|---|---|
| Supported | `single_fact`, `rule_application`, `paraphrase` (everyday wording that avoids the handbook's terms) |
| Unsupported | `not_covered`, `near_miss` (the handbook mentions something nearby, such as a car park or an on-call overtime rate) |
| Multi-document | `two_documents`: each answer needs sections from two documents |
| Adversarial | `version_false_premise`, `future_version`, `active_conflict`, `injection_in_document`, `injection_in_question` |

### Case fields

| Field | Use |
|---|---|
| `expected_outcome` | `answered`, `insufficient_evidence` or `conflicting_evidence` |
| `expected_answer` | Reference answer for the human reviewer |
| `evidence` | Sections (`DOC-ID#section`) required for a complete answer; retrieval recall is measured against these |
| `also_relevant` | Other sections that support the answer; citing them counts as relevant |
| `key_facts` | Groups of acceptable spellings; every group must appear in the answer |
| `computed_facts` | Facts derived by arithmetic (for example 100 miles × 45p = £45), which need not appear in a source |
| `must_not_say` | Phrases that make an answer wrong, such as text from the instructions or the injected document |
| `scoring` | Guidance for the reviewer |

A test checks that every evidence label names a section that exists in the documents in force, and that every key fact appears in the text of its evidence sections. Labels that cannot be satisfied by the handbook therefore fail the build.

### Freezing

The frozen file's SHA-256 is stored in `eval/frozen_cases.sha256`. The runner and the report both refuse to use the frozen file if it no longer matches, and CI runs `eval freeze --check`. The hash is computed with normalised line endings, so a Windows checkout gives the same value.

The frozen set was revised once before it was used: see the 28 October 2026 entry in [decisions.md](decisions.md). No model output was produced on the frozen set before it was frozen.

## Retrieval metrics

Computed for every answerable case (49 frozen, 20 development), at k = 5 unless stated:

| Metric | Definition |
|---|---|
| Hit@k | At least one required section appears in the top k |
| Hit@1 | The top chunk covers a required section |
| Recall@k | Share of the required sections covered by the top k (matters for multi-document cases) |
| MRR | Mean of 1 / rank of the first relevant chunk (0 if none) |
| Context words | Words in the top k chunks: what the model would read, a proxy for input cost |
| Search ms | Time to rank. Each question's embedding is fetched once beforehand, and that API latency is reported on its own line |

`eval retrieval` runs every combination of retrieval mode and chunking configuration on the same cases. Its report includes a table of which cases keyword search found and embeddings missed, and the reverse.

## Answer metrics

| Metric | Definition |
|---|---|
| Outcome correct | Returned outcome equals the expected outcome |
| Passed (automatic) | Answerable: outcome correct, every key fact present and no forbidden phrase. Unanswerable: outcome correct and no forbidden phrase |
| Cites relevant section | At least one surviving citation covers a required or also-relevant section |
| Citations removed | Citations dropped because they were unknown or not supplied |
| Errors | Requests that failed, by category |
| Time, tokens, cost | Median and 95th percentile; estimated cost per run and per 1,000 questions |

The outcome table lists expected against actual outcomes, so false abstentions (answerable questions declined) and false answers (unanswerable questions answered) show separately.

## Human review

Automatic scoring matches text. It cannot tell whether a cited passage actually supports a sentence, or whether an answer containing the right number is otherwise wrong. Every answer run therefore writes `review.csv`, with the question, the reference answer, the model's answer and the full text of each cited passage. The reviewer fills in:

| Column | Values |
|---|---|
| `human_correct` | `yes`, `partly` or `no`, compared with the reference answer and the scoring guidance |
| `human_supported` | `yes`, `partly` or `no`: is each claim backed by the cited text? `na` when nothing is cited |
| `human_notes` | Free text, especially for every `partly` and `no` |

Then rebuild the report with the review included:

```powershell
python -m ops_assistant eval report eval/results/<run> --review eval/results/<run>/review.csv
```

The report shows reviewed correctness and support by category, and how often the automatic check agrees with the reviewer.

## Procedure

1. Retrieval experiment on the development set: `eval retrieval --set dev`.
2. Choose the retrieval mode and chunking from the development results; record the decision.
3. Answer runs on the development set with the chosen configuration; inspect the failures, and change the prompt only if a failure shows a general problem.
4. Fix the configuration and commit it.
5. Run the frozen set once: `eval retrieval --set frozen` and `eval answers --set frozen`.
6. Review the frozen answers by hand and rebuild the report with the review.
7. Publish the headline numbers: `eval publish --answers <run> --retrieval <run> --review <csv>`.

## Limits

- The handbook and both question sets were written by the same author. The paraphrased questions reduce, but don't remove, the advantage this gives keyword search.
- Ten cases per category is small: one case moves a category's rate by ten points. Rates are always shown with their counts.
- Each frozen result comes from a single run. The model can answer differently on a repeat run, and run-to-run variation is not measured unless the run is repeated.
- Results apply to the model version reported in `run.json` and the prices recorded there.
