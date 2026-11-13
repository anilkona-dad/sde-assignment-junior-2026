# AI Usage Disclosure

## Tools used

- ChatGPT

## What I used them for

I used ChatGPT as a development assistant throughout Assignment A.

Specifically, I used it for:

- Understanding the assignment requirements and breaking them into implementation steps.
- Discussing the ingestion architecture and SQLite database design.
- Developing and refining Python code for lead ingestion, event ingestion, validation, normalization, and reporting.
- Understanding AES-GCM encryption and keyed HMAC-based phone identity.
- Developing test cases for normalization, validation, and reporting logic.
- Debugging Python errors and Windows CMD commands.
- Reviewing report calculations and checking the consistency of generated metrics.
- Preparing the submission documentation.

AI assistance included code generation and refinement. I did not treat generated code as automatically correct.

## What I wrote or decided myself

I made implementation decisions and worked through the code and its behavior step by step.

My contributions included:

- Selecting Assignment A and following its data-processing requirements.
- Running the dataset generator and inspecting the generated input files.
- Executing the ingestion pipeline against both drops.
- Reviewing normalization, validation, merging, and event-linking behavior.
- Checking the database contents and generated report outputs.
- Running the test suite and investigating failures.
- Verifying idempotency by processing the same drops again.
- Checking report totals against ingestion metrics.
- Reviewing the security configuration and ensuring secrets were not hardcoded.

I used AI explanations and suggestions to support implementation, but I was responsible for running the code, evaluating its output, and deciding whether the behavior matched the assignment requirements.

## Where the AI was wrong or unhelpful

There were cases where AI-generated suggestions or verification logic needed correction.

1. **Timezone handling:** An approach using `ZoneInfo("Asia/Kolkata")` was unsuitable for the current Windows environment because the timezone database was unavailable. I investigated the issue and used India's fixed UTC+05:30 offset, which is appropriate because India does not observe daylight-saving changes.

2. **Phone masking verification:** An initial verification check expected the masked phone number to have a length of 14 characters. Comparing it with the required `+91******last4` format showed that the correct length is 13. I corrected the verification check rather than changing the implementation to satisfy an incorrect expectation.

These examples reinforced the need to compare AI suggestions with the assignment specification and actual program behavior.

## How I verified AI-generated code

I verified the implementation through multiple methods:

- Ran the Python test suite and checked the individual test results.
- Executed `python -m pytest -v` from the repository root: **44 tests passed**.
- Ran `python -m compileall -q solution` to check Python compilation.
- Generated the provided small synthetic dataset and processed both drops.
- Inspected database records and ingestion metrics.
- Checked that duplicate lead rows were merged and duplicate event IDs were not inserted again.
- Verified that orphan events could be resolved when later lead records became available.
- Generated all five reports and reconciled their totals with the underlying database and ingestion metrics.
- Re-ran the same drops and confirmed that they were skipped without changing the existing results.

I also reviewed the implementation and its outputs rather than relying only on successful test execution.