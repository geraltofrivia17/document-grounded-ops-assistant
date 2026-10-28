# Retrieval experiment: 20261028T123243Z_retrieval_dev_k5

## Run details

| Item | Value |
|---|---|
| Run (UTC) | 20261028T123243Z |
| Case set | dev |
| Cases with labelled evidence | 20 |
| Case file SHA-256 | d9977335f6648d76e5489e2ce126744a8399136fae2de1bebc8f42a78afe64c9 |
| Embedding model | text-embedding-3-small |
| Keyword stemming | True |
| Hybrid candidates per retriever | 20 |
| RRF k | 60 |
| Corpus fingerprint | 1b62a68bc1b2a3df |
| Code version | commit unknown, uncommitted_changes True |

## All configurations

Recall counts how many of a case's required sections appear in the top results. Context words is the text that would be sent to the model, a proxy for cost.

| Chunking | Mode | Cases | Hit@1 | Hit@5 | Recall@5 | MRR | Context words | Search ms (median) | Search ms (p95) |
|---|---|---|---|---|---|---|---|---|---|
| section-160-40 | keyword | 20 | 16/20 (80%) | 19/20 (95%) | 0.95 | 0.86 | 195 | 0.2 | 0.3 |
| section-160-40 | embedding | 20 | 19/20 (95%) | 20/20 (100%) | 1.00 | 0.97 | 201 | 169 | 30685 |
| section-160-40 | hybrid | 20 | 19/20 (95%) | 19/20 (95%) | 0.95 | 0.95 | 204 | 0.3 | 0.4 |
| section-40-10 | keyword | 20 | 16/20 (80%) | 19/20 (95%) | 0.95 | 0.86 | 149 | 0.2 | 0.3 |
| section-40-10 | embedding | 20 | 20/20 (100%) | 20/20 (100%) | 1.00 | 1.00 | 150 | 0.1 | 0.1 |
| section-40-10 | hybrid | 20 | 19/20 (95%) | 20/20 (100%) | 1.00 | 0.96 | 148 | 0.3 | 0.4 |
| window-80-20 | keyword | 20 | 16/20 (80%) | 19/20 (95%) | 0.95 | 0.88 | 295 | 0.2 | 0.3 |
| window-80-20 | embedding | 20 | 18/20 (90%) | 20/20 (100%) | 0.97 | 0.94 | 292 | 0.0 | 0.1 |
| window-80-20 | hybrid | 20 | 17/20 (85%) | 20/20 (100%) | 1.00 | 0.91 | 288 | 0.2 | 0.3 |
| window-160-40 | keyword | 20 | 19/20 (95%) | 19/20 (95%) | 0.95 | 0.95 | 621 | 0.1 | 0.2 |
| window-160-40 | embedding | 20 | 19/20 (95%) | 20/20 (100%) | 1.00 | 0.97 | 622 | 0.0 | 0.0 |
| window-160-40 | hybrid | 20 | 18/20 (90%) | 20/20 (100%) | 1.00 | 0.95 | 631 | 0.2 | 0.3 |
| window-320-60 | keyword | 20 | 18/20 (90%) | 20/20 (100%) | 1.00 | 0.93 | 1070 | 0.1 | 0.2 |
| window-320-60 | embedding | 20 | 17/20 (85%) | 20/20 (100%) | 1.00 | 0.93 | 1123 | 0.0 | 0.0 |
| window-320-60 | hybrid | 20 | 18/20 (90%) | 20/20 (100%) | 1.00 | 0.95 | 1107 | 0.2 | 0.3 |

## By category (section-160-40)

| Mode | Category | Cases | Hit@5 | Recall@5 |
|---|---|---|---|---|
| keyword | supported | 12 | 11/12 (92%) | 0.92 |
| keyword | multi_document | 4 | 4/4 (100%) | 1.00 |
| keyword | adversarial | 4 | 4/4 (100%) | 1.00 |
| embedding | supported | 12 | 12/12 (100%) | 1.00 |
| embedding | multi_document | 4 | 4/4 (100%) | 1.00 |
| embedding | adversarial | 4 | 4/4 (100%) | 1.00 |
| hybrid | supported | 12 | 11/12 (92%) | 0.92 |
| hybrid | multi_document | 4 | 4/4 (100%) | 1.00 |
| hybrid | adversarial | 4 | 4/4 (100%) | 1.00 |

## Keyword against embedding (section-160-40, hit@5)

| Found by | Cases | Case ids |
|---|---|---|
| both | 19 | D001, D002, D003, D004, D005, D006, D007, D009, D010, D011, D012, D017, D018, D019, D020, D021, D022, D023, D024 |
| keyword only | 0 | - |
| embedding only | 1 | D008 |
| neither | 0 | - |

## Cases with missing evidence (section-160-40)

| Mode | Case | Question | Needed | Top 3 retrieved |
|---|---|---|---|---|
| keyword | D008 | How much notice do I need to give before a guest comes to site? | FAC-401#1 | HR-204#2; FAC-401#2; SEC-303#5 |
| hybrid | D008 | How much notice do I need to give before a guest comes to site? | FAC-401#1 | HR-204#2; FAC-401#2; OPS-104#5 |
