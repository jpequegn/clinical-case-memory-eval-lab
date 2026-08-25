# Project Guide

## What It Can Do

The lab turns a generated note and its source transcript into a reason-coded, evidence-cited verdict.
It measures failures by class and severity, calibrates confidence, retrieves only human-approved
training precedents, records review decisions, and reproduces historical runs against frozen inputs.

## Typical Usage Pattern

1. Maintain a versioned synthetic or properly governed redacted golden set.
2. Run a candidate judge or prompt in `judge_only` mode.
3. Review disputed or severe findings in the browser.
4. Promote only accepted cases into reviewed memory.
5. Run `retrieval_grounded`, compare it with the baseline, and inspect precedent-removal ablations.
6. Gate releases on severe recall, per-class F1, calibration, and provenance stability.
7. Archive the run manifest and evidence packet with the software release.

## Potential Extensions

- Implement an external structured judge adapter and compare providers under the same contract.
- Replace feature hashing with a governed clinical embedding while retaining snapshot identities.
- Add reviewer cohorts, blinded adjudication, and inter-rater agreement beyond exact-match agreement.
- Expand mutation testing for temporality, dosage, negation scope, and cross-note contradictions.
- Export spans to an OpenTelemetry collector and regression reports to CI annotations.
- Add authenticated multi-user review and object storage only after a security design review.

## Innovative Uses

- Treat accepted review cases as executable safety precedents for prompt and model upgrades.
- Detect institutional documentation-policy drift by replaying old cases against a new policy version.
- Use ablation to identify single precedents that disproportionately control a verdict.
- Build a curriculum from recurring disagreement clusters for reviewer training.
- Generate counterfactual note pairs that differ by one safety-critical fact and test causal sensitivity.

None of these extensions converts benchmark performance into clinical validation or certification.
