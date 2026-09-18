# Evals

Phase 1 delivers the harness v1 (promptfoo-style, plain Python): each eval set is a directory
with `cases.jsonl`, a grader, and a `README.md`. `make evals` runs them and writes a report.
`evals/model_selection.md` is written after Phase 1 from harness results; the harness decides
model assignments, not `config/models.yaml`.

Planned sets: `extraction/` (precision on the labelled entity set), `explain/` (citation
correctness), `synthesis/` (verb accuracy), `adversarial/` (verifier rejection rate),
`pii/` (recogniser recall), `immune/` (injection success rate with benign controls).
