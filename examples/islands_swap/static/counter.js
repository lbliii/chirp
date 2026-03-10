/**
 * Counter island adapter — no-build ES module.
 */
export function mount(payload, api) {
  const el = payload.element;
  const initialCount = (payload.props && payload.props.initial_count) || 0;

  const valueEl = el.querySelector("#counter-value");
  const btn = el.querySelector("button");

  if (!valueEl || !btn) return;

  let count = initialCount;
  valueEl.textContent = String(count);
  btn.textContent = "Click to increment";
  btn.disabled = false;

  function onClick() {
    count += 1;
    valueEl.textContent = String(count);
  }

  btn.addEventListener("click", onClick);

  return function cleanup() {
    btn.removeEventListener("click", onClick);
  };
}

export function unmount(payload, api) {}
