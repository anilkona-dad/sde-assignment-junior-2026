# Assignment A - Interaction Ledger & Reporting Pipeline

## Candidate

- **Name:** Kona Meghana
- **Assignment chosen:** A (Data)
- **Time spent (honest estimate):** 7h

## 1. How to run

### Requirements

- Python 3.11+
- Windows CMD or a compatible terminal
- Git

### 1.1 Environment setup

From the repository root:

```cmd
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 1.2 Configure security keys

The application requires two environment variables:

- `PII_ENCRYPTION_KEY`: a 32-byte AES key represented as 64 hexadecimal characters.
- `PHONE_HMAC_KEY`: a secret used for keyed HMAC-based phone identity.

Generate separate random values:

```cmd
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the first generated value into:

```cmd
set PII_ENCRYPTION_KEY=PASTE_FIRST_GENERATED_VALUE_HERE
```

Copy the second generated value into:

```cmd
set PHONE_HMAC_KEY=PASTE_SECOND_GENERATED_VALUE_HERE
```

Keep both values private. Do not commit them to Git. Use the same values whenever you need to access data encrypted or identified using those keys. Changing them without a planned key migration can make existing protected data inaccessible.

### 1.3 Generate the sample dataset

```cmd
python assignment-a-data\tools\generate_data.py --seed 42 --scale small --out data
```

This generates the two input drops under `data/`.

### 1.4 Process both drops

```cmd
set PYTHONPATH=solution
python -c "from ingestion.pipeline import ingest_drop; print(ingest_drop('data/drop_1'))"
python -c "from ingestion.pipeline import ingest_drop; print(ingest_drop('data/drop_2'))"
```

The pipeline initializes the SQLite database when required and processes each drop transactionally.

### 1.5 Generate reports

```cmd
python -c "from reporting import generate_reports; print(generate_reports())"
```

The five generated reports are written to the `reports/` directory:

- `batch_summary.csv`
- `daily_overview.csv`
- `lead_report.csv`
- `rejections.csv`
- `data_quality.json`

### 1.6 Run tests and compilation checks

```cmd
python -m pytest -v
python -m compileall -q solution
```

### 1.7 Verify idempotency

Run the two ingestion commands from section 1.4 again. Previously processed drops should be skipped rather than ingested again.

---

## 2. Design and architecture

The implementation is organized into three main areas:

- **Core:** normalization, validation, and security utilities.
- **Ingestion:** lead ingestion, event ingestion, and drop-level orchestration.
- **Reporting:** generation of CSV and JSON reports from the stored records.

SQLite is used as the persistent store. The ingestion pipeline processes lead records before interaction events so that events can be linked to known leads when possible.

The pipeline maintains ingestion metadata and event-linking information to support incremental processing, duplicate detection, reporting, and later resolution of orphan events.

### Main database entities

The database includes the following tables:

- `leads` - normalized lead records and protected personal information.
- `batches` - batch-level processing information.
- `ingestion_drops` - records of processed input drops.
- `interaction_events` - stored interaction events.
- `seen_event_ids` - event identifiers used for duplicate detection.
- `event_lead_links` - links between interaction events and leads.
- `rejections` - rejected input records and associated reasons.
- `drop_metrics` - ingestion metrics for individual drops.

### Data protection

- AES-GCM is used to encrypt protected lead data.
- Keyed HMAC-SHA256 is used for phone identity matching without relying on plaintext phone numbers as identity keys.
- Security keys are supplied through environment variables rather than hardcoded in source files.

---

## 3. Implementation decisions

| Area | Decision |
|---|---|
| Persistence | SQLite for local, transactional storage |
| Ingestion order | Process leads before events in each drop |
| Duplicate leads | Merge valid duplicate lead rows instead of creating separate lead identities |
| Duplicate events | Track event IDs and prevent repeated insertion |
| Event linking | Link events to leads when a matching lead is available |
| Orphan events | Retain unresolved events so they can be linked when matching lead information becomes available |
| Timestamp handling | Use India's fixed UTC+05:30 offset for the supported local-time handling |
| Security | AES-GCM encryption and keyed HMAC-SHA256 phone identity |
| Reprocessing | Track processed drops and skip previously completed drops |

The implementation also distinguishes between rejected records and accepted records containing optional-field warnings. Optional values are handled separately from required-field validation so that defaults can be applied at the appropriate stage.

---

## 4. Verification and observed results

The small dataset was generated with seed `42` and processed through both drops.

### Lead ingestion

| Metric | Observed result |
|---|---:|
| Total lead rows | 2,057 |
| Rejected lead rows | 108 |
| Duplicate lead rows merged | 57 |
| Unique leads after merging | 1,892 |
| Field warnings | 122 |

### Event ingestion

| Metric | Observed result |
|---|---:|
| Total event lines | 8,745 |
| Malformed events | 8 |
| Duplicate events dropped | 237 |
| Unknown-disposition events | 19 |
| Events stored | 8,481 |
| Linked stored events | 8,020 |
| Unresolved orphan events after both drops | 461 |

### Report generation

All five reports were generated successfully:

- `batch_summary.csv`
- `daily_overview.csv`
- `lead_report.csv`
- `rejections.csv`
- `data_quality.json`

The observed report-generation output contained:

- 1,892 leads
- 33 daily overview rows
- 108 rejection records
- 461 unresolved orphan events

### Test results

Executed:

```cmd
python -m pytest -v
```

**Result: 44 tests passed.**

Also executed:

```cmd
python -m compileall -q solution
```

Compilation completed without errors.

The same input drops were processed again to verify idempotency. Previously processed drops were skipped without duplicate ingestion.

---

## 5. Failure handling and limitations

The implementation handles several data-quality and ingestion cases:

- Invalid required fields are rejected.
- Optional-field issues are recorded as warnings where applicable.
- Malformed events are excluded from normal event ingestion.
- Duplicate event identifiers are detected and prevented from being inserted again.
- Events without a matching lead remain available for later linking.
- Drop-level transactions help prevent partially committed ingestion.

Current limitations and areas for improvement:

- SQLite is intended for this local assignment implementation; a production deployment with concurrent workloads may require a server database such as PostgreSQL.
- Encryption-key rotation and centralized key management are not implemented.
- Large-scale performance benchmarking has not been conducted.
- Production-grade monitoring, alerting, and schema migration management are not included.
- Additional crash-recovery and integration testing would strengthen operational confidence.

## 6. Future improvements

Potential next steps include:

- Benchmarking ingestion and reporting against larger datasets.
- Adding more integration and failure-recovery tests.
- Introducing a command-line interface for ingestion and report generation.
- Integrating managed key storage and key rotation.
- Adding database migrations and structured operational logging.
- Evaluating PostgreSQL for larger or concurrent workloads.
