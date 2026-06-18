"""Passkey JS bridge injection — the vendored ``window.chirp.passkeys`` runtime.

Mirrors the Alpine/htmx/islands injection path
(``src/chirp/server/{alpine,htmx,islands}.py``). When ``AppConfig(passkeys=True)``
Chirp injects this inline ``<script>`` before ``</body>`` via
:class:`~chirp.middleware.inject.HTMLInject`, marked ``data-chirp="passkeys"``
and carrying the live per-request CSP nonce.

Unlike Alpine/htmx, **nothing external is loaded** — the bridge is a pure
``base64url`` + ``navigator.credentials`` shim, so there is no CDN footgun
(``AGENTS.md`` jsDelivr rule) to get wrong and no npm/Node toolchain. It absorbs
the part of WebAuthn every DIY integration fumbles: base64url↔ArrayBuffer
marshalling of the challenge / user handle / credential ids / signatures, and
mapping ``DOMException`` names to clean states.

Browser API exposed (SimpleWebAuthn-parity — one call, options in, POSTable JSON
out; the app does the ``fetch`` so it controls the URL **and includes the CSRF
token**, since the JS POST is not a template ``<form>`` the ``csrf_form`` rule
can validate)::

    const opts = await (await fetch('/auth/passkey/login/begin', {method:'POST'})).json();
    const credential = await chirp.passkeys.authenticate(opts);   // throws on cancel/misconfig
    await fetch('/auth/passkey/login/finish', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
      body: JSON.stringify(credential),
    });

Errors thrown carry a ``.passkeyReason`` of ``cancelled`` (user dismissed /
timeout), ``duplicate`` (authenticator already registered), ``misconfigured``
(bad rp_id/origin — also logged as a developer console error, the browser twin
of the ``passkeys`` startup contract), ``unsupported``, or ``failed``.
"""


