"""Tests for form field extraction and validation."""

from dataclasses import dataclass

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import FormContract, check_hypermedia_surface, contract
from chirp.contracts.rules_forms import extract_form_field_names


class TestExtractFormFieldNames:
    """Unit tests for _extract_form_field_names."""

    def test_input(self):
        html = '<input name="title" type="text">'
        assert extract_form_field_names(html) == {"title"}

    def test_select(self):
        html = '<select name="status"><option>open</option></select>'
        assert extract_form_field_names(html) == {"status"}

    def test_textarea(self):
        html = '<textarea name="body"></textarea>'
        assert extract_form_field_names(html) == {"body"}

    def test_multiple_fields(self):
        html = (
            '<input name="title" type="text">'
            '<textarea name="body"></textarea>'
            '<select name="priority"><option>P1</option></select>'
        )
        assert extract_form_field_names(html) == {"title", "body", "priority"}

    def test_excludes_csrf_token(self):
        html = '<input name="_csrf_token" type="hidden"><input name="title">'
        assert extract_form_field_names(html) == {"title"}

    def test_skips_template_expressions(self):
        html = '<input name="{{ field_name }}">'
        assert extract_form_field_names(html) == set()

    def test_empty_source(self):
        assert extract_form_field_names("") == set()


class TestFormFieldValidation:
    """Integration tests for form field validation in check_hypermedia_surface."""

    def test_matching_fields_pass(self, tmp_path):
        """Template fields match dataclass fields — no issues."""

        @dataclass
        class TaskForm:
            title: str
            body: str

        (tmp_path / "tasks.html").write_text(
            '<form><input name="title" type="text"><textarea name="body"></textarea></form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "tasks.html"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_issues = [i for i in result.issues if i.category == "form"]
        assert len(form_issues) == 0
        assert result.forms_validated == 1

    def test_missing_field_reports_error(self, tmp_path):
        """Dataclass field missing from template = ERROR."""

        @dataclass
        class TaskForm:
            title: str
            body: str

        (tmp_path / "tasks.html").write_text('<form><input name="title" type="text"></form>')
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "tasks.html"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_errors = [i for i in result.errors if i.category == "form"]
        assert len(form_errors) == 1
        assert "body" in form_errors[0].message
        assert "TaskForm.body" in form_errors[0].message

    def test_extra_field_warns_with_suggestion(self, tmp_path):
        """Extra template field with typo = WARNING with 'did you mean?'."""

        @dataclass
        class TaskForm:
            title: str

        (tmp_path / "tasks.html").write_text(
            '<form><input name="title" type="text"><input name="titl" type="text"></form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "tasks.html"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_warnings = [i for i in result.warnings if i.category == "form"]
        assert len(form_warnings) == 1
        assert "titl" in form_warnings[0].message
        assert "Did you mean 'title'?" in form_warnings[0].message

    def test_csrf_token_excluded(self, tmp_path):
        """Hidden CSRF token field should not trigger a warning."""

        @dataclass
        class LoginForm:
            username: str
            password: str

        (tmp_path / "login.html").write_text(
            "<form>"
            '<input name="_csrf_token" type="hidden">'
            '<input name="username" type="text">'
            '<input name="password" type="password">'
            "</form>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/login", methods=["POST"])
        @contract(form=FormContract(LoginForm, "login.html"))
        async def login():
            return "ok"

        result = check_hypermedia_surface(app)
        form_issues = [i for i in result.issues if i.category == "form"]
        assert len(form_issues) == 0

    def test_block_scoped_extraction(self, tmp_path):
        """FormContract with block= restricts field scanning to that block."""

        @dataclass
        class TaskForm:
            title: str

        (tmp_path / "page.html").write_text(
            '{% block header %}<input name="search">{% endblock %}'
            "{% block task_form %}"
            '<form><input name="title" type="text"></form>'
            "{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "page.html", block="task_form"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_issues = [i for i in result.issues if i.category == "form"]
        # "search" is in header block, not task_form — should not warn
        assert len(form_issues) == 0
