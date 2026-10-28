# Retrieval experiment: 20261028T125110Z_retrieval_frozen_k5

## Run details

| Item | Value |
|---|---|
| Run (UTC) | 20261028T125110Z |
| Case set | frozen |
| Cases with labelled evidence | 49 |
| Case file SHA-256 | 73d9b0f6b1f1a7a7b34d0d17bed9b61a1feee35ebaa3d2779316ad9989b6ed09 |
| Embedding model | text-embedding-3-small |
| Keyword stemming | True |
| Hybrid candidates per retriever | 20 |
| RRF k | 60 |
| Corpus fingerprint | 1b62a68bc1b2a3df |
| Code version | commit 61317ad0104a8bcaa5b03c0a31f9592f44a420c0, uncommitted_changes False |

## All configurations

Recall counts how many of a case's required sections appear in the top results. Context words is the text that would be sent to the model, a proxy for cost. Search times are ranking only: each question's embedding was fetched once beforehand and its latency is reported below.

| Chunking | Mode | Cases | Hit@1 | Hit@5 | Recall@5 | MRR | Context words | Search ms (median) | Search ms (p95) |
|---|---|---|---|---|---|---|---|---|---|
| section-160-40 | keyword | 49 | 33/49 (67%) | 41/49 (84%) | 0.82 | 0.75 | 202 | 0.2 | 0.3 |
| section-160-40 | embedding | 49 | 42/49 (86%) | 49/49 (100%) | 0.98 | 0.93 | 212 | 0.0 | 0.1 |
| section-160-40 | hybrid | 49 | 39/49 (80%) | 47/49 (96%) | 0.95 | 0.86 | 208 | 0.2 | 0.4 |
| section-40-10 | keyword | 49 | 35/49 (71%) | 42/49 (86%) | 0.83 | 0.78 | 152 | 0.2 | 0.3 |
| section-40-10 | embedding | 49 | 44/49 (90%) | 49/49 (100%) | 0.96 | 0.94 | 149 | 0.0 | 0.1 |
| section-40-10 | hybrid | 49 | 39/49 (80%) | 47/49 (96%) | 0.96 | 0.87 | 150 | 0.3 | 0.4 |
| window-80-20 | keyword | 49 | 34/49 (69%) | 44/49 (90%) | 0.87 | 0.79 | 289 | 0.2 | 0.3 |
| window-80-20 | embedding | 49 | 44/49 (90%) | 49/49 (100%) | 0.99 | 0.94 | 292 | 0.0 | 0.0 |
| window-80-20 | hybrid | 49 | 39/49 (80%) | 46/49 (94%) | 0.93 | 0.86 | 288 | 0.2 | 0.3 |
| window-160-40 | keyword | 49 | 39/49 (80%) | 47/49 (96%) | 0.96 | 0.86 | 614 | 0.1 | 0.2 |
| window-160-40 | embedding | 49 | 41/49 (84%) | 49/49 (100%) | 1.00 | 0.90 | 610 | 0.0 | 0.0 |
| window-160-40 | hybrid | 49 | 41/49 (84%) | 47/49 (96%) | 0.96 | 0.89 | 615 | 0.2 | 0.3 |
| window-320-60 | keyword | 49 | 40/49 (82%) | 47/49 (96%) | 0.95 | 0.87 | 1108 | 0.1 | 0.2 |
| window-320-60 | embedding | 49 | 46/49 (94%) | 49/49 (100%) | 1.00 | 0.97 | 1128 | 0.0 | 0.0 |
| window-320-60 | hybrid | 49 | 44/49 (90%) | 48/49 (98%) | 0.98 | 0.92 | 1119 | 0.2 | 0.2 |

Embedding API calls for the questions: 49 calls, median 163.1 ms, 95th percentile 328.4 ms, slowest 1242.2 ms, 0 retries. Embedding and hybrid retrieval add one such call to every question.

## By category (section-160-40)

