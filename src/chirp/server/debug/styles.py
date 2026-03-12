"""CSS and JS for debug error page."""

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: ui-monospace, 'Cascadia Code', 'Source Code Pro', Menlo, Consolas,
                 'DejaVu Sans Mono', monospace;
    background: #1a1b26; color: #a9b1d6; line-height: 1.6;
    padding: 2rem; font-size: 14px;
}
.error-page { max-width: 960px; margin: 0 auto; }
h1 { color: #f7768e; font-size: 1.4rem; margin-bottom: 0.5rem; }
h2 { color: #7aa2f7; font-size: 1.1rem; margin: 1.5rem 0 0.5rem; border-bottom: 1px solid #2f3549; padding-bottom: 0.3rem; }
h3 { color: #bb9af7; font-size: 0.95rem; margin: 0.8rem 0 0.3rem; }
.exc-message { color: #e0af68; font-size: 1rem; margin-bottom: 1rem; white-space: pre-wrap; word-break: break-word; }
.exc-chain { color: #565f89; font-size: 0.85rem; margin-bottom: 0.5rem; font-style: italic; }

/* Frames */
.frame { margin: 0.5rem 0; border: 1px solid #2f3549; border-radius: 6px; overflow: hidden; }
.frame.app-frame { border-color: #7aa2f7; }
.frame-header { padding: 0.4rem 0.8rem; background: #24283b; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; }
.frame-header a { color: #7dcfff; text-decoration: none; }
.frame-header a:hover { text-decoration: underline; }
.frame-header .func { color: #bb9af7; }
.frame-header .app-badge { color: #9ece6a; font-size: 0.75rem; margin-left: 0.5rem; }
.source { padding: 0; margin: 0; overflow-x: auto; }
.source-line { display: flex; padding: 0 0.8rem; font-size: 0.82rem; }
.source-line .lineno { color: #565f89; min-width: 3.5rem; text-align: right; padding-right: 1rem; user-select: none; flex-shrink: 0; }
.source-line .code { white-space: pre; }
.source-line.error-line { background: rgba(247, 118, 142, 0.15); }
.source-line.error-line .lineno { color: #f7768e; }

/* Locals */
.locals-toggle { cursor: pointer; color: #565f89; font-size: 0.8rem; padding: 0.3rem 0.8rem; user-select: none; }
.locals-toggle:hover { color: #7aa2f7; }
.locals { display: none; padding: 0.4rem 0.8rem; background: #1a1b26; border-top: 1px solid #2f3549; font-size: 0.8rem; }
.locals.open { display: block; }
.local-var { display: flex; gap: 0.5rem; padding: 0.15rem 0; }
.local-var .name { color: #7dcfff; min-width: 120px; flex-shrink: 0; }
.local-var .value { color: #a9b1d6; white-space: pre-wrap; word-break: break-all; }
.frame-collapsed { margin: 0.5rem 0; border: 1px solid #2f3549; border-radius: 6px; overflow: hidden; }
.frame-collapsed .collapse-toggle { padding: 0.4rem 0.8rem; background: #24283b; font-size: 0.85rem; cursor: pointer; color: #565f89; }
.frame-collapsed .collapse-toggle:hover { color: #7aa2f7; }
.frame-collapsed .collapse-content { display: none; }
.frame-collapsed.open .collapse-content { display: block; }
.frame-collapsed.open .collapse-toggle .arrow { transform: rotate(0deg); }
.frame-collapsed .collapse-toggle .arrow { display: inline-block; margin-right: 0.5rem; transform: rotate(-90deg); }

/* Request context */
.request-panel { background: #24283b; border-radius: 6px; padding: 0.8rem; margin: 0.5rem 0; }
.request-line { display: flex; gap: 0.5rem; padding: 0.15rem 0; font-size: 0.85rem; }
.request-line .label { color: #7aa2f7; min-width: 140px; flex-shrink: 0; }
.request-line .val { color: #a9b1d6; word-break: break-all; }

/* Template error panel */
.template-panel { background: #1f2335; border: 1px solid #e0af68; border-radius: 6px; padding: 0.8rem; margin: 0.5rem 0; }
.template-panel h3 { color: #e0af68; }
.template-source { margin: 0.5rem 0; }
.template-source .source-line { font-size: 0.85rem; }
.template-suggestion { color: #9ece6a; font-style: italic; margin-top: 0.4rem; }
.template-values { margin-top: 0.4rem; }

/* Fragment (compact) mode */
.chirp-error-fragment { font-family: ui-monospace, monospace; font-size: 13px; color: #a9b1d6; background: #1a1b26; padding: 1rem; border: 2px solid #f7768e; border-radius: 6px; max-height: 70vh; overflow-y: auto; }
.chirp-error-fragment h1 { font-size: 1.1rem; }
.chirp-error-fragment .frame { margin: 0.3rem 0; }
"""

_TOGGLE_JS = """\
document.querySelectorAll('.locals-toggle').forEach(el => {
    el.addEventListener('click', () => {
        const panel = el.nextElementSibling;
        panel.classList.toggle('open');
        el.textContent = panel.classList.contains('open') ? '▾ locals' : '▸ locals';
    });
});
document.querySelectorAll('.frame-collapsed .collapse-toggle').forEach(el => {
    el.addEventListener('click', () => {
        el.closest('.frame-collapsed').classList.toggle('open');
    });
});
"""
