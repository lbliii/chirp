"""HTMX debug overlay for development mode.

Intercepts htmx client-side error events and presents them as rich,
developer-friendly console messages and a small in-page toast —
replacing the opaque ``htmx:targetError`` one-liners from the minified
htmx bundle.

Auto-injected when ``debug=True`` via :class:`~chirp.middleware.inject.HTMLInject`.
"""

HTMX_DEBUG_SCRIPT = """\
<script data-chirp-debug="htmx">
(function() {
  /* ── bail if htmx isn't loaded yet ────────────────────────── */
  if (typeof htmx === 'undefined') return;

  /* ── console styling ──────────────────────────────────────── */
  var ERR  = 'background:#f7768e;color:#1a1b26;padding:2px 8px;border-radius:3px;font-weight:bold';
  var WARN = 'background:#e0af68;color:#1a1b26;padding:2px 8px;border-radius:3px;font-weight:bold';
  var LBL  = 'color:#7aa2f7;font-weight:bold';
  var VAL  = 'color:#a9b1d6';
  var DIM  = 'color:#565f89';

  /* ── helpers ───────────────────────────────────────────────── */
  function desc(el) {
    if (!el || !el.tagName) return '(unknown element)';
    var s = '<' + el.tagName.toLowerCase();
    if (el.id) s += ' id="' + el.id + '"';
    if (el.className && typeof el.className === 'string')
      s += ' class="' + el.className.split(/\\s+/).join(' ') + '"';
    s += '>';
    var text = (el.textContent || '').trim();
    if (text.length > 40) text = text.substring(0, 37) + '...';
    if (text) s += ' "' + text + '"';
    return s;
  }

  function hxAttrs(el) {
    if (!el || !el.attributes) return {};
    var out = {};
    for (var i = 0; i < el.attributes.length; i++) {
      var a = el.attributes[i];
      if (a.name.indexOf('hx-') === 0) out[a.name] = a.value;
    }
    return out;
  }

  /* ── toast container ──────────────────────────────────────── */
  var toastBox = document.createElement('div');
  toastBox.id = 'chirp-htmx-debug-toasts';
  toastBox.setAttribute('style',
    'position:fixed;bottom:16px;right:16px;z-index:99999;' +
    'display:flex;flex-direction:column-reverse;gap:8px;' +
    'max-height:60vh;overflow-y:auto;pointer-events:none;' +
    'font-family:ui-monospace,"Cascadia Code","Source Code Pro",Menlo,Consolas,monospace;'
  );
  document.body.appendChild(toastBox);

  function toast(title, body, color) {
    var el = document.createElement('div');
    el.setAttribute('style',
      'pointer-events:auto;background:#1a1b26;color:#a9b1d6;' +
      'border:1px solid ' + color + ';border-left:4px solid ' + color + ';' +
      'border-radius:6px;padding:10px 14px;max-width:420px;' +
      'font-size:13px;line-height:1.5;box-shadow:0 4px 24px rgba(0,0,0,.5);' +
      'cursor:pointer;opacity:0;transition:opacity .2s;'
    );
    el.innerHTML =
      '<div style="color:' + color + ';font-weight:bold;margin-bottom:4px">' + title + '</div>' +
      '<div style="white-space:pre-wrap;word-break:break-word">' + body + '</div>' +
      '<div style="color:#565f89;font-size:11px;margin-top:6px">click to dismiss · see console for details</div>';
    el.addEventListener('click', function() {
      el.style.opacity = '0';
      setTimeout(function() { el.remove(); }, 200);
    });
    toastBox.appendChild(el);
    /* trigger transition */
    requestAnimationFrame(function() { el.style.opacity = '1'; });
    /* auto-dismiss after 12s */
    setTimeout(function() {
      el.style.opacity = '0';
      setTimeout(function() { el.remove(); }, 200);
    }, 12000);
  }

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  /* ── fuzzy ID matching ─────────────────────────────────────── *
   * When an #id selector fails, scan the DOM for similar IDs    *
   * and suggest the closest match.                              */
  function editDist(a, b) {
    if (a.length > b.length) { var t = a; a = b; b = t; }
    var prev = [];
    for (var i = 0; i <= a.length; i++) prev[i] = i;
    for (var j = 1; j <= b.length; j++) {
      var curr = [j];
      for (var i2 = 1; i2 <= a.length; i2++) {
        var cost = a[i2-1] === b[j-1] ? 0 : 1;
        curr[i2] = Math.min(curr[i2-1]+1, prev[i2]+1, prev[i2-1]+cost);
      }
      prev = curr;
    }
    return prev[a.length];
  }

  function suggestIds(selector) {
    /* Only suggest for #id selectors */
    if (!selector || selector[0] !== '#') return null;
    var target = selector.substring(1).toLowerCase();
    if (!target) return null;
    var allEls = document.querySelectorAll('[id]');
    var best = null, bestDist = 4;  /* max 3 edits */
    var available = [];
    for (var i = 0; i < allEls.length; i++) {
      var id = allEls[i].id;
      if (!id) continue;
      available.push('#' + id);
      var d2 = editDist(target, id.toLowerCase());
      if (d2 < bestDist) { bestDist = d2; best = id; }
    }
    return { suggestion: best, available: available.slice(0, 15) };
  }

  /* ── htmx:targetError ─────────────────────────────────────── *
   * Fires when hx-target selector matches nothing in the DOM.  *
   * The minified htmx logs "htmx:targetError" with no context. */
  document.body.addEventListener('htmx:targetError', function(evt) {
    var d  = evt.detail || {};
    var el = d.elt || evt.target;
    var targetSel = d.target || el.getAttribute('hx-target') || '(default — self)';
    var fuzzy = suggestIds(targetSel);

    console.group('%c htmx:targetError %c Target element not found in the DOM', ERR, '');
    console.log('%cSelector%c  ' + targetSel, LBL, VAL);
    if (fuzzy && fuzzy.suggestion)
      console.log('%cDid you mean?%c  #' + fuzzy.suggestion, LBL, 'color:#9ece6a;font-weight:bold');
    console.log('%cTrigger%c   ' + desc(el), LBL, VAL);
    var attrs = hxAttrs(el);
    if (Object.keys(attrs).length) console.table(attrs);
    if (fuzzy && fuzzy.available.length)
      console.log('%cIDs in DOM%c  ' + fuzzy.available.join(', '), LBL, DIM);
    console.log('%cFix%c       Check that an element matching "' + targetSel + '" exists in the DOM ' +
                'when this request fires.  Common causes:\\n' +
                '  · typo in the selector\\n' +
                '  · target removed by an earlier swap\\n' +
                '  · target inside a block that hasn\\'t rendered yet', LBL, DIM);
    console.log('Element →', el);
    console.groupEnd();

    var hint = fuzzy && fuzzy.suggestion ? '\\n\\nDid you mean #' + fuzzy.suggestion + '?' : '';
    toast(
      'Target Not Found',
      esc(targetSel) + hint + '\\n\\nTriggered by ' + esc(desc(el)),
      '#f7768e'
    );
  });

  /* ── htmx:responseError ────────────────────────────────────── *
   * Fires when the server returns a non-2xx status.             */
  document.body.addEventListener('htmx:responseError', function(evt) {
    var d   = evt.detail || {};
    var xhr = d.xhr || {};
    var el  = d.elt || evt.target;
    var url = d.pathInfo ? (d.pathInfo.requestPath || '') : '';
    var method = d.requestConfig ? (d.requestConfig.verb || '').toUpperCase() : '';
    var status = xhr.status || '?';
    var body = xhr.responseText || '';

    /* Detect chirp debug fragment — render it in a modal instead
     * of a useless "500" toast.  The server already did the hard
     * work of building a rich error page; show it. */
    var isDebugFragment = body.indexOf('chirp-error') !== -1;

    console.group('%c htmx:responseError %c Server returned ' + status, ERR, '');
    console.log('%cRequest%c  ' + method + ' ' + url, LBL, VAL);
    console.log('%cStatus%c   ' + status + ' ' + (xhr.statusText || ''), LBL, VAL);
    console.log('%cTrigger%c  ' + desc(el), LBL, VAL);
    if (!isDebugFragment) {
      var snippet = body.substring(0, 500);
      if (snippet) console.log('%cBody%c     ' + snippet, LBL, DIM);
    } else {
      console.log('%cDebug%c    Server sent a chirp debug page — opening overlay', LBL, 'color:#9ece6a');
    }
    console.log('Element →', el);
    console.groupEnd();

    if (isDebugFragment) {
      /* Show the server's debug page in a full overlay */
      var overlay = document.createElement('div');
      overlay.setAttribute('style',
        'position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.7);' +
        'display:flex;align-items:center;justify-content:center;padding:2rem;'
      );
      var inner = document.createElement('div');
      inner.setAttribute('style',
        'background:#1a1b26;border-radius:12px;max-width:960px;width:100%;' +
        'max-height:85vh;overflow-y:auto;box-shadow:0 8px 48px rgba(0,0,0,.6);' +
        'position:relative;'
      );
      /* close button */
      var close = document.createElement('button');
      close.textContent = '\\u00d7';
      close.setAttribute('style',
        'position:sticky;top:8px;float:right;margin:8px 12px 0 0;background:none;' +
        'border:none;color:#f7768e;font-size:24px;cursor:pointer;z-index:1;'
      );
      close.addEventListener('click', function() { overlay.remove(); });
      overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });
      inner.appendChild(close);
      var content = document.createElement('div');
      content.innerHTML = body;
      inner.appendChild(content);
      overlay.appendChild(inner);
      document.body.appendChild(overlay);
    } else {
      toast(
        status + ' Response Error',
        method + ' ' + esc(url) + '\\n' + (xhr.statusText || ''),
        '#f7768e'
      );
    }
  });

  /* ── htmx:sendError ───────────────────────────────────────── *
   * Network-level failure (server unreachable, CORS, etc.).     */
  document.body.addEventListener('htmx:sendError', function(evt) {
    var d  = evt.detail || {};
    var el = d.elt || evt.target;
    var url = d.pathInfo ? (d.pathInfo.requestPath || '') : '';
    var method = d.requestConfig ? (d.requestConfig.verb || '').toUpperCase() : '';

    console.group('%c htmx:sendError %c Network request failed', ERR, '');
    console.log('%cRequest%c  ' + method + ' ' + url, LBL, VAL);
    console.log('%cTrigger%c  ' + desc(el), LBL, VAL);
    console.log('%cFix%c      Is the server running?  Check the terminal for errors.', LBL, DIM);
    console.log('Element →', el);
    console.groupEnd();

    toast(
      'Network Error',
      method + ' ' + esc(url) + '\\nRequest failed — is the server running?',
      '#f7768e'
    );
  });

  /* ── htmx:swapError ──────────────────────────────────────── *
   * Error thrown during the DOM swap phase.                     */
  document.body.addEventListener('htmx:swapError', function(evt) {
    var d  = evt.detail || {};
    var el = d.elt || evt.target;
    var err = d.error || '(unknown)';

    console.group('%c htmx:swapError %c DOM swap failed', WARN, '');
    console.log('%cError%c    ' + err, LBL, VAL);
    console.log('%cTrigger%c  ' + desc(el), LBL, VAL);
    console.log('Element →', el);
    console.groupEnd();

    toast('Swap Error', esc(String(err)), '#e0af68');
  });

  /* ── htmx:timeout ─────────────────────────────────────────── */
  document.body.addEventListener('htmx:timeout', function(evt) {
    var d  = evt.detail || {};
    var el = d.elt || evt.target;
    var url = d.pathInfo ? (d.pathInfo.requestPath || '') : '';

    console.group('%c htmx:timeout %c Request timed out', WARN, '');
    console.log('%cURL%c      ' + url, LBL, VAL);
    console.log('%cTrigger%c  ' + desc(el), LBL, VAL);
    console.log('Element →', el);
    console.groupEnd();

    toast('Timeout', esc(url) + '\\nRequest timed out', '#e0af68');
  });

  /* ── htmx:onLoadError ─────────────────────────────────────── *
   * Error in an htmx:load event handler or hx-on:load.         */
  document.body.addEventListener('htmx:onLoadError', function(evt) {
    var d   = evt.detail || {};
    var err = d.error || '(unknown)';
    var el  = d.elt || evt.target;

    console.group('%c htmx:onLoadError %c Error in load handler', WARN, '');
    console.error(err);
    console.log('%cElement%c  ' + desc(el), LBL, VAL);
    console.log('Element →', el);
    console.groupEnd();

    toast('Load Handler Error', esc(String(err)), '#e0af68');
  });

  console.log(
    '%c chirp %c htmx debug overlay active — errors will appear as toasts + rich console messages',
    'background:#7aa2f7;color:#1a1b26;padding:2px 8px;border-radius:3px;font-weight:bold', ''
  );
})();
</script>
"""
