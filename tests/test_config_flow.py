"""Tests for Dial-a-Story config flow."""

from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

# Ensure config_flow module is imported so patch targets resolve
import custom_components.dial_a_story.config_flow  # noqa: F401
from custom_components.dial_a_story.const import (
    CONF_ELEVENLABS_API_KEY,
    CONF_STORY_LENGTH,
    CONF_TELNYX_API_KEY,
    CONF_VOICE_PREFERENCE,
    DOMAIN,
)

PATCH_TARGET = "custom_components.dial_a_story.config_flow.async_get_clientsession"


@pytest.fixture
def mock_telnyx_valid():
    """Mock a valid Telnyx API response."""
    with patch(PATCH_TARGET) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        response = AsyncMock()
        response.status = 200
        session.get.return_value = response
        yield session


@pytest.fixture
def mock_telnyx_invalid_auth():
    """Mock an invalid auth Telnyx API response."""
    with patch(PATCH_TARGET) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        response = AsyncMock()
        response.status = 401
        session.get.return_value = response
        yield session


@pytest.fixture
def mock_telnyx_forbidden():
    """Mock a forbidden Telnyx API response."""
    with patch(PATCH_TARGET) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        response = AsyncMock()
        response.status = 403
        session.get.return_value = response
        yield session


@pytest.fixture
def mock_telnyx_connection_error():
    """Mock a connection error to Telnyx API."""
    with patch(PATCH_TARGET) as mock_get_session:
        session = AsyncMock()
        mock_get_session.return_value = session
        session.get.side_effect = Exception("Connection refused")
        yield session


@pytest.fixture
def mock_setup_entry():
    """Mock async_setup_entry."""
    with patch(
        "custom_components.dial_a_story.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


def _create_config_entry(hass: HomeAssistant):
    """Create and add a config entry for reauth/reconfigure tests."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Dial-a-Story",
        data={
            CONF_TELNYX_API_KEY: "original_key",
            CONF_ELEVENLABS_API_KEY: "",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
        source=config_entries.SOURCE_USER,
        unique_id=DOMAIN,
        discovery_keys=MappingProxyType({}),
        options=None,
        subentries_data=None,
    )
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


async def test_config_flow_success(
    hass: HomeAssistant, mock_telnyx_valid, mock_setup_entry
) -> None:
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "test_key_123",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dial-a-Story"
    assert result["data"][CONF_TELNYX_API_KEY] == "test_key_123"
    assert result["data"][CONF_STORY_LENGTH] == "medium"
    assert result["data"][CONF_VOICE_PREFERENCE] == "female"
    assert result["data"][CONF_ELEVENLABS_API_KEY] == ""


async def test_config_flow_invalid_auth(
    hass: HomeAssistant, mock_telnyx_invalid_auth
) -> None:
    """Test config flow with invalid API key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "bad_key",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_forbidden(
    hass: HomeAssistant, mock_telnyx_forbidden
) -> None:
    """Test config flow with forbidden API key (403)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "bad_key",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_connection_error(
    hass: HomeAssistant, mock_telnyx_connection_error
) -> None:
    """Test config flow with connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "test_key",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_duplicate_entry(
    hass: HomeAssistant, mock_telnyx_valid, mock_setup_entry
) -> None:
    """Test config flow aborts on duplicate entry."""
    # Create first entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "test_key_123",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # Try to create second entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "another_key",
            CONF_STORY_LENGTH: "short",
            CONF_VOICE_PREFERENCE: "male",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_config_flow_with_elevenlabs(
    hass: HomeAssistant, mock_telnyx_valid, mock_setup_entry
) -> None:
    """Test config flow with optional ElevenLabs key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "test_key_123",
            CONF_ELEVENLABS_API_KEY: "elevenlabs_key",
            CONF_STORY_LENGTH: "long",
            CONF_VOICE_PREFERENCE: "male",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ELEVENLABS_API_KEY] == "elevenlabs_key"
    assert result["data"][CONF_STORY_LENGTH] == "long"
    assert result["data"][CONF_VOICE_PREFERENCE] == "male"


# --- Reauthentication flow tests ---


async def test_reauth_flow_success(
    hass: HomeAssistant, mock_telnyx_valid, mock_setup_entry
) -> None:
    """Test successful reauthentication flow."""
    entry = _create_config_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "new_valid_key",
            CONF_ELEVENLABS_API_KEY: "new_elevenlabs_key",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_flow_invalid_auth(
    hass: HomeAssistant, mock_telnyx_invalid_auth, mock_setup_entry
) -> None:
    """Test reauthentication flow with invalid credentials."""
    entry = _create_config_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "bad_key",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_flow_connection_error(
    hass: HomeAssistant, mock_telnyx_connection_error, mock_setup_entry
) -> None:
    """Test reauthentication flow with connection error."""
    entry = _create_config_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "some_key",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# --- Reconfiguration flow tests ---


async def test_reconfigure_flow_success(
    hass: HomeAssistant, mock_telnyx_valid, mock_setup_entry
) -> None:
    """Test successful reconfiguration flow."""
    entry = _create_config_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "updated_key",
            CONF_ELEVENLABS_API_KEY: "updated_el_key",
            CONF_STORY_LENGTH: "long",
            CONF_VOICE_PREFERENCE: "male",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_flow_invalid_auth(
    hass: HomeAssistant, mock_telnyx_invalid_auth, mock_setup_entry
) -> None:
    """Test reconfiguration flow with invalid credentials."""
    entry = _create_config_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "bad_key",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_flow_connection_error(
    hass: HomeAssistant, mock_telnyx_connection_error, mock_setup_entry
) -> None:
    """Test reconfiguration flow with connection error."""
    entry = _create_config_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TELNYX_API_KEY: "some_key",
            CONF_STORY_LENGTH: "medium",
            CONF_VOICE_PREFERENCE: "female",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
