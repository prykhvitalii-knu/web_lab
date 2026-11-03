from unittest.mock import Mock, patch

from app.telegram import send_telegram_notification


def test_send_notification_posts_to_telegram():
    response = Mock(is_error=False)
    response.json.return_value = {"ok": True}

    with (
        patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": "123:token", "TELEGRAM_CHAT_ID": "456"},
        ),
        patch("app.telegram.httpx.post", return_value=response) as post,
    ):
        sent = send_telegram_notification("Pale Ale", "IPA", 6.5)

    assert sent is True
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "https://api.telegram.org/bot123:token/sendMessage"
    assert kwargs["data"] == {
        "chat_id": "456",
        "text": "New Akatosh beer recipe\n\nName: Pale Ale\nStyle: IPA\nABV: 6.5%",
    }


def test_send_notification_skips_without_configuration():
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("app.telegram.httpx.post") as post,
    ):
        sent = send_telegram_notification("Pale Ale", "IPA", 6.5)

    assert sent is False
    post.assert_not_called()


def test_send_notification_returns_false_when_telegram_rejects_request():
    response = Mock(is_error=False)
    response.json.return_value = {
        "ok": False,
        "error_code": 400,
        "description": "chat not found",
    }

    with (
        patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": "123:token", "TELEGRAM_CHAT_ID": "456"},
        ),
        patch("app.telegram.httpx.post", return_value=response),
    ):
        sent = send_telegram_notification("Pale Ale", "IPA", 6.5)

    assert sent is False
