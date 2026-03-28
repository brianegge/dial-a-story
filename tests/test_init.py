"""Tests for Dial-a-Story integration setup and unload."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from custom_components.dial_a_story import (
    _get_runtime_data,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.dial_a_story.const import (
    CONF_ELEVENLABS_API_KEY,
    CONF_STORY_LENGTH,
    CONF_TELNYX_API_KEY,
    CONF_VOICE_PREFERENCE,
    DOMAIN,
    SERVICE_CLEAR_STORY,
    SERVICE_SET_STORY,
    WEBHOOK_ID,
    WEBHOOK_ID_AUDIO,
)


def _make_entry(hass):
    """Create a mock config entry."""
    entry = AsyncMock()
    entry.entry_id = "test_entry"
    entry.domain = DOMAIN
    entry.data = {
        CONF_TELNYX_API_KEY: "test_telnyx_key",
        CONF_ELEVENLABS_API_KEY: "test_elevenlabs_key",
        CONF_STORY_LENGTH: "medium",
        CONF_VOICE_PREFERENCE: "female",
    }
    # Give it a real runtime_data attribute that can be set
    entry.runtime_data = None
    return entry


@pytest.fixture
def mock_telnyx_valid():
    """Mock a valid Telnyx API response during setup."""
    with patch(
        "custom_components.dial_a_story.async_get_clientsession"
    ) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        response = AsyncMock()
        response.status = 200
        session.get.return_value = response
        yield session


@pytest.fixture
def mock_telnyx_invalid():
    """Mock an invalid auth Telnyx API response during setup."""
    with patch(
        "custom_components.dial_a_story.async_get_clientsession"
    ) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        response = AsyncMock()
        response.status = 401
        session.get.return_value = response
        yield session


@pytest.fixture
def mock_telnyx_forbidden():
    """Mock a forbidden Telnyx API response during setup (403)."""
    with patch(
        "custom_components.dial_a_story.async_get_clientsession"
    ) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        response = AsyncMock()
        response.status = 403
        session.get.return_value = response
        yield session


@pytest.fixture
def mock_telnyx_error():
    """Mock a connection error to Telnyx during setup."""
    with patch(
        "custom_components.dial_a_story.async_get_clientsession"
    ) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        session.get.side_effect = OSError("Connection refused")
        yield session


async def test_setup_entry_success(hass: HomeAssistant, mock_telnyx_valid) -> None:
    """Test successful setup creates runtime data and registers webhooks."""
    entry = _make_entry(hass)

    result = await async_setup_entry(hass, entry)

    assert result is True
    assert entry.runtime_data is not None
    assert entry.runtime_data.telnyx_api_key == "test_telnyx_key"
    assert entry.runtime_data.elevenlabs_api_key == "test_elevenlabs_key"
    assert entry.runtime_data.story_length == "medium"
    assert entry.runtime_data.voice_preference == "female"

    # Services should be registered
    assert hass.services.has_service(DOMAIN, SERVICE_SET_STORY)
    assert hass.services.has_service(DOMAIN, SERVICE_CLEAR_STORY)


async def test_setup_entry_invalid_auth(
    hass: HomeAssistant, mock_telnyx_invalid
) -> None:
    """Test setup raises ConfigEntryNotReady on invalid API key."""
    entry = _make_entry(hass)

    with pytest.raises(ConfigEntryNotReady, match="Invalid Telnyx API key"):
        await async_setup_entry(hass, entry)


async def test_setup_entry_forbidden(
    hass: HomeAssistant, mock_telnyx_forbidden
) -> None:
    """Test setup raises ConfigEntryNotReady on forbidden API key (403)."""
    entry = _make_entry(hass)

    with pytest.raises(ConfigEntryNotReady, match="Invalid Telnyx API key"):
        await async_setup_entry(hass, entry)


async def test_setup_entry_connection_error(
    hass: HomeAssistant, mock_telnyx_error
) -> None:
    """Test setup raises ConfigEntryNotReady on connection error."""
    entry = _make_entry(hass)

    with pytest.raises(ConfigEntryNotReady, match="Error connecting to Telnyx API"):
        await async_setup_entry(hass, entry)


async def test_setup_without_elevenlabs(
    hass: HomeAssistant, mock_telnyx_valid
) -> None:
    """Test setup works without ElevenLabs API key."""
    entry = _make_entry(hass)
    entry.data = {
        CONF_TELNYX_API_KEY: "test_telnyx_key",
        CONF_STORY_LENGTH: "short",
        CONF_VOICE_PREFERENCE: "male",
    }

    result = await async_setup_entry(hass, entry)

    assert result is True
    assert entry.runtime_data.elevenlabs_api_key is None
    assert entry.runtime_data.story_length == "short"
    assert entry.runtime_data.voice_preference == "male"


async def test_setup_with_empty_elevenlabs(
    hass: HomeAssistant, mock_telnyx_valid
) -> None:
    """Test setup treats empty ElevenLabs key as None."""
    entry = _make_entry(hass)
    entry.data = {
        CONF_TELNYX_API_KEY: "test_telnyx_key",
        CONF_ELEVENLABS_API_KEY: "",
        CONF_STORY_LENGTH: "medium",
        CONF_VOICE_PREFERENCE: "female",
    }

    result = await async_setup_entry(hass, entry)

    assert result is True
    assert entry.runtime_data.elevenlabs_api_key is None


async def test_setup_defaults(hass: HomeAssistant, mock_telnyx_valid) -> None:
    """Test setup uses defaults when optional fields are missing."""
    entry = _make_entry(hass)
    entry.data = {
        CONF_TELNYX_API_KEY: "test_telnyx_key",
    }

    result = await async_setup_entry(hass, entry)

    assert result is True
    assert entry.runtime_data.story_length == "medium"
    assert entry.runtime_data.voice_preference == "female"
    assert entry.runtime_data.elevenlabs_api_key is None


async def test_unload_entry(hass: HomeAssistant, mock_telnyx_valid) -> None:
    """Test unload removes webhooks and services."""
    entry = _make_entry(hass)

    await async_setup_entry(hass, entry)

    # Verify services exist before unload
    assert hass.services.has_service(DOMAIN, SERVICE_SET_STORY)
    assert hass.services.has_service(DOMAIN, SERVICE_CLEAR_STORY)

    with patch(
        "custom_components.dial_a_story.webhook.async_unregister"
    ) as mock_unregister:
        result = await async_unload_entry(hass, entry)

    assert result is True

    # Webhooks should be unregistered
    assert mock_unregister.call_count == 2
    mock_unregister.assert_any_call(hass, WEBHOOK_ID)
    mock_unregister.assert_any_call(hass, WEBHOOK_ID_AUDIO)

    # Services should be removed after unload
    assert not hass.services.has_service(DOMAIN, SERVICE_SET_STORY)
    assert not hass.services.has_service(DOMAIN, SERVICE_CLEAR_STORY)


async def test_set_story_service(hass: HomeAssistant, mock_telnyx_valid) -> None:
    """Test set_story service queues a story."""
    entry = _make_entry(hass)
    await async_setup_entry(hass, entry)

    assert entry.runtime_data.queued_story is None

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_STORY,
        {"story": "A magical tale about a friendly dragon."},
        blocking=True,
    )

    assert entry.runtime_data.queued_story == "A magical tale about a friendly dragon."


async def test_set_story_service_strips_whitespace(
    hass: HomeAssistant, mock_telnyx_valid
) -> None:
    """Test set_story service strips leading/trailing whitespace."""
    entry = _make_entry(hass)
    await async_setup_entry(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_STORY,
        {"story": "  A story with whitespace.  "},
        blocking=True,
    )

    assert entry.runtime_data.queued_story == "A story with whitespace."


async def test_set_story_service_empty_raises(
    hass: HomeAssistant, mock_telnyx_valid
) -> None:
    """Test set_story service raises on empty story."""
    entry = _make_entry(hass)
    await async_setup_entry(hass, entry)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_STORY,
            {"story": "   "},
            blocking=True,
        )


async def test_clear_story_service(hass: HomeAssistant, mock_telnyx_valid) -> None:
    """Test clear_story service removes queued story."""
    entry = _make_entry(hass)
    await async_setup_entry(hass, entry)

    entry.runtime_data.queued_story = "Some story"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAR_STORY,
        {},
        blocking=True,
    )

    assert entry.runtime_data.queued_story is None


async def test_get_runtime_data_no_entries(hass: HomeAssistant) -> None:
    """Test _get_runtime_data raises when no entries configured."""
    with pytest.raises(RuntimeError, match="not configured"):
        _get_runtime_data(hass)
