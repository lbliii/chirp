# RFC: Contract Validation Extensions

**Status**: Draft  
**Date**: 2026-02-10  
**Scope**: `src/chirp/contracts.py`  
**Related**: Gap Analysis — Kida/Chirp Strategic Plan  
**Depends on**: Gap 1 RFC (Typed `{% def %}` in Kida), Gap 3 RFC (Form Patterns)

---

## Problem

`app.check()` is Chirp's killer differentiator — no other Python web framework
validates the server-client boundary at startup. Currently it checks
(`src/chirp/contracts.py:435-587`):

1. Fragment contracts — routes reference valid templates and blocks
2. htmx URL targets — `hx-get`, `hx-post`, etc. resolve to registered routes
3. Form actions — `action="/path"` resolves to registered routes
4. hx-target selectors — `hx-target="#id"` references exist
5. Accessibility — htmx on non-interactive elements
6. Orphan routes — routes never referenced from templates

This is already more than any competitor offers. But there are four categories
of bugs that slip through — and Chirp has the information to catch them.

### Bugs That Still Escape

**1. Form field / dataclass mismatch**: A template has
`<input name="titl">` but the handler expects `TaskForm.title`. Discovered
when a user submits the form and gets a `FormBindingError`.

**2. Component call-site errors**: A template calls
`{% call card(titl="x") %}` but `card` expects `title`. Discovered at render
time. (Requires Gap 1 — typed `{% def %}` parameters.)

**3. SSE fragment validity**: An `EventStream` handler yields
`Fragment("chat.html", "messge")` with a typo. Discovered when the SSE stream
sends an empty event.

**4. Dead templates**: Templates in the templates directory that no route
references and no other template includes. These accumulate during refactors
and create confusion about what's active.

---

## Goals

1. Extend `check_hypermedia_surface()` with four new validation passes.
2. Maintain the existing severity model (ERROR, WARNING, INFO).
3. Each extension is independently useful — no all-or-nothing requirement.
4. Zero false positives where possible; clear warnings where heuristic.

### Non-Goals

- Runtime validation (contracts are compile-time only).
- Type-level validation of template context (would require inter-language
  type checking).
- Blocking deployment on warnings (only errors cause `SystemExit(1)`).

---

## Design

### Extension 1: Form Field Validation

**What it checks**: For routes that use `form_from()` or `form_or_errors()`
with a dataclass, compare the dataclass fields against `<input name="...">`,
`<select name="...">`, and `<textarea name="...">` in the associated
template.

**How it works**:

1. During `_freeze()`, inspect route handlers for type hints that reference
   `form_from` or `form_or_errors` calls. Extract the dataclass type from
   the type annotation or source inspection.

2. Alternatively, use a `FormContract` declaration:

```python
@dataclass(frozen=True, slots=True)
class FormContract:
    """Declares which dataclass a route binds form data to."""
    datacls: type
    template: str
    block: str | None = None  # None = full template
```

```python
@app.route("/tasks", methods=["POST"],
           contract=RouteContract(
               form=FormContract(TaskForm, "tasks.html", "task_form"),
           ))
async def add_task(request: Request):
    ...
```

3. During `check_hypermedia_surface()`:
   - Load the template (or block) source
   - Extract `<input name="...">` and `<select name="...">` from HTML
   - Compare against `dataclasses.fields(datacls)`
   - Report mismatches:

```
ERROR [form] Route '/tasks' (POST) expects field 'title' (TaskForm.title)
       but template 'tasks.html' block 'task_form' has no <input name="title">.

WARNING [form] Template 'tasks.html' block 'task_form' has <input name="titl">
         which does not match any field in TaskForm. Did you mean 'title'?
```

**Severity**: Missing fields are ERROR (form will fail). Extra fields are
WARNING (may be intentional — hidden fields, CSRF tokens, etc.).

**Category**: `"form"`

### Extension 2: Component Call Validation

**Requires**: Gap 1 RFC (Typed `{% def %}` parameters in Kida)

**What it checks**: When Kida's analysis pass detects `{% def %}` definitions
with typed parameters, validate all `{% call %}` sites across the template
tree.

**How it works**:

1. After compiling templates, use Kida's analysis API to extract `Def` node
   signatures from each template.

2. Walk the AST for `CallBlock` nodes and match call arguments against the
   definition's parameters.

3. Report mismatches:

```
ERROR [component] Template 'board.html' calls card(titl="x") at line 45
       but card() has no parameter 'titl'. Did you mean 'title'?

WARNING [component] Template 'board.html' calls card() at line 52
         without required parameter 'title' (defined in components/_card.html:8).
```

**Implementation**: This is primarily a Kida-side analysis pass (see Gap 1
RFC). Chirp's `check_hypermedia_surface()` invokes it:

```python
# In check_hypermedia_surface():

# 7. Component call validation (requires kida typed def support)
if hasattr(kida_env, 'validate_calls'):
    for issue in kida_env.validate_calls():
        result.issues.append(ContractIssue(
            severity=Severity.ERROR if issue.is_error else Severity.WARNING,
            category="component",
            message=issue.message,
            template=issue.template,
        ))
```

