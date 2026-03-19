/**
 * Ticker island adapter — simulates live stock price updates.
 *
 * Reads stock data from props, updates prices randomly every 2 seconds.
 * Returns a cleanup function that clears the interval on unmount.
 */
export function mount(payload, api) {
  const el = payload.element;
  const stocks = (payload.props && payload.props.stocks) || [];

  const display = el.querySelector("#ticker-display");
  if (!display || stocks.length === 0) return;

  // Clone stock data for mutation
  const liveStocks = stocks.map(function(s) {
    return { symbol: s.symbol, price: s.price, change: s.change };
  });

  function render() {
    display.innerHTML = liveStocks.map(function(s) {
      var color = s.change >= 0 ? "var(--chirpui-color-success, green)" : "var(--chirpui-color-danger, red)";
      var arrow = s.change >= 0 ? "▲" : "▼";
      return '<span style="color:' + color + '">' + s.symbol + ': $' + s.price.toFixed(2) + ' ' + arrow + '</span>';
    }).join("  ");
  }

  function tick() {
    liveStocks.forEach(function(s) {
      var delta = (Math.random() - 0.48) * 2;
      s.price = Math.max(1, s.price + delta);
      s.change = delta;
    });
    render();
  }

  render();
  var interval = setInterval(tick, 2000);

  return function cleanup() {
    clearInterval(interval);
  };
}

export function unmount(payload, api) {
  // Cleanup handled by mount's return value
}
