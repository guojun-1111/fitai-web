# Security Policy

## Reporting a Vulnerability

**Do not open a public issue.** Email the maintainer directly.

We take the security of health data seriously. FitAI-Web processes
personally identifiable health information (heart rate, sleep patterns,
body metrics) and implements multiple defensive layers.

## Security Architecture

- **Authentication**: scrypt password hashing (N=16384, r=8, p=1), stateless JWT tokens, 24h expiry
- **Transport**: TLS 1.2+ enforced via Nginx reverse proxy (production)
- **Middleware**: CSP headers, HSTS, X-Content-Type-Options, X-Frame-Options
- **Input validation**: Prompt injection filtering on LLM inputs, file upload type/magic-byte checks
- **WebSocket**: JWT authentication before connection accept, per-connection rate limiting
- **Error handling**: PII redaction in logs, sanitized error messages (no stack traces to client)
- **Data**: Multi-tenant isolation via `user_id` on all DB queries, WAL mode for concurrent reads

## Privacy by Design

- All health data processing happens locally on your server
- No third-party analytics, telemetry, or crash reporters
- No data ever sent to external services without explicit user opt-in (e.g., LLM API)
- Full data export via API
- Hard account deletion (all data removed from DB + filesystem)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x.x   | Yes |

## Acknowledgments

We appreciate responsible disclosure. Critical vulnerabilities will be
acknowledged in release notes (with reporter's permission).