def passkeys_snippet(version: str, *, nonce: str = "") -> str:
    """Return the inline ``window.chirp.passkeys`` bridge ``<script>``.

    When *nonce* is non-empty the ``<script>`` carries a ``nonce="..."``
    attribute so it survives a nonce-based CSP that no longer ships
    ``'unsafe-inline'``.

    Args:
        version: Bridge version, embedded as a ``VERSION`` constant / cache-bust
            marker (mirrors ``islands_version``).
        nonce: Per-request CSP nonce.

    Returns:
        An inline ``<script data-chirp="passkeys">`` tag. Self-contained — no
        external ``src``.
    """
    nonce_attr = f' nonce="{nonce}"' if nonce else ""
    return f"""<script data-chirp="passkeys"{nonce_attr}>
(function() {{
  if (window.chirp && window.chirp.passkeys) return;
  window.chirp = window.chirp || {{}};
  const VERSION = "{version}";

  function b64uToBuf(value) {{
    const pad = "=".repeat((4 - (value.length % 4)) % 4);
    const bin = atob((value + pad).replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }}
  function bufToB64u(buf) {{
    const bytes = new Uint8Array(buf);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
  }}

  function decodeCreation(options) {{
    const o = Object.assign({{}}, options);
    o.challenge = b64uToBuf(o.challenge);
    o.user = Object.assign({{}}, o.user, {{ id: b64uToBuf(o.user.id) }});
    if (Array.isArray(o.excludeCredentials)) {{
      o.excludeCredentials = o.excludeCredentials.map((c) =>
        Object.assign({{}}, c, {{ id: b64uToBuf(c.id) }}));
    }}
    return o;
  }}
  function decodeRequest(options) {{
    const o = Object.assign({{}}, options);
    o.challenge = b64uToBuf(o.challenge);
    if (Array.isArray(o.allowCredentials)) {{
      o.allowCredentials = o.allowCredentials.map((c) =>
        Object.assign({{}}, c, {{ id: b64uToBuf(c.id) }}));
    }}
    return o;
  }}

  function encodeRegistration(cred) {{
    const r = cred.response;
    return {{
      id: cred.id,
      rawId: bufToB64u(cred.rawId),
      type: cred.type,
      authenticatorAttachment: cred.authenticatorAttachment || undefined,
      clientExtensionResults: cred.getClientExtensionResults
        ? cred.getClientExtensionResults() : {{}},
      response: {{
        clientDataJSON: bufToB64u(r.clientDataJSON),
        attestationObject: bufToB64u(r.attestationObject),
        transports: r.getTransports ? r.getTransports() : [],
      }},
    }};
  }}
  function encodeAuthentication(cred) {{
    const r = cred.response;
    return {{
      id: cred.id,
      rawId: bufToB64u(cred.rawId),
      type: cred.type,
      authenticatorAttachment: cred.authenticatorAttachment || undefined,
      clientExtensionResults: cred.getClientExtensionResults
        ? cred.getClientExtensionResults() : {{}},
      response: {{
        clientDataJSON: bufToB64u(r.clientDataJSON),
        authenticatorData: bufToB64u(r.authenticatorData),
        signature: bufToB64u(r.signature),
        userHandle: r.userHandle ? bufToB64u(r.userHandle) : null,
      }},
    }};
  }}

  // Map a DOMException to a clean, app-actionable reason. SecurityError is a
  // developer misconfig (bad rp_id/origin) — log it loudly; a normal user
  // cancel/timeout (NotAllowedError) is a quiet clean state, not an error.
  function normalizeError(err) {{
    let reason = "failed";
    if (err && err.name === "NotAllowedError") reason = "cancelled";
    else if (err && err.name === "AbortError") reason = "cancelled";
    else if (err && err.name === "InvalidStateError") reason = "duplicate";
    else if (err && err.name === "SecurityError") {{
      reason = "misconfigured";
      console.error(
        "[chirp.passkeys] SecurityError — the page origin does not match the " +
        "server rp_id/origin (or the page is not a secure context). WebAuthn " +
        "is disabled until this is fixed.", err);
    }}
    const wrapped = new Error("passkey ceremony " + reason);
    wrapped.name = "PasskeyError";
    wrapped.passkeyReason = reason;
    wrapped.cause = err;
    return wrapped;
  }}

  function isSupported() {{
    return typeof window.PublicKeyCredential !== "undefined" &&
      !!(navigator.credentials && navigator.credentials.create);
  }}
  async function isConditionalSupported() {{
    try {{
      return isSupported() &&
        typeof PublicKeyCredential.isConditionalMediationAvailable === "function" &&
        (await PublicKeyCredential.isConditionalMediationAvailable());
    }} catch (e) {{ return false; }}
  }}

  async function register(optionsJSON) {{
    if (!isSupported()) {{
      const e = new Error("passkeys unsupported"); e.passkeyReason = "unsupported"; throw e;
    }}
    try {{
      const publicKey = (PublicKeyCredential.parseCreationOptionsFromJSON)
        ? PublicKeyCredential.parseCreationOptionsFromJSON(optionsJSON)
        : decodeCreation(optionsJSON);
      const cred = await navigator.credentials.create({{ publicKey }});
      return (cred.toJSON) ? cred.toJSON() : encodeRegistration(cred);
    }} catch (err) {{ throw normalizeError(err); }}
  }}

  async function authenticate(optionsJSON, opts) {{
    opts = opts || {{}};
    if (!isSupported()) {{
      const e = new Error("passkeys unsupported"); e.passkeyReason = "unsupported"; throw e;
    }}
    try {{
      const publicKey = (PublicKeyCredential.parseRequestOptionsFromJSON)
        ? PublicKeyCredential.parseRequestOptionsFromJSON(optionsJSON)
        : decodeRequest(optionsJSON);
      const request = {{ publicKey }};
      // Conditional UI / autofill. Full autocomplete + in-flight cancel-on-
      // password wiring is the scaffold's job (5c); the bridge just plumbs the
      // mediation mode and an optional AbortSignal.
      if (opts.conditional) request.mediation = "conditional";
      if (opts.signal) request.signal = opts.signal;
      const cred = await navigator.credentials.get(request);
      return (cred.toJSON) ? cred.toJSON() : encodeAuthentication(cred);
    }} catch (err) {{ throw normalizeError(err); }}
  }}

  window.chirp.passkeys = {{
    version: VERSION,
    register: register,
    authenticate: authenticate,
    isSupported: isSupported,
    isConditionalSupported: isConditionalSupported,
  }};
}})();
</script>"""
