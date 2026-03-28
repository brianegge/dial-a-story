"""Diagnostics support for Dial-a-Story."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ELEVENLABS_API_KEY, CONF_TELNYX_API_KEY

if TYPE_CHECKING:
    from . import DialAStoryData

    DialAStoryConfigEntry = ConfigEntry[DialAStoryData]

TO_REDACT = {CONF_TELNYX_API_KEY, CONF_ELEVENLABS_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: DialAStoryConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data

    return {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "runtime": {
            "story_length": data.story_length,
            "voice_preference": data.voice_preference,
            "has_elevenlabs": data.elevenlabs_api_key is not None,
            "queued_story": data.queued_story is not None,
            "active_calls": len(data.active_calls),
            "audio_cache_size": len(data.audio_cache),
        },
    }
