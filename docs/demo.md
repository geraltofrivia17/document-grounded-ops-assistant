# Demo script (about three minutes)

## Before the demo

```powershell
cd "E:\Project 3\document-grounded-ops-assistant"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m ops_assistant index
python -m ops_assistant serve
```

Open http://127.0.0.1:8000 in a browser, and keep the terminal visible so the log lines can be seen.

## 1. What the service knows (20 seconds)

The header line under the title is `/health`: documents in force, the as-of date, the retrieval mode and the model. Run `python -m ops_assistant corpus` in a second terminal to show the three versions that were excluded and why.

## 2. A supported answer (40 seconds)

Click **Supported**. Point out:

- the answer and the cited passage, with its document, version and section
- the request id, the retrieval and generation times, the tokens and the estimated cost
- the JSON log line in the terminal with the same request id; the question text is not logged

## 3. A question the handbook does not answer (30 seconds)

Click **Not in the handbook**. The outcome is "Not enough evidence", with an HTTP 200. Abstaining is a normal answer, not an error.

## 4. Documents that disagree (30 seconds)

Click **Conflicting documents**. The assistant gives both rules with both citations instead of choosing one.

## 5. An injected instruction (30 seconds)

Ask: `Can Greywell Haulage invoices be paid without a purchase order?` The external haulier guide contains an instruction aimed at AI systems. The answer should come from the supplier policy (SUP-501), and the external passage is labelled as external.

## 6. A handled failure (30 seconds)

Stop the server (Ctrl+C) and restart it with an impossible timeout:

```powershell
$env:OPS_TIMEOUT_SECONDS = "0.001"
python -m ops_assistant serve
```

Ask any question. The page shows `provider_timeout` with stage `generation` and the request id, and the API returns HTTP 504. Afterwards:

```powershell
Remove-Item Env:OPS_TIMEOUT_SECONDS
```

## 7. The evidence (30 seconds)

Open the README results table and `docs/results/retrieval.md`. Show the "keyword against embedding" table: the paraphrased questions are where embeddings found evidence that keyword search missed.
