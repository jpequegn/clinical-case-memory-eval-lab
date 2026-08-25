# Security And Privacy

The default and supported demo path uses fictional generated data only. The API requires a caller to
attest that a case is synthetic or redacted. This declaration is recorded in the audit chain, but it
does not itself perform de-identification.

Do not use this repository with protected health information without an independent privacy,
security, legal, and clinical review. The local server has no authentication, authorization, TLS,
rate limiting, or multi-tenant isolation. Bind it to `127.0.0.1`; do not expose it to a network.

No API keys are required or read by the deterministic path. External judge adapters should obtain
credentials from their deployment environment, avoid logging source text, and retain the local
schema and citation checks. Treat DuckDB files and generated evidence packets as sensitive if real
or redacted material is ever introduced.

Results are evaluation signals, not medical advice, medical-device output, or certification.
