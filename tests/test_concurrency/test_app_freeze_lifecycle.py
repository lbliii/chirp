"""Concurrency tests for app freeze lifecycle publication."""

import threading

from chirp import App

from .conftest import STRESS_TIMEOUT, ThreadStressResult, run_threads_synchronized


class _CountingDomain:
    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def register(self, app: App) -> None:
        with self._lock:
            self.calls += 1


class TestAppFreezeLifecycle:
    def test_concurrent_freeze_publishes_runtime_once(self) -> None:
        app = App()
        domain = _CountingDomain()
        app.register_domain(domain)

        @app.route("/", name="home")
        def home():
            return "ok"

        def worker(_idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            try:
                app.freeze()
                result.record(app.url_for("home"))
            except Exception as exc:
                result.record_error(exc)

        result = run_threads_synchronized(40, worker, timeout=STRESS_TIMEOUT)

        assert not result.errors
        assert result.results == ["/"] * 40
        assert domain.calls == 1

    def test_freeze_setup_apis_reject_threaded_post_freeze_mutation(self) -> None:
        app = App()
        app.freeze()

        def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            try:
                if idx % 2 == 0:
                    app.freeze_exclude(f"/late/{idx}")
                else:

                    @app.freeze_params(f"/late/{idx}/{{id}}")
                    def params():
                        return [{"id": "1"}]
            except RuntimeError as exc:
                result.record(str(exc))
            except Exception as exc:
                result.record_error(exc)

        result = run_threads_synchronized(20, worker, timeout=STRESS_TIMEOUT)

        assert not result.errors
        assert len(result.results) == 20
        assert all("Cannot modify the app" in message for message in result.results)
        assert not app._mutable_state.freeze_exclude
        assert not app._mutable_state.freeze_param_providers
