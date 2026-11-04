import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


ROOT = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="module")
def running_app(tmp_path_factory):
    database_path = tmp_path_factory.mktemp("e2e") / "akatosh.db"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "SECRET_KEY": "e2e-test-secret-key-that-is-at-least-32-chars",
            "REDIS_URL": "redis://127.0.0.1:6398/0",
            "FEATURE_ADMIN_TOKEN": "e2e-test-admin-token",
            "GEMINI_API_KEY": "e2e-test-gemini-key",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("API server stopped before becoming ready")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    else:
        process.terminate()
        process.wait(timeout=5)
        raise RuntimeError("API server did not become ready")

    yield base_url

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_recipe_book_end_to_end(running_app):
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Install Chromium with `playwright install chromium`: {exc}")

        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(running_app, wait_until="networkidle")
        assert page.title() == "Akatosh — Beer Recipe Book"
        assert page.locator('meta[name="description"]').get_attribute("content")
        assert page.locator("#lab-showcase").count() == 0
        assert page.locator("h1").inner_text() == "Brew something\nworth sharing."
        overflow = page.evaluate(
            """() => [...document.querySelectorAll("body *")]
              .map(element => ({
                tag: element.tagName,
                id: element.id,
                className: typeof element.className === "string" ? element.className : "",
                right: Math.round(element.getBoundingClientRect().right),
                width: Math.round(element.getBoundingClientRect().width),
              }))
              .filter(element => element.right > window.innerWidth + 1)"""
        )
        assert not overflow, overflow

        page.get_by_label("Email").fill("e2e-brewer@example.com")
        page.get_by_label("Password").fill("safe-password-123")
        page.get_by_role("button", name="Create account").click()
        page.locator("#account-email").get_by_text("e2e-brewer@example.com").wait_for()
        assert page.locator("#status").inner_text() == ""
        assert page.get_by_text("JSON REST API · tenant scoped").count() == 0
        assert page.get_by_text("Explore the lab project").count() == 0
        assert page.locator(".hero-facts").count() == 0
        assert page.locator(".navbar-brand").inner_text() == "Akatosh"
        assert page.locator("#auth-panel").is_hidden()
        assert page.locator("#account-session").is_visible()
        assert page.locator("#recipe-editor").is_visible()
        assert page.locator("#recipe-file").is_visible()

        page.locator('#recipe-form [name="title"]').fill("E2E Golden Ale")
        page.locator('#recipe-form [name="style"]').fill("Golden Ale")
        page.locator('#recipe-form [name="abv"]').fill("5.1")
        page.locator('#recipe-form [name="ibu"]').fill("30")
        ingredient = page.locator(".ingredient-row").first
        ingredient.locator(".ingredient-name").fill("Cascade")
        ingredient.locator(".ingredient-type").select_option(label="Hop")
        ingredient.locator(".ingredient-amount").fill("20")
        page.get_by_role("button", name="Save recipe").click()
        recipe_card = page.get_by_role("article").filter(has_text="E2E Golden Ale")
        recipe_card.wait_for()
        assert "5.1% ABV" in recipe_card.inner_text()
        assert "Cascade · 20 g Hop" in recipe_card.inner_text()
        recipe_card.get_by_role("button", name="View details").click()
        detail_modal = page.locator("#recipe-details-modal")
        detail_modal.wait_for(state="visible")
        assert page.locator("#recipe-detail-title").inner_text() == "E2E Golden Ale"
        assert page.locator("#recipe-detail-abv").inner_text() == "5.1%"
        assert page.locator("#recipe-detail-ingredients").inner_text() == "Cascade · 20 g Hop"
        detail_modal.locator(".modal-footer").get_by_role(
            "button", name="Close"
        ).click()
        detail_modal.wait_for(state="hidden")

        assistant_request_content_types = []
        page.on(
            "request",
            lambda request: assistant_request_content_types.append(
                request.headers.get("content-type")
            )
            if request.url.endswith("/api/assistant/stream")
            else None,
        )
        page.route(
            "**/api/assistant/stream",
            lambda route: route.fulfill(
                status=200,
                content_type="text/event-stream",
                body=(
                    'event: progress\ndata: {"message": "Checking recipe tools…"}\n\n'
                    'data: {"text": "Try a small dry-hop addition."}\n\n'
                    "event: done\ndata: {}\n\n"
                ),
            ),
        )
        page.locator("#prompt").fill("How should I improve aroma?")
        page.get_by_role("button", name="Ask the assistant").click()
        page.get_by_text("Try a small dry-hop addition.").wait_for()
        assert page.locator("#assistant-status").inner_text() == "Answer complete."
        assert assistant_request_content_types == ["application/json"]

        page.unroute("**/api/assistant/stream")
        page.route(
            "**/api/assistant/stream",
            lambda route: route.fulfill(
                status=200,
                content_type="text/event-stream",
                body='event: error\ndata: {"error":{"message":"Gemini rejected the request"}}\n\n',
            ),
        )
        page.locator("#prompt").fill("Why did this fail?")
        page.get_by_role("button", name="Ask the assistant").click()
        page.get_by_text("Gemini rejected the request").wait_for()
        assert page.locator("#assistant-status").inner_text() == "Gemini rejected the request"

        recipe_card.get_by_role("button", name="Edit recipe").click()
        assert page.locator("#recipe-editor-title").inner_text() == "Edit recipe"
        assert page.locator('#recipe-form [name="title"]').input_value() == "E2E Golden Ale"
        page.locator('#recipe-form [name="title"]').fill("E2E Updated Golden Ale")
        page.locator('#recipe-form [name="abv"]').fill("5.4")
        edited_ingredient = page.locator(".ingredient-row").first
        assert edited_ingredient.locator(".ingredient-name").input_value() == "Cascade"
        edited_ingredient.locator(".ingredient-name").fill("Centennial")
        edited_ingredient.locator(".ingredient-amount").fill("25")
        page.get_by_role("button", name="Save changes").click()
        updated_recipe_card = page.get_by_role("article").filter(
            has_text="E2E Updated Golden Ale"
        )
        updated_recipe_card.wait_for()
        assert "5.4% ABV" in updated_recipe_card.inner_text()
        assert "Centennial · 25 g Hop" in updated_recipe_card.inner_text()
        assert page.locator("#recipe-editor-title").inner_text() == "Add a recipe"
        assert page.locator("#cancel-edit").is_hidden()

        updated_recipe_card.get_by_role("button", name="Delete recipe").click()
        page.get_by_text("No recipes yet. Add one with the form to get started.").wait_for()

        page.reload(wait_until="networkidle")
        page.locator("#account-session").wait_for(state="visible")
        assert page.locator("#account-email").inner_text() == "e2e-brewer@example.com"
        assert page.locator("#auth-panel").is_hidden()
        assert page.locator("#recipe-editor").is_visible()

        page.get_by_role("button", name="Sign out").click()
        page.locator("#auth-panel").wait_for(state="visible")
        page.locator("#account-session").wait_for(state="hidden")
        page.locator("#recipe-editor").wait_for(state="hidden")
        browser.close()
