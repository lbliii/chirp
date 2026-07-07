# Declarative WebMCP form

This example adds experimental WebMCP discovery attributes to one real Chirp
form. `TaskForm` remains the typed server contract, `/tasks` remains the only
submission handler, and `FormAction`/`ValidationError` preserve normal and htmx
behavior. The mutation uses the same session-backed CSRF protection for human,
htmx, and browser-agent submissions. There is no imperative browser-tool
registry or JSON response path.

Run it from the repository root:

```bash
PYTHONPATH=src python examples/standalone/webmcp_form/app.py
```

Open `http://127.0.0.1:8000/`. A browser without WebMCP sees and submits the
ordinary form. A compatible browser can discover `tasks.create`, populate the
same controls, and then leaves the mutation for human confirmation because the
form does not emit `toolautosubmit`. The server still enforces session-backed
CSRF and repeats the advertised title/priority constraints; browser validation
is never the authority.

This is an experimental preview, pinned to WebMCP proposal commit
`0b676d27a08aafd3b4f8a709756eeeab342fd9bd`. Chrome documents its origin trial
from Chrome 149 and the local `chrome://flags/#enable-webmcp-testing` switch.
The automated lane pins Playwright 1.61.0 / Chrome for Testing 149.0.7827.55
and deliberately verifies the flag-off and `Permissions-Policy: tools=()`
fallbacks. Chrome's docs say WebMCP needs a visible browsing context, so the
repository does not claim headless agent invocation coverage.

Do not ship a reusable origin-trial token with an application or library. A
production trial token is registered to the application's own origin. Whether
WebMCP is available, unavailable, or policy-disabled, users retain the same
ordinary form and the same HTTP/htmx handler.

Run its offline proof with:

```bash
pytest examples/standalone/webmcp_form/
```
