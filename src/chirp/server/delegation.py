"""Event delegation for dynamic content (SSE, OOB, fragments).

``hx-on`` is bound at parse time; content swapped by htmx (SSE, OOB,
fragments) does not get new handlers. This script uses event delegation
on ``document`` so handlers work for dynamically inserted elements.

Handles:
- ``.copy-btn`` — copies text from ancestor ``[data-copy-text]`` to clipboard
- ``.compare-switch`` — toggles ``aria-checked`` and syncs ``input[name=compare]``,
  ``select[name=model_b]`` in the same form

Injected into full-page HTML responses via ``HTMLInject`` middleware.
Controlled by ``AppConfig(delegation=True)`` (default: ``False``).
"""

DELEGATION_JS = """\
(function(){
  if(window.__chirpDelegation)return;
  window.__chirpDelegation=true;
  function handleCompareSwitch(btn){
    if(!btn||btn.getAttribute("role")!=="switch")return;
    var wasOn=btn.getAttribute("aria-checked")==="true";
    btn.setAttribute("aria-checked",wasOn?"false":"true");
    var form=btn.closest("form");
    if(!form)return;
    var cb=form.querySelector("input[name=compare]");
    var sel=form.querySelector("select[name=model_b]");
    if(cb)cb.checked=!wasOn;
    if(sel){sel.disabled=wasOn;sel.setAttribute("aria-hidden",wasOn);}
  }
  document.body.addEventListener("click",function(e){
    var btn=e.target.closest(".compare-switch");
    if(btn){e.preventDefault();e.stopPropagation();handleCompareSwitch(btn);return;}
    var copyBtn=e.target.closest(".copy-btn");
    if(copyBtn){
      var wrap=copyBtn.closest("[data-copy-text]");
      if(wrap){
        var text=wrap.dataset.copyText||"";
        navigator.clipboard.writeText(text).then(function(){
          copyBtn.textContent="Copied!";
          setTimeout(function(){copyBtn.textContent="Copy";},1500);
        });
      }
    }
  });
})();
"""

DELEGATION_SNIPPET = (
    '<script data-chirp="delegation">' + DELEGATION_JS + "</script>"
)
