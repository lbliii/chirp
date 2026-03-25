# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Chirp, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email: **lbeezr@icloud.com**

You will receive an acknowledgment within 48 hours and a detailed response within 5 business days.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| < 0.2   | No        |

## Security Features

Chirp includes built-in security features:

- **CSRF protection** via `CSRFMiddleware` (enabled by default with sessions)
- **Security headers** via `SecurityHeadersMiddleware` (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, CSP)
- **Allowed hosts validation** via `AllowedHostsMiddleware`
- **HSTS** auto-enabled in production with TLS
- **CSP nonces** for inline script protection
- **Signed cookie sessions** via `itsdangerous`
- **Security audit** via `chirp security-check`

## Best Practices

1. Always set a strong `secret_key` in production
2. Configure `allowed_hosts` explicitly (do not use `"*"`)
3. Enable HSTS when serving over TLS
4. Use `chirp security-check` in your CI pipeline
