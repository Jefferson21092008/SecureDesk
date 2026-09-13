# SecureDesk — V0.4 Security Review

This document records the final security review for the V0.4 milestone. It is a focused application-security review of the current API, not a claim that the system is free of vulnerabilities.

## Scope

Reviewed attack surfaces:

- authentication and JWT validation;
- authorization, IDOR and role boundaries;
- input validation and mass assignment;
- login abuse and rate limiting;
- ticket search and ORM query construction;
- attachment upload, download and filesystem paths;
- security audit data handling;
- production configuration safeguards;
- HTTP response hardening.

The regression suite is implemented in `tests/test_vulnerability_analysis.py` and complements the authorization, JWT, rate-limit, audit and hardening suites added earlier in V0.4.

## Findings closed in V0.4.6

### Login resource-exhaustion guard

Registration already caps passwords at 128 characters, but the OAuth2 login form previously accepted arbitrarily long credentials before password verification. Because Argon2 is intentionally expensive, attacker-controlled oversized passwords should not reach the password hasher.

V0.4.6 rejects oversized login identifiers/passwords with the same generic `401 Invalid credentials` response used for other failed logins.

### Account-enumeration timing reduction

A nonexistent account previously skipped password verification while an existing account performed Argon2 verification. The response body was already generic, but the computational difference could create a timing side channel.

V0.4.6 verifies nonexistent accounts against a process-local dummy password hash before returning the same generic failure response. This reduces, but does not mathematically eliminate, network timing differences.

### Attachment path traversal defense in depth

Uploaded files already receive server-generated random storage keys and user filenames are reduced to their basename. V0.4.6 additionally validates every stored key before resolving it and refuses any path that escapes the configured attachment root. This protects downloads and cleanup even if a storage key is unexpectedly corrupted or tampered with in the database.

### Attachment content spoofing

Extension and declared MIME type checks alone do not prove that the uploaded bytes match the claimed type. V0.4.6 checks lightweight signatures for PDF, PNG and JPEG files and requires UTF-8, NUL-free content for `text/plain` uploads.

This is format validation, not malware scanning.

### Security response headers

API responses now include:

- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`.

Authentication and security-audit responses also receive `Cache-Control: no-store`.

## Regression coverage

The final vulnerability suite verifies that:

- unsigned (`alg=none`) JWTs are rejected;
- alternate JWT algorithms are rejected;
- malformed JWT subjects are rejected;
- oversized login credentials do not reach password verification;
- nonexistent accounts still execute a dummy password-verification path;
- known and unknown accounts return the same invalid-credential response;
- SQL-injection-shaped search input does not escape ticket ownership scope;
- spoofed attachment content is rejected;
- tampered attachment storage keys cannot read files outside the upload root;
- security headers are present;
- auth responses are marked `no-store`;
- audit records do not persist raw passwords or bearer tokens.

Earlier V0.4 suites also cover IDOR, nested resource access, mass assignment, role escalation attempts, token expiry/revocation, audience/type validation, brute-force throttling, `Retry-After`, spoofed `X-Forwarded-For`, and admin-only security audit access.

## Query safety

Ticket search and filters are built with SQLAlchemy expressions rather than string-concatenated SQL. User search text is passed as a bound expression, and owner scoping is applied independently before pagination and ordering. The regression suite uses SQL-injection-shaped input to verify that it does not bypass the current user's ticket scope.

## Residual risks / accepted limitations

These items are intentionally documented instead of hidden:

1. **Rate limiting is process-local.** The in-memory limiter is appropriate for the current single-process portfolio deployment, but multiple workers/replicas require a shared backend such as Redis.
2. **Attachments use local filesystem storage.** Production should use durable object storage, private buckets, malware scanning, content-disposition controls and operational cleanup/reconciliation.
3. **No malware scanner is present.** Signature validation only checks basic file-type consistency.
4. **Registration reveals duplicate email addresses with `409`.** Login does not reveal account existence, but registration enumeration remains an explicit product/security tradeoff.
5. **No MFA or refresh-token flow exists.** Access tokens are short-lived and individually revocable, but higher-assurance deployments may require MFA and a dedicated refresh-token lifecycle.
6. **Audit logs are database records, not tamper-evident logs.** Production security monitoring should forward them to append-only/centralized logging with retention and alerting.
7. **Secrets come from environment configuration.** Production should inject them through a managed secret store rather than relying on a local `.env` file.
8. **TLS is expected at the deployment/proxy layer.** HSTS is not forced by the application because the current local Docker environment is plain HTTP.
9. **Dependency/SAST scanning is not yet a blocking CI gate.** This should be added during V1.0 deployment/CI hardening.

## V0.4 conclusion

V0.4 closes with defense in depth across authorization, token lifecycle, abuse protection, auditability, strict input handling, password/secrets policy and targeted vulnerability regression tests. The remaining documented risks are deployment or operational concerns rather than silent assumptions.