| Mode | Category | Cases | Hit@5 | Recall@5 |
|---|---|---|---|---|
| keyword | supported | 30 | 22/30 (73%) | 0.73 |
| keyword | multi_document | 10 | 10/10 (100%) | 0.90 |
| keyword | adversarial | 9 | 9/9 (100%) | 1.00 |
| embedding | supported | 30 | 30/30 (100%) | 1.00 |
| embedding | multi_document | 10 | 10/10 (100%) | 0.90 |
| embedding | adversarial | 9 | 9/9 (100%) | 1.00 |
| hybrid | supported | 30 | 28/30 (93%) | 0.93 |
| hybrid | multi_document | 10 | 10/10 (100%) | 0.95 |
| hybrid | adversarial | 9 | 9/9 (100%) | 1.00 |

## Keyword against embedding (section-160-40, hit@5)

| Found by | Cases | Case ids |
|---|---|---|
| both | 41 | F001, F002, F004, F005, F007, F008, F009, F010, F012, F013, F015, F017, F018, F019, F020, F021, F022, F023, F025, F027, F028, F029, F041, F042, F043, F044, F045, F046, F047, F048, F049, F050, F051, F052, F053, F054, F055, F056, F057, F059, F060 |
| keyword only | 0 | - |
| embedding only | 8 | F003, F006, F011, F014, F016, F024, F026, F030 |
| neither | 0 | - |

## Cases with missing evidence (section-160-40)

| Mode | Case | Question | Needed | Top 3 retrieved |
|---|---|---|---|---|
| keyword | F003 | What's the cut-off for getting my out-of-pocket costs reimbursed? | HR-201#2 | HR-201#1; OPS-104#1; FAC-402#2 |
| keyword | F006 | What's the most I can pay for a room when I stay in the capital? | HR-202#4 | OPS-102#1; SUP-502#3; FAC-401#4 |
| keyword | F011 | I've woken up ill. By when do I have to let my boss know? | HR-204#4 | HR-201#5; HR-201#6; HR-204#3 |
| keyword | F014 | Our depot can't dispatch anything because the warehouse system is down. How f... | OPS-101#4 | OPS-102#7; OPS-101#3; OPS-102#6 |
| keyword | F016 | After a critical outage is fixed, how long do we have to hold the lessons-lea... | OPS-101#7 | HR-204#6; SEC-302#4; OPS-101#3 |
| keyword | F024 | I think I left my work computer on the train. How long have I got to tell som... | OPS-105#4 | OPS-104#4; OPS-104#5; HR-202#6 |
| keyword | F026 | We turned down some job applicants. How long can we hold on to their CVs? | SEC-302#3 | SEC-302#4; OPS-103#1; HR-204#6 |
| keyword | F030 | How long do we take to settle a vendor's bill once it's approved? | SUP-501#5 | SUP-501#3; OPS-104#3; SUP-501#2 |
| keyword | F043 | I clicked a link in a phishing email at 21:00 on a Tuesday. Which number shou... | SEC-303#3, OPS-101#2 | SEC-303#3; SEC-303#2; SEC-303#1 |
| keyword | F045 | How long are IT incident tickets kept, and when must a P1 post-incident revie... | SEC-302#2, OPS-101#7 | OPS-101#7; FAC-401#5; OPS-101#4 |
| embedding | F043 | I clicked a link in a phishing email at 21:00 on a Tuesday. Which number shou... | SEC-303#3, OPS-101#2 | SEC-303#3; SEC-303#2; SEC-303#4 |
| embedding | F047 | What should a visiting haulier's driver do while their lorry is unloaded, and... | FAC-401#4, SUP-502#2 | SUP-502#3; SUP-502#2; SUP-502#5 |
| hybrid | F014 | Our depot can't dispatch anything because the warehouse system is down. How f... | OPS-101#4 | OPS-101#3; OPS-102#7; OPS-101#1 |
| hybrid | F024 | I think I left my work computer on the train. How long have I got to tell som... | OPS-105#4 | OPS-104#5; HR-204#6; HR-203#5 |
| hybrid | F045 | How long are IT incident tickets kept, and when must a P1 post-incident revie... | SEC-302#2, OPS-101#7 | OPS-101#7; OPS-101#4; OPS-101#5 |
