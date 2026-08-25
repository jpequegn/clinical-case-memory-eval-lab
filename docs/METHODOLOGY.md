# Evaluation Methodology

The golden set has four scenario families and four independently measured failure modes: omission,
unsupported inference, plan reversal, and unsafe certainty. Each failure includes exact transcript
and note spans plus severity and reviewer rationale. Clean controls prevent a detector from earning
recall by flagging every case.

The baseline is conservative and deterministic. Retrieval may add reviewed context, but only
promoted training cases can influence a validation or holdout query. The query case is always
excluded. Reports retain TP, FP, FN, and TN counts for each class alongside precision, recall, F1,
severe-failure recall, exact reviewer agreement, abstention rate, and expected calibration error.

Regression policy gives severe recall its own hard gate. Aggregate improvement cannot hide a severe
recall decline. A newly introduced failure mode requires explicit human approval. Precedent-removal
ablation measures whether retrieval changed the evidence context.

These synthetic fixtures demonstrate evaluation mechanics; they do not establish clinical validity,
population coverage, robustness to real documentation, or readiness for patient care.
