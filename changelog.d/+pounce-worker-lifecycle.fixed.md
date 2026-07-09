Production worker lifecycle hooks now use Pounce 0.9's fail-loud startup
policy across direct, `App.run()`, and CLI launches. Sync workers are no
longer rejected, while subinterpreter launches remain explicitly unsupported
with an actionable error.
