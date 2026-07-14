"""Real-browser controls and intentional failures for a11y research issue #686."""

from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = sync_api.Error
sync_playwright = sync_api.sync_playwright

_FIXTURE = Path(__file__).with_name("templates") / "a11y_interactions.html"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"Chromium not installed for Playwright: {exc}")
        try:
            yield chromium
        finally:
            chromium.close()


def _page(browser, *, reduced_motion: str = "no-preference"):
    context = browser.new_context(reduced_motion=reduced_motion)
    page = context.new_page()
    page.set_content(_FIXTURE.read_text(encoding="utf-8"))
    return context, page


@pytest.mark.issue(686)
def test_focus_control_preserves_identity_and_broken_swap_detaches_focus(browser) -> None:
    context, page = _page(browser)
    try:
        page.locator("#good-focus-control").click()
        assert page.evaluate("document.activeElement.id") == "good-focus-control"

        page.locator("#bad-focus-control").click()
        assert page.evaluate("document.activeElement === document.body") is True
        assert page.locator("#bad-focus-control").count() == 0
    finally:
        context.close()


@pytest.mark.issue(686)
def test_unattended_update_preserves_focus_and_broken_outer_swap_drops_policy(browser) -> None:
    context, page = _page(browser)
    try:
        page.locator("#focus-probe").focus()
        page.evaluate("goodLiveUpdate()")
        assert page.evaluate("document.activeElement.id") == "focus-probe"
        assert page.locator("#good-live-region").get_attribute("aria-live") == "polite"

        page.evaluate("badLiveUpdate()")
        assert page.evaluate("document.activeElement.id") == "focus-probe"
        assert page.locator("#bad-live-region").get_attribute("aria-live") is None
        assert page.locator("#bad-live-region").get_attribute("role") is None
    finally:
        context.close()


@pytest.mark.issue(686)
def test_native_dialog_and_auto_popover_controls_expose_broken_custom_dialog(browser) -> None:
    context, page = _page(browser)
    try:
        page.locator("#good-dialog-open").click()
        assert page.locator("#good-dialog").evaluate("element => element.open") is True
        assert page.evaluate("document.activeElement.id") == "good-dialog-close"
        page.keyboard.press("Escape")
        assert page.locator("#good-dialog").evaluate("element => element.open") is False
        assert page.evaluate("document.activeElement.id") == "good-dialog-open"

        page.locator("#bad-dialog-open").click()
        assert page.locator("#bad-dialog").is_visible()
        assert page.evaluate("document.activeElement.id") == "bad-dialog-open"
        page.keyboard.press("Escape")
        assert page.locator("#bad-dialog").is_visible()

        page.locator("#popover-open").click()
        assert page.locator("#auto-popover").is_visible()
        page.keyboard.press("Escape")
        assert not page.locator("#auto-popover").is_visible()
    finally:
        context.close()


@pytest.mark.issue(686)
@pytest.mark.parametrize(
    ("preference", "expected_duration"),
    [("no-preference", "2s"), ("reduce", "0.001s")],
)
def test_reduced_motion_changes_animation_not_focus_result(
    browser, preference: str, expected_duration: str
) -> None:
    context, page = _page(browser, reduced_motion=preference)
    try:
        page.locator("#focus-probe").focus()
        page.evaluate("runMotionUpdate()")
        assert page.evaluate("document.activeElement.id") == "focus-probe"
        duration = page.locator("#motion-target").evaluate(
            "element => getComputedStyle(element).animationDuration"
        )
        assert duration == expected_duration
    finally:
        context.close()
