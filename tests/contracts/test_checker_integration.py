from chirp import App
from chirp.config import AppConfig
from chirp.contracts import check_hypermedia_surface


def test_checker_golden_category_counts(tmp_path) -> None:
    template = tmp_path / "index.html"
    template.write_text(
        '<div id="results"></div><button hx-post="/save" hx-target="#missing"></button>',
        encoding="utf-8",
    )

    app = App(AppConfig(template_dir=str(tmp_path), debug=False))

    @app.route("/")
    def index():
        return "ok"

    @app.route("/save", methods=["GET"])
    def save():
        return "ok"

    result = check_hypermedia_surface(app)
    categories = [issue.category for issue in result.issues]
    assert categories.count("method") == 1
    assert categories.count("hx-target") >= 1
    assert categories.count("dead") == 1


def test_checker_never_reports_setup_for_frozen_app(tmp_path) -> None:
    template = tmp_path / "index.html"
    template.write_text("<div id='ok'></div>", encoding="utf-8")

    app = App(AppConfig(template_dir=str(tmp_path), debug=False))

    @app.route("/")
    def index():
        return "ok"

    app._ensure_frozen()
    result = check_hypermedia_surface(app)
    assert all(issue.category != "setup" for issue in result.issues)
