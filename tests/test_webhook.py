"""Tests for Dial-a-Story webhook handlers."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dial_a_story import (
    DialAStoryData,
    _CallHandler,
    handle_audio_webhook,
    handle_webhook,
)


@pytest.fixture
def runtime_data() -> DialAStoryData:
    """Create runtime data with defaults."""
    return DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key=None,
        story_length="medium",
        voice_preference="female",
    )


@pytest.fixture
def mock_request():
    """Create a mock aiohttp request."""
    request = AsyncMock()
    return request


async def test_webhook_call_initiated(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test webhook handles call.initiated event."""
    mock_request.json.return_value = {
        "data": {
            "event_type": "call.initiated",
            "payload": {
                "call_control_id": "ctrl_123",
                "from": "+15551234567",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_telnyx_api_call",
            new_callable=AsyncMock,
        ) as mock_api,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    assert "ctrl_123" in runtime_data.active_calls
    assert runtime_data.active_calls["ctrl_123"]["from"] == "+15551234567"
    mock_api.assert_called_once_with("/v2/calls/ctrl_123/actions/answer", {})


async def test_webhook_call_hangup(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test webhook handles call.hangup event and logs correctly."""
    runtime_data.active_calls["ctrl_456"] = {
        "from": "+15559876543",
        "story_count": 2,
        "state": "telling_story",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.hangup",
            "payload": {
                "call_control_id": "ctrl_456",
            },
        }
    }

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    assert "ctrl_456" not in runtime_data.active_calls


async def test_webhook_call_hangup_unknown_call(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test webhook handles hangup for unknown call gracefully."""
    mock_request.json.return_value = {
        "data": {
            "event_type": "call.hangup",
            "payload": {
                "call_control_id": "unknown_ctrl",
            },
        }
    }

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_webhook(hass, "dial_a_story", mock_request)

    assert response.status == 200


async def test_webhook_invalid_json(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test webhook handles invalid JSON gracefully."""
    mock_request.json.side_effect = ValueError("Invalid JSON")

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_webhook(hass, "dial_a_story", mock_request)

    # Should return an error response with appropriate status and payload
    assert response is not None
    assert response.status == 500
    body = json.loads(response.body)
    assert body["status"] == "error"


async def test_webhook_call_answered(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test webhook handles call.answered event."""
    runtime_data.active_calls["ctrl_789"] = {
        "from": "+15551111111",
        "story_count": 0,
        "state": "initiated",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.answered",
            "payload": {
                "call_control_id": "ctrl_789",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_speak_on_call",
            new_callable=AsyncMock,
        ) as mock_speak,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    assert runtime_data.active_calls["ctrl_789"]["state"] == "answered"
    mock_speak.assert_called_once()
    # Verify greeting text contains expected content
    greeting_text = mock_speak.call_args[0][1]
    assert "Dial-a-Story" in greeting_text


async def test_webhook_call_answered_unknown_call(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test call.answered for unknown call is ignored."""
    mock_request.json.return_value = {
        "data": {
            "event_type": "call.answered",
            "payload": {
                "call_control_id": "unknown_ctrl",
            },
        }
    }

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_webhook(hass, "dial_a_story", mock_request)

    assert response.status == 200


async def test_webhook_speak_ended_after_answered(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test speak.ended after answered triggers telling_story."""
    runtime_data.active_calls["ctrl_speak"] = {
        "from": "+15551111111",
        "story_count": 0,
        "state": "answered",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.speak.ended",
            "payload": {
                "call_control_id": "ctrl_speak",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_tell_story",
            new_callable=AsyncMock,
        ) as mock_tell,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    assert runtime_data.active_calls["ctrl_speak"]["state"] == "telling_story"
    mock_tell.assert_called_once_with("ctrl_speak")


async def test_webhook_speak_ended_after_telling_story(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test speak.ended after telling_story offers another."""
    runtime_data.active_calls["ctrl_offer"] = {
        "from": "+15551111111",
        "story_count": 0,
        "state": "telling_story",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.speak.ended",
            "payload": {
                "call_control_id": "ctrl_offer",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_offer_another_story",
            new_callable=AsyncMock,
        ) as mock_offer,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    assert runtime_data.active_calls["ctrl_offer"]["state"] == "offering_another"
    mock_offer.assert_called_once_with("ctrl_offer")


async def test_webhook_speak_ended_after_offering(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test speak.ended after offering_another says goodbye."""
    runtime_data.active_calls["ctrl_bye"] = {
        "from": "+15551111111",
        "story_count": 0,
        "state": "offering_another",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.speak.ended",
            "payload": {
                "call_control_id": "ctrl_bye",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_say_goodbye",
            new_callable=AsyncMock,
        ) as mock_goodbye,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    mock_goodbye.assert_called_once_with("ctrl_bye")


async def test_webhook_speak_ended_unknown_call(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test speak.ended for unknown call is ignored."""
    mock_request.json.return_value = {
        "data": {
            "event_type": "call.speak.ended",
            "payload": {
                "call_control_id": "unknown_ctrl",
            },
        }
    }

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_webhook(hass, "dial_a_story", mock_request)

    assert response.status == 200


async def test_webhook_playback_ended(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test playback.ended event is handled same as speak.ended."""
    runtime_data.active_calls["ctrl_pb"] = {
        "from": "+15551111111",
        "story_count": 0,
        "state": "answered",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.playback.ended",
            "payload": {
                "call_control_id": "ctrl_pb",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_tell_story",
            new_callable=AsyncMock,
        ) as mock_tell,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    mock_tell.assert_called_once()


async def test_webhook_gather_ended_press_1(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test gather.ended with digit 1 tells another story."""
    runtime_data.active_calls["ctrl_gather"] = {
        "from": "+15551111111",
        "story_count": 0,
        "state": "offering_another",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.gather.ended",
            "payload": {
                "call_control_id": "ctrl_gather",
                "digits": "1",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_speak_on_call",
            new_callable=AsyncMock,
        ) as mock_speak,
        patch.object(
            _CallHandler,
            "_tell_story",
            new_callable=AsyncMock,
        ) as mock_tell,
        patch("custom_components.dial_a_story.asyncio.sleep", new_callable=AsyncMock),
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    assert runtime_data.active_calls["ctrl_gather"]["story_count"] == 1
    mock_speak.assert_called_once()
    mock_tell.assert_called_once()


async def test_webhook_gather_ended_max_stories(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test gather.ended with 3 stories already says enough."""
    runtime_data.active_calls["ctrl_max"] = {
        "from": "+15551111111",
        "story_count": 2,
        "state": "offering_another",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.gather.ended",
            "payload": {
                "call_control_id": "ctrl_max",
                "digits": "1",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_speak_on_call",
            new_callable=AsyncMock,
        ) as mock_speak,
        patch.object(
            _CallHandler,
            "_hangup_call",
            new_callable=AsyncMock,
        ) as mock_hangup,
        patch("custom_components.dial_a_story.asyncio.sleep", new_callable=AsyncMock),
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    mock_speak.assert_called_once()
    assert "three wonderful stories" in mock_speak.call_args[0][1]
    mock_hangup.assert_called_once_with("ctrl_max")


async def test_webhook_gather_ended_no_digit(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test gather.ended with no digit says goodbye."""
    runtime_data.active_calls["ctrl_nodigit"] = {
        "from": "+15551111111",
        "story_count": 0,
        "state": "offering_another",
    }

    mock_request.json.return_value = {
        "data": {
            "event_type": "call.gather.ended",
            "payload": {
                "call_control_id": "ctrl_nodigit",
                "digits": "",
            },
        }
    }

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_say_goodbye",
            new_callable=AsyncMock,
        ) as mock_goodbye,
    ):
        await handle_webhook(hass, "dial_a_story", mock_request)

    mock_goodbye.assert_called_once_with("ctrl_nodigit")


async def test_webhook_gather_ended_unknown_call(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test gather.ended for unknown call is ignored."""
    mock_request.json.return_value = {
        "data": {
            "event_type": "call.gather.ended",
            "payload": {
                "call_control_id": "unknown_ctrl",
                "digits": "1",
            },
        }
    }

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_webhook(hass, "dial_a_story", mock_request)

    assert response.status == 200


async def test_webhook_unknown_event(
    hass: HomeAssistant, runtime_data: DialAStoryData, mock_request
) -> None:
    """Test webhook handles unknown event types gracefully."""
    mock_request.json.return_value = {
        "data": {
            "event_type": "call.some_unknown_event",
            "payload": {},
        }
    }

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_webhook(hass, "dial_a_story", mock_request)

    assert response.status == 200


async def test_telnyx_api_call_error_logging(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test Telnyx API call logs errors with lazy formatting."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    mock_response = AsyncMock()
    mock_response.status = 422
    mock_response.text.return_value = "Unprocessable Entity"
    mock_response.json.return_value = {"error": "bad request"}

    session = AsyncMock()
    session.post.return_value = mock_response

    with patch(
        "custom_components.dial_a_story.async_get_clientsession",
        return_value=session,
    ):
        result = await handler._telnyx_api_call(
            "/v2/calls/test/actions/speak", {"payload": "test"}
        )

    # Should still return response even on error
    assert result == {"error": "bad request"}


async def test_telnyx_api_call_exception(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test Telnyx API call handles exceptions with lazy formatting."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    session = AsyncMock()
    session.post.side_effect = OSError("Connection refused")

    with (
        patch(
            "custom_components.dial_a_story.async_get_clientsession",
            return_value=session,
        ),
        pytest.raises(OSError, match="Connection refused"),
    ):
        await handler._telnyx_api_call("/v2/calls/test/actions/speak", {})


async def test_telnyx_api_call_success(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test Telnyx API call succeeds with 200 status."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"result": "ok"}

    session = AsyncMock()
    session.post.return_value = mock_response

    with patch(
        "custom_components.dial_a_story.async_get_clientsession",
        return_value=session,
    ):
        result = await handler._telnyx_api_call(
            "/v2/calls/test/actions/speak", {"payload": "test"}
        )

    assert result == {"result": "ok"}


async def test_generate_story_ai_fallback_to_backup(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test story generation falls back to backup when AI task fails."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    with patch.object(
        handler,
        "_generate_story_ai_task",
        side_effect=RuntimeError("AI service unavailable"),
    ):
        story = await handler._generate_story()

    # Should return a backup story (all end with "Sweet dreams, Chloe!")
    assert "Sweet dreams, Chloe!" in story


async def test_generate_story_ai_task_success(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test AI task story generation succeeds."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    mock_call = AsyncMock(
        return_value={"data": "  A beautiful story about a bunny.  "}
    )
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        mock_call,
    ):
        story = await handler._generate_story_ai_task()
    assert story == "A beautiful story about a bunny."


async def test_generate_story_ai_task_empty_response(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test AI task raises ValueError on empty response."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    mock_call = AsyncMock(return_value={"data": ""})
    with (
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            mock_call,
        ),
        pytest.raises(ValueError, match="ai_task returned empty response"),
    ):
        await handler._generate_story_ai_task()


async def test_generate_story_ai_task_short_length(
    hass: HomeAssistant,
) -> None:
    """Test AI task uses correct word count for short stories."""
    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key=None,
        story_length="short",
        voice_preference="female",
    )

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    mock_call = AsyncMock(return_value={"data": "Short story."})
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        mock_call,
    ):
        story = await handler._generate_story_ai_task()
    assert story == "Short story."

    # Verify call used "200" for short
    call_args = mock_call.call_args
    instructions = call_args[0][2]["instructions"]
    assert "200-word" in instructions


async def test_generate_story_ai_task_long_length(
    hass: HomeAssistant,
) -> None:
    """Test AI task uses correct word count for long stories."""
    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key=None,
        story_length="long",
        voice_preference="female",
    )

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    mock_call = AsyncMock(return_value={"data": "Long story."})
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        mock_call,
    ):
        story = await handler._generate_story_ai_task()
    assert story == "Long story."

    # Verify call used "500" for long
    call_args = mock_call.call_args
    instructions = call_args[0][2]["instructions"]
    assert "500-word" in instructions


async def test_speak_elevenlabs_fallback_to_telnyx(
    hass: HomeAssistant,
) -> None:
    """Test TTS falls back to Telnyx when ElevenLabs fails."""
    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key="elevenlabs_key",
        story_length="medium",
        voice_preference="female",
    )

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    with (
        patch.object(
            handler,
            "_speak_elevenlabs",
            side_effect=RuntimeError("ElevenLabs API error"),
        ),
        patch.object(
            handler,
            "_telnyx_api_call",
            new_callable=AsyncMock,
        ) as mock_telnyx,
    ):
        await handler._speak_on_call("ctrl_test", "Hello world")

    # Should fall back to Telnyx TTS
    mock_telnyx.assert_called_once_with(
        "/v2/calls/ctrl_test/actions/speak",
        {
            "payload": "Hello world",
            "voice": "female",
            "language": "en-US",
        },
    )


async def test_speak_without_elevenlabs(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test TTS uses Telnyx directly when no ElevenLabs key."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    with patch.object(
        handler,
        "_telnyx_api_call",
        new_callable=AsyncMock,
    ) as mock_telnyx:
        await handler._speak_on_call("ctrl_direct", "Hello")

    mock_telnyx.assert_called_once_with(
        "/v2/calls/ctrl_direct/actions/speak",
        {
            "payload": "Hello",
            "voice": "female",
            "language": "en-US",
        },
    )


async def test_speak_elevenlabs_audio_playback(
    hass: HomeAssistant,
) -> None:
    """Test ElevenLabs TTS generates audio and plays via Telnyx."""
    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key="elevenlabs_key",
        story_length="medium",
        voice_preference="female",
    )

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    mock_el_response = AsyncMock()
    mock_el_response.status = 200
    mock_el_response.read.return_value = b"fake_audio_bytes"

    session = AsyncMock()
    session.post.return_value = mock_el_response

    with (
        patch(
            "custom_components.dial_a_story.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.dial_a_story.get_url",
            return_value="https://ha.example.com",
        ),
        patch.object(
            handler,
            "_telnyx_api_call",
            new_callable=AsyncMock,
        ) as mock_telnyx,
    ):
        await handler._speak_elevenlabs("ctrl_audio", "Once upon a time")

    # Should have cached audio
    assert len(data.audio_cache) == 1

    # Should have called Telnyx playback
    mock_telnyx.assert_called_once()
    call_args = mock_telnyx.call_args
    assert "playback_start" in call_args[0][0]
    assert "audio_url" in call_args[0][1]


async def test_speak_elevenlabs_api_error(
    hass: HomeAssistant,
) -> None:
    """Test ElevenLabs TTS raises HomeAssistantError on API failure."""
    from homeassistant.exceptions import HomeAssistantError

    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key="elevenlabs_key",
        story_length="medium",
        voice_preference="male",
    )

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    mock_el_response = AsyncMock()
    mock_el_response.status = 500
    mock_el_response.text.return_value = "Internal Server Error"

    session = AsyncMock()
    session.post.return_value = mock_el_response

    with (
        patch(
            "custom_components.dial_a_story.async_get_clientsession",
            return_value=session,
        ),
        pytest.raises(HomeAssistantError),
    ):
        await handler._speak_elevenlabs("ctrl_err", "Hello")


async def test_speak_elevenlabs_uses_male_voice(
    hass: HomeAssistant,
) -> None:
    """Test ElevenLabs uses male voice when configured."""
    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key="elevenlabs_key",
        story_length="medium",
        voice_preference="male",
    )

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    mock_el_response = AsyncMock()
    mock_el_response.status = 200
    mock_el_response.read.return_value = b"fake_audio"

    session = AsyncMock()
    session.post.return_value = mock_el_response

    with (
        patch(
            "custom_components.dial_a_story.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.dial_a_story.get_url",
            return_value="https://ha.example.com",
        ),
        patch.object(
            handler,
            "_telnyx_api_call",
            new_callable=AsyncMock,
        ),
    ):
        await handler._speak_elevenlabs("ctrl_male", "Story text")

    # Check the ElevenLabs API was called with male voice ID
    el_call = session.post.call_args
    assert "pNInz6obpgDQGcFmaJgB" in el_call[0][0]


async def test_speak_elevenlabs_url_fallback(
    hass: HomeAssistant,
) -> None:
    """Test ElevenLabs URL falls back when cloud URL unavailable."""
    from homeassistant.helpers.network import NoURLAvailableError

    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key="elevenlabs_key",
        story_length="medium",
        voice_preference="female",
    )

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    mock_el_response = AsyncMock()
    mock_el_response.status = 200
    mock_el_response.read.return_value = b"fake_audio"

    session = AsyncMock()
    session.post.return_value = mock_el_response

    call_count = 0

    def get_url_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise NoURLAvailableError
        return "https://fallback.example.com"

    with (
        patch(
            "custom_components.dial_a_story.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.dial_a_story.get_url",
            side_effect=get_url_side_effect,
        ),
        patch.object(
            handler,
            "_telnyx_api_call",
            new_callable=AsyncMock,
        ) as mock_telnyx,
    ):
        await handler._speak_elevenlabs("ctrl_fb", "Story")

    # Verify fallback URL was used
    playback_args = mock_telnyx.call_args[0][1]
    assert "fallback.example.com" in playback_args["audio_url"]


async def test_speak_elevenlabs_cache_cleanup(
    hass: HomeAssistant,
) -> None:
    """Test audio cache is cleaned when > 10 entries."""
    data = DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key="elevenlabs_key",
        story_length="medium",
        voice_preference="female",
    )

    # Pre-populate cache with 10 entries
    for i in range(10):
        data.audio_cache[f"old_audio_{i}"] = b"old"

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=data,
    ):
        handler = _CallHandler(hass)

    mock_el_response = AsyncMock()
    mock_el_response.status = 200
    mock_el_response.read.return_value = b"new_audio"

    session = AsyncMock()
    session.post.return_value = mock_el_response

    with (
        patch(
            "custom_components.dial_a_story.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.dial_a_story.get_url",
            return_value="https://ha.example.com",
        ),
        patch.object(
            handler,
            "_telnyx_api_call",
            new_callable=AsyncMock,
        ),
    ):
        await handler._speak_elevenlabs("ctrl_cache", "New story")

    # Should keep only last 10 entries (cleaned up old)
    assert len(data.audio_cache) == 10


async def test_audio_webhook_serves_cached_audio(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test audio webhook serves cached audio."""
    runtime_data.audio_cache["test_audio_id"] = b"audio_content"

    mock_request = MagicMock()
    mock_request.query = {"id": "test_audio_id"}

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_audio_webhook(hass, "dial_a_story_audio", mock_request)

    assert response.status == 200
    assert response.body == b"audio_content"
    assert response.content_type == "audio/mpeg"


async def test_audio_webhook_missing_id(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test audio webhook returns 404 for missing id."""
    mock_request = MagicMock()
    mock_request.query = {}

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_audio_webhook(hass, "dial_a_story_audio", mock_request)

    assert response.status == 404


async def test_audio_webhook_unknown_id(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test audio webhook returns 404 for unknown audio id."""
    mock_request = MagicMock()
    mock_request.query = {"id": "nonexistent"}

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        response = await handle_audio_webhook(hass, "dial_a_story_audio", mock_request)

    assert response.status == 404


async def test_offer_another_story(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test offering another story sends gather request."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    with patch.object(
        handler,
        "_telnyx_api_call",
        new_callable=AsyncMock,
    ) as mock_api:
        await handler._offer_another_story("ctrl_offer")

    mock_api.assert_called_once()
    call_args = mock_api.call_args
    assert "gather" in call_args[0][0]
    assert call_args[0][1]["timeout_millis"] == 10000


async def test_say_goodbye(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test saying goodbye speaks and hangs up."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    with (
        patch.object(
            handler,
            "_speak_on_call",
            new_callable=AsyncMock,
        ) as mock_speak,
        patch.object(
            handler,
            "_hangup_call",
            new_callable=AsyncMock,
        ) as mock_hangup,
        patch("custom_components.dial_a_story.asyncio.sleep", new_callable=AsyncMock),
    ):
        await handler._say_goodbye("ctrl_bye")

    mock_speak.assert_called_once()
    goodbye_text = mock_speak.call_args[0][1]
    assert "Sweet dreams" in goodbye_text
    mock_hangup.assert_called_once_with("ctrl_bye")


async def test_hangup_call(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test hangup sends hangup API call."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    with patch.object(
        handler,
        "_telnyx_api_call",
        new_callable=AsyncMock,
    ) as mock_api:
        await handler._hangup_call("ctrl_hangup")

    mock_api.assert_called_once_with(
        "/v2/calls/ctrl_hangup/actions/hangup", {}
    )


async def test_tell_story(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test tell story generates and speaks."""
    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)

    with (
        patch.object(
            handler,
            "_generate_story",
            return_value="A lovely story.",
        ),
        patch.object(
            handler,
            "_speak_on_call",
            new_callable=AsyncMock,
        ) as mock_speak,
    ):
        await handler._tell_story("ctrl_tell")

    mock_speak.assert_called_once_with("ctrl_tell", "A lovely story.", pause=500)
