"""Tests for Dial-a-Story diagnostics."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dial_a_story import DialAStoryData
from custom_components.dial_a_story.const import (
    CONF_ELEVENLABS_API_KEY,
    CONF_STORY_LENGTH,
    CONF_TELNYX_API_KEY,
    CONF_VOICE_PREFERENCE,
    DOMAIN,
)
from custom_components.dial_a_story.diagnostics import (
    async_get_config_entry_diagnostics,
)


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry with runtime data."""
    entry = AsyncMock()
    entry.entry_id = "test_entry"
    entry.domain = DOMAIN
    entry.data = {
        CONF_TELNYX_API_KEY: "super_secret_telnyx_key",
        CONF_ELEVENLABS_API_KEY: "super_secret_elevenlabs_key",
        CONF_STORY_LENGTH: "medium",
        CONF_VOICE_PREFERENCE: "female",
    }
    entry.runtime_data = DialAStoryData(
        telnyx_api_key="super_secret_telnyx_key",
        elevenlabs_api_key="super_secret_elevenlabs_key",
        story_length="medium",
        voice_preference="female",
    )
    return entry


async def test_diagnostics_redacts_api_keys(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that diagnostics redacts API keys."""
    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # API keys must be redacted
    assert diag["config_entry"][CONF_TELNYX_API_KEY] == "**REDACTED**"
    assert diag["config_entry"][CONF_ELEVENLABS_API_KEY] == "**REDACTED**"

    # Non-sensitive config should be present
    assert diag["config_entry"][CONF_STORY_LENGTH] == "medium"
    assert diag["config_entry"][CONF_VOICE_PREFERENCE] == "female"


async def test_diagnostics_runtime_data(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that diagnostics includes runtime info."""
    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    runtime = diag["runtime"]
    assert runtime["story_length"] == "medium"
    assert runtime["voice_preference"] == "female"
    assert runtime["has_elevenlabs"] is True
    assert runtime["queued_story"] is False
    assert runtime["active_calls"] == 0
    assert runtime["audio_cache_size"] == 0


async def test_diagnostics_with_active_state(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test diagnostics reflects active calls and queued story."""
    mock_config_entry.runtime_data.queued_story = "A test story"
    mock_config_entry.runtime_data.active_calls["call_1"] = {"from": "+1234567890"}
    mock_config_entry.runtime_data.audio_cache["audio_1"] = b"fake_audio"

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    runtime = diag["runtime"]
    assert runtime["queued_story"] is True
    assert runtime["active_calls"] == 1
    assert runtime["audio_cache_size"] == 1


async def test_diagnostics_without_elevenlabs(hass: HomeAssistant) -> None:
    """Test diagnostics when ElevenLabs is not configured."""
    entry = AsyncMock()
    entry.entry_id = "test_entry"
    entry.domain = DOMAIN
    entry.data = {
        CONF_TELNYX_API_KEY: "telnyx_key",
        CONF_ELEVENLABS_API_KEY: "",
        CONF_STORY_LENGTH: "short",
        CONF_VOICE_PREFERENCE: "male",
    }
    entry.runtime_data = DialAStoryData(
        telnyx_api_key="telnyx_key",
        elevenlabs_api_key=None,
        story_length="short",
        voice_preference="male",
    )

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["runtime"]["has_elevenlabs"] is False
    assert diag["runtime"]["story_length"] == "short"
    assert diag["runtime"]["voice_preference"] == "male"
