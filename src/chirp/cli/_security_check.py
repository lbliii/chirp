"""Security audit CLI command — validates config against OWASP checklist.

``chirp security-check app:app`` exits 1 on failure (CI-friendly).
"""

import sys

from chirp.cli._resolve import resolve_app


def run_security_check(args) -> None:
    """Run security audit against the app's configuration."""
    app = resolve_app(args.app)
    config = app.config
    passed = 0
    failed = 0

    def check(ok: bool, pass_msg: str, fail_msg: str) -> None:
        nonlocal passed, failed
        if ok:
            print(f"  \u2713 {pass_msg}")
            passed += 1
        else:
            print(f"  \u2717 {fail_msg}")
            failed += 1

    print("Chirp Security Check")
    print("=" * 40)

    # 1. Secret key
    check(
        bool(config.secret_key),
        "secret_key is set",
        "secret_key is empty \u2014 sessions and CSRF will not work",
    )

    # 2. ALLOWED_HOSTS
    allowed = getattr(config, "allowed_hosts", ("*",))
    check(
        "*" not in allowed,
        f"allowed_hosts configured ({', '.join(allowed)})",
        'allowed_hosts is "*" \u2014 all hosts accepted',
    )

    # 3. Debug mode in production
    check(
        not (config.env == "production" and config.debug),
        "debug is off in production",
        "debug=True in production \u2014 never deploy with debug enabled",
    )

    # 4. HSTS
    has_hsts = bool(getattr(config, "strict_transport_security", None))
    has_ssl = bool(config.ssl_certfile)
    check(
        has_hsts or not (config.env == "production" and has_ssl),
        "HSTS configured or not applicable",
        "HSTS not enabled \u2014 set strict_transport_security for HTTPS production",
    )

    # 5. CSP nonces
    csp_nonce = getattr(config, "csp_nonce_enabled", False)
    check(
        csp_nonce,
        "CSP nonce enabled",
        "CSP nonce not enabled \u2014 inline scripts won't have nonces",
    )

    print()
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed > 0 else 0)
