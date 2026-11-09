Perform only the retention component below. Read memory through fixture-read_input. Submit the raw record retention limit, whether to compact the index for this input, and whether to keep the protected current record through fixture-publish_result. A restricted executor applies the decision to the frozen working copy. Other phases are outside this comparison.

5. **Retention & Compaction (MANDATORY — keeps the knowledge base under the repo-memory caps)**:

   The repo-memory branch enforces hard `max-file-count` (1000) and `max-file-size` (1 MiB) caps on every push; once either is exceeded, **the entire push is rejected** and this run's investigation — and all future ones — silently fail to persist. To stay under them, prune the two unbounded, low-value-over-time datasets down to rolling windows **after** writing this run's artefacts (steps 1–3). No permanent signal is lost: long-term recurrence lives in the per-signature `patterns/*.json` `count`/`first_seen`/`last_seen` fields, which are **never** pruned.

   Constants:
   - `INVESTIGATION_RETENTION_MAX = 300` — max per-run investigation record files to keep under `investigations/`.
   - `INDEX_RETENTION_MAX = 2000` — max entries to keep in `index.json` (≈600 KiB, comfortably under the 1 MiB file cap).

   **Step A — Prune raw investigation records:**
   - List every `*.json` file under `/tmp/gh-aw/repo-memory/default/${{ github.aw.import-inputs.slug }}/investigations/` **except** `index.json`.
   - If the count exceeds `INVESTIGATION_RETENTION_MAX`, delete the oldest files (order by the `YYYY-MM-DD-HH-MM-SS-sss` timestamp in the filename, oldest first) until exactly `INVESTIGATION_RETENTION_MAX` remain. **Never** delete the record you wrote in this run.
   - Deleting a raw record does not erase the failure from history: its lightweight reference stays in `index.json` (until the index prune below) and its recurrence is already folded into the pattern record.

   **Step B — Compact the index to its rolling window:**
   - Re-read `index.json` (the superset written in step 1a).
   - If `length(entries) > INDEX_RETENTION_MAX`, keep only the newest `INDEX_RETENTION_MAX` entries (sort by `timestamp` descending, take the first `INDEX_RETENTION_MAX`). This is the ONLY sanctioned place the index shrinks.
   - Set `total = length(entries)`, write the object back, then validate against `index.schema.json` and confirm this run's `investigation_id` is still present (it is one of the newest, so it must survive the trim).

   **Step C — Verify headroom (monitoring):**
   - Count all persisted files under `/tmp/gh-aw/repo-memory/default/${{ github.aw.import-inputs.slug }}/` and confirm the total is `< max-file-count` (1000).
   - Confirm `index.json` on disk is `< max-file-size` (1 MiB). If it is within ~10% of the cap despite the entry trim, lower the effective `INDEX_RETENTION_MAX` for this write and note it in the investigation.
   - Never leave the branch over any cap — an over-cap push is rejected wholesale and this run's investigation is lost. If pattern records alone approach `max-file-count`, flag it in the Teams report so a maintainer can raise the cap or archive old signatures.