**Severity**: Unknown parameters are ERROR. Missing optional parameters are
INFO (may have defaults).

**Category**: `"component"`

### Extension 3: SSE Fragment Validation

**What it checks**: Routes with `SSEContract` that declare fragment event
types should have those fragments resolvable.

**How it works**:

1. Extend `SSEContract` with optional fragment metadata:

```python
@dataclass(frozen=True, slots=True)
class SSEContract:
    event_types: frozenset[str] = frozenset()
    fragments: tuple[FragmentContract, ...] = ()  # NEW
```

2. During `check_hypermedia_surface()`, validate each fragment in the contract:

```python
for fc in contract.fragments:
    tmpl = kida_env.get_template(fc.template)
    if fc.block not in tmpl.blocks:
        result.issues.append(ContractIssue(
            severity=Severity.ERROR,
            category="sse",
            message=f"SSE route '{route.path}' yields Fragment "
                    f"'{fc.template}':'{fc.block}' but block doesn't exist.",
            route=route.path,
            template=fc.template,
        ))
```

**Severity**: ERROR — a missing block means SSE events will fail.

**Category**: `"sse"`

### Extension 4: Dead Template Detection

**What it checks**: Templates in the templates directory that are never
referenced by any route, include, extends, or import.

**How it works**:

1. Collect all template names from the loader
   (`kida_env.loader.list_templates()`).

2. Collect all referenced templates:
   - Route return types (`Template.name`, `Fragment.template_name`, etc.)
   - `{% extends "..." %}` in template source
   - `{% include "..." %}` in template source
   - `{% from "..." import ... %}` in template source

3. Templates in the loader but not in the referenced set are "dead":

```
INFO [dead] Template 'old_dashboard.html' is not referenced by any route
      or template.  Consider removing it.
```

**Severity**: INFO — dead templates are not bugs, but they're cleanup
candidates.

**Category**: `"dead"`

---

## Implementation Plan

### Phase 1: Dead Template Detection (standalone, no dependencies)

Add to `check_hypermedia_surface()`:

```python
# After existing checks:

# 7. Dead template detection
all_templates = set(kida_env.loader.list_templates())
referenced_templates = set()

# From routes
for route in router.routes:
    contract = getattr(route.handler, "_chirp_contract", None)
    if contract and isinstance(contract.returns, FragmentContract):
        referenced_templates.add(contract.returns.template)

# From template sources (extends, includes, imports)
for tmpl_name, source in template_sources.items():
    referenced_templates.update(_extract_template_references(source))

# Report dead templates
for tmpl_name in sorted(all_templates - referenced_templates):
    if not tmpl_name.startswith("_"):  # Skip partials by convention
        result.issues.append(ContractIssue(
            severity=Severity.INFO,
            category="dead",
            message=f"Template '{tmpl_name}' is not referenced by any route or template.",
            template=tmpl_name,
        ))
```

### Phase 2: SSE Fragment Validation (small extension to existing)

Extend the existing fragment contract checking loop to also cover
`SSEContract.fragments`.

### Phase 3: Form Field Validation (requires Gap 3)

After `form_or_errors()` and `FormContract` are implemented, add the
form field comparison pass.

### Phase 4: Component Call Validation (requires Gap 1)

After Kida's typed `{% def %}` and analysis pass are implemented, wire
the results into Chirp's contract checker.

---

## Updated `CheckResult` Statistics

Extend `CheckResult` (`src/chirp/contracts.py:390-432`) with new counters:

```python
@dataclass
class CheckResult:
    issues: list[ContractIssue] = field(default_factory=list)
    routes_checked: int = 0
    templates_scanned: int = 0
    targets_found: int = 0
    hx_targets_validated: int = 0

    # New counters
    forms_validated: int = 0         # Phase 3
    component_calls_validated: int = 0  # Phase 4
    dead_templates_found: int = 0    # Phase 1
    sse_fragments_validated: int = 0 # Phase 2
```

---

## Testing Strategy

1. **Dead template detection**: Create apps with unused templates, verify they
   are reported. Verify partials (`_partial.html`) are excluded by convention.
2. **SSE fragment validation**: Declare `SSEContract` with valid and invalid
   fragments, verify errors.
3. **Form field validation**: Create routes with `FormContract`, templates with
   matching/mismatching field names, verify correct errors and warnings.
4. **Component call validation**: After Gap 1 lands, create templates with
   typed `{% def %}` and incorrect `{% call %}` sites, verify errors.
5. **False positive tests**: Verify that dynamic expressions, conditional
   includes, and computed field names don't trigger false positives.

---

## Future Considerations

1. **`--strict` mode**: Treat warnings as errors for CI pipelines.
2. **JSON output**: `chirp check --json myapp:app` for machine-readable results.
3. **Watch mode**: `chirp check --watch` re-validates on file changes.
4. **IDE integration**: LSP-compatible diagnostics from contract checking.
5. **Cross-app validation**: Check consistency between multiple Chirp services
   that link to each other.
