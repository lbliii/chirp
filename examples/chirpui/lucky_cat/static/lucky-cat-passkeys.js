/* Lucky Cat passkey UI — document-delegated register/login handlers.

   Inline <script> blocks inside #page-content carry a per-request CSP nonce.
   Under hx-boost the browser keeps the *first* page's Content-Security-Policy
   header, so a boosted navigation that swaps in a fresh inline script (new nonce)
   is blocked before the click handler runs. An external 'self' script is allowed
   by script-src without a nonce and survives boosted shell swaps — same pattern
   as lucky-cat-shell.js / coachmarks.js. */
(function () {
  "use strict";

  function csrfToken() {
    return (
      document.querySelector('meta[name="csrf-token"]')?.content ||
      document.querySelector('input[name="_csrf_token"]')?.value
    );
  }

  function passkeysReady() {
    return !!(window.chirp && window.chirp.passkeys);
  }

  function syncPasskeyButtons() {
    var loginBtn = document.getElementById("passkey-login");
    var registerBtn = document.getElementById("passkey-register");
    if (loginBtn) loginBtn.hidden = !passkeysReady();
    if (registerBtn) registerBtn.hidden = !passkeysReady();
  }

  async function loginWithPasskey() {
    var err = document.getElementById("passkey-login-error");
    if (!err) return;
    err.hidden = true;
    var csrf = csrfToken();
    var nextInput = document.querySelector('#login-form input[name="next"]');
    var nextUrl = (nextInput && nextInput.value) || "/";
    try {
      var begin = await fetch("/auth/passkey/login/begin", {
        method: "POST",
        headers: csrf ? { "X-CSRF-Token": csrf } : {},
      });
      if (!begin.ok) throw new Error("Could not start passkey sign-in.");
      var opts = await begin.json();
      var credential = await window.chirp.passkeys.authenticate(opts);
      var finish = await fetch("/auth/passkey/login/finish", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        },
        body: JSON.stringify(Object.assign({}, credential, { next: nextUrl })),
      });
      var result = await finish.json();
      if (!finish.ok || !result.ok) {
        throw new Error(result.error || "Passkey sign-in failed.");
      }
      window.location = result.redirect || nextUrl;
    } catch (e) {
      if (e && e.passkeyReason === "cancelled") return;
      err.textContent = (e && e.message) || "Passkey sign-in failed.";
      err.hidden = false;
    }
  }

  async function registerPasskey() {
    var err = document.getElementById("passkey-register-error");
    if (!err) return;
    err.hidden = true;
    var csrf = csrfToken();
    try {
      var begin = await fetch("/auth/passkey/register/begin", {
        method: "POST",
        headers: csrf ? { "X-CSRF-Token": csrf } : {},
      });
      if (!begin.ok) throw new Error("Could not start passkey enrollment.");
      var opts = await begin.json();
      var credential = await window.chirp.passkeys.register(opts);
      var finish = await fetch("/auth/passkey/register/finish", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        },
        body: JSON.stringify(credential),
      });
      var result = await finish.json();
      if (!finish.ok || !result.ok) {
        throw new Error(result.error || "Enrollment failed.");
      }
      window.location = result.redirect || "/settings/security";
    } catch (e) {
      if (e && e.passkeyReason === "cancelled") return;
      err.textContent = (e && e.message) || "Enrollment failed.";
      err.hidden = false;
    }
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || typeof target.closest !== "function") return;
    if (!passkeysReady()) return;
    if (target.closest("#passkey-login")) {
      event.preventDefault();
      loginWithPasskey();
      return;
    }
    if (target.closest("#passkey-register")) {
      event.preventDefault();
      registerPasskey();
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncPasskeyButtons);
  } else {
    syncPasskeyButtons();
  }
  document.addEventListener("htmx:afterSettle", syncPasskeyButtons);
})();
