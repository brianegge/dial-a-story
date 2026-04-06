"""
Dial-a-Story: AI Bedtime Stories Hotline for Toddlers
Home Assistant Custom Component

HACS-compatible integration for creating a phone number your kids can call
to hear AI-generated bedtime stories.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    CONF_ELEVENLABS_API_KEY,
    CONF_STORY_LENGTH,
    CONF_TELNYX_API_KEY,
    CONF_VOICE_PREFERENCE,
    DOMAIN,
    ELEVENLABS_VOICES,
    SERVICE_CLEAR_STORY,
    SERVICE_SET_STORY,
    WEBHOOK_ID,
    WEBHOOK_ID_AUDIO,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CONTENT_TYPE_JSON = "application/json"

# Story themes appropriate for 2-5 year olds
STORY_THEMES = [
    "Chloe and a friendly dinosaur who loves to share toys",
    "Chloe riding a magical train that visits the moon and stars",
    "Chloe and a brave little bunny exploring a beautiful garden",
    "Chloe meeting a silly elephant who can't stop sneezing bubbles",
    "Chloe and a kind robot who helps animals find their way home",
    "Chloe and a curious kitten on their first adventure outside",
    "Chloe and a gentle whale who sings lullabies to fish",
    "Chloe and a happy cloud that makes rainbow rain",
    "Chloe and a sleepy teddy bear finding the perfect bedtime",
    "Chloe and a tiny firefly making friends in the forest",
]

# Backup stories in case LLM is unavailable
BACKUP_STORIES = [
    """Once upon a time, Chloe looked up at the sky and saw the moon. 'Hello, moon!'
    said Chloe. The moon smiled down at her. 'Hello, Chloe! I have the most important
    job. I watch over you while you sleep and keep you safe with my gentle light.'
    Chloe smiled and waved. That night, the moon shone brightly and sang a soft lullaby
    just for Chloe. And Chloe slept so peacefully. Sweet dreams, Chloe!""",
    """In a cozy garden, Chloe met a little bunny named Benny. 'Want to hop with me?'
    asked Benny. Chloe and Benny hopped and played together. When it got dark, they
    heard a tiny voice - it was a little firefly! 'I'm scared of the dark,' the firefly
    said. Chloe held the firefly's little hand. 'Don't be scared! We're here!' said
    Chloe. Together they weren't scared anymore. Chloe, Benny, and the firefly became
    best friends. Sweet dreams, Chloe!""",
    """There was once a kind little cloud named Fluffy. One day, Fluffy floated over
    Chloe's house. 'Hi Fluffy!' said Chloe. Fluffy wanted to help the flowers grow,
    so she made the gentlest, softest rain. The flowers danced and Chloe danced too!
    Then Fluffy made a beautiful rainbow just for Chloe! All the animals came out to
    see it. 'Thank you, Fluffy!' said Chloe. And Fluffy smiled and floated happily
    in the sky. Sweet dreams, Chloe!""",
]


@dataclass
class DialAStoryData:
    """Runtime data for Dial-a-Story."""

    telnyx_api_key: str
    elevenlabs_api_key: str | None
    story_length: str
    voice_preference: str
    queued_story: str | None = None
    active_calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    audio_cache: dict[str, bytes] = field(default_factory=dict)


if TYPE_CHECKING:
    DialAStoryConfigEntry = ConfigEntry[DialAStoryData]


async def async_setup_entry(hass: HomeAssistant, entry: DialAStoryConfigEntry) -> bool:
    """Set up Dial-a-Story from a config entry."""
    telnyx_api_key: str = entry.data[CONF_TELNYX_API_KEY]

    # test-before-setup: validate Telnyx API key
    session = async_get_clientsession(hass)
    try:
        response = await session.get(
            "https://api.telnyx.com/v2/phone_numbers?page[size]=1",
            headers={
                "Authorization": f"Bearer {telnyx_api_key}",
                "Content-Type": CONTENT_TYPE_JSON,
            },
        )
        if response.status in (401, 403):
            raise ConfigEntryNotReady("Invalid Telnyx API key")
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(f"Error connecting to Telnyx API: {err}") from err

    elevenlabs_key: str | None = entry.data.get(CONF_ELEVENLABS_API_KEY) or None

    entry.runtime_data = DialAStoryData(
        telnyx_api_key=telnyx_api_key,
        elevenlabs_api_key=elevenlabs_key,
        story_length=str(entry.data.get(CONF_STORY_LENGTH, "medium")),
        voice_preference=str(entry.data.get(CONF_VOICE_PREFERENCE, "female")),
    )

    webhook.async_register(
        hass,
        DOMAIN,
        "Dial-a-Story",
        WEBHOOK_ID,
        handle_webhook,
        allowed_methods=["POST"],
        local_only=False,
    )

    webhook.async_register(
        hass,
        DOMAIN,
        "Dial-a-Story Audio",
        WEBHOOK_ID_AUDIO,
        handle_audio_webhook,
        allowed_methods=["GET"],
        local_only=False,
    )

    async def handle_set_story(call: ServiceCall) -> None:
        """Handle set_story service call."""
        story_text: str = call.data["story"]
        if not story_text or not story_text.strip():
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="story_text_empty",
            )
        entry.runtime_data.queued_story = story_text.strip()
        _LOGGER.info("Story queued for next call (%d chars)", len(story_text))

    async def handle_clear_story(call: ServiceCall) -> None:
        """Handle clear_story service call."""
        entry.runtime_data.queued_story = None
        _LOGGER.info("Queued story cleared")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_STORY,
        handle_set_story,
        schema=vol.Schema({vol.Required("story"): cv.string}),
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_STORY, handle_clear_story)

    _LOGGER.info("Dial-a-Story initialized successfully")
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: DialAStoryConfigEntry,
) -> bool:
    """Unload a Dial-a-Story config entry."""
    webhook.async_unregister(hass, WEBHOOK_ID)
    webhook.async_unregister(hass, WEBHOOK_ID_AUDIO)
    hass.services.async_remove(DOMAIN, SERVICE_SET_STORY)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAR_STORY)
    return True


def _get_runtime_data(hass: HomeAssistant) -> DialAStoryData:
    """Get runtime data from the first config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise RuntimeError("Dial-a-Story is not configured")
    data: DialAStoryData = entries[0].runtime_data
    return data


async def handle_audio_webhook(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    """Serve cached audio files to Telnyx."""
    audio_id = request.query.get("id")
    data = _get_runtime_data(hass)
    if not audio_id or audio_id not in data.audio_cache:
        return web.Response(status=404)

    audio_bytes = data.audio_cache[audio_id]
    return web.Response(
        body=audio_bytes,
        content_type="audio/mpeg",
        headers={"Content-Length": str(len(audio_bytes))},
    )


async def handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    """Handle incoming webhook from Telnyx."""
    try:
        data = await request.json()
        event_type: str = data.get("data", {}).get("event_type", "")
        payload: dict[str, Any] = data.get("data", {}).get("payload", {})

        _LOGGER.info("Received Telnyx event: %s", event_type)

        handler = _CallHandler(hass)

        if event_type == "call.initiated":
            await handler.handle_call_initiated(payload)
        elif event_type == "call.answered":
            await handler.handle_call_answered(payload)
        elif event_type in ("call.speak.ended", "call.playback.ended"):
            await handler.handle_speak_ended(payload)
        elif event_type == "call.gather.ended":
            await handler.handle_gather_ended(payload)
        elif event_type == "call.hangup":
            await handler.handle_call_hangup(payload)

        return web.json_response({"status": "ok"})

    except Exception as e:
        _LOGGER.error("Error handling webhook: %s", e, exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)}, status=500
        )


class _CallHandler:
    """Handle Telnyx call events."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._data = _get_runtime_data(hass)

    async def handle_call_initiated(self, payload: dict[str, Any]) -> None:
        """Handle when a new call comes in."""
        call_control_id: str = str(payload.get("call_control_id", ""))
        from_number = payload.get("from")

        _LOGGER.info(
            "New call from %s, control_id: %s", from_number, call_control_id
        )

        self._data.active_calls[call_control_id] = {
            "from": from_number,
            "story_count": 0,
            "state": "initiated",
        }

        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/answer", {}
        )

    async def handle_call_answered(self, payload: dict[str, Any]) -> None:
        """Handle when call is answered - play greeting."""
        call_control_id: str = str(payload.get("call_control_id", ""))

        call_state = self._data.active_calls.get(call_control_id)
        if not call_state:
            return

        call_state["state"] = "answered"

        greeting = (
            "Hello! Welcome to Dial-a-Story, your magical story friend! "
            "I'm so happy you called. Let me tell you a wonderful bedtime story!"
        )

        await self._speak_on_call(call_control_id, greeting)

    async def handle_speak_ended(self, payload: dict[str, Any]) -> None:
        """Handle when TTS finishes speaking."""
        call_control_id: str = str(payload.get("call_control_id", ""))

        call_state = self._data.active_calls.get(call_control_id)
        if not call_state:
            return

        current_state = call_state.get("state")

        if current_state == "answered":
            call_state["state"] = "telling_story"
            await self._tell_story(call_control_id)

        elif current_state == "telling_story":
            call_state["state"] = "offering_another"
            await self._offer_another_story(call_control_id)

        elif current_state == "offering_another":
            await self._say_goodbye(call_control_id)

    async def handle_gather_ended(self, payload: dict[str, Any]) -> None:
        """Handle DTMF input (key press) from caller."""
        call_control_id: str = str(payload.get("call_control_id", ""))
        digits: str = str(payload.get("digits", ""))

        call_state = self._data.active_calls.get(call_control_id)
        if not call_state:
            return

        if call_state.get("state") == "offering_another" and digits == "1":
            call_state["state"] = "telling_story"
            call_state["story_count"] += 1

            if call_state["story_count"] >= 3:
                await self._speak_on_call(
                    call_control_id,
                    "You've had three wonderful stories tonight! "
                    "Time to rest now. Sweet dreams!",
                )
                await asyncio.sleep(3)
                await self._hangup_call(call_control_id)
            else:
                await self._speak_on_call(
                    call_control_id,
                    "Wonderful! Here's another story for you!",
                )
                await asyncio.sleep(1)
                await self._tell_story(call_control_id)
        else:
            await self._say_goodbye(call_control_id)

    async def handle_call_hangup(self, payload: dict[str, Any]) -> None:
        """Handle call ending."""
        call_control_id: str = str(payload.get("call_control_id", ""))

        if call_control_id in self._data.active_calls:
            call_info = self._data.active_calls[call_control_id]
            _LOGGER.info(
                "Call ended from %s, told %d stories",
                call_info.get("from"),
                call_info.get("story_count", 0),
            )
            del self._data.active_calls[call_control_id]

    async def _tell_story(self, call_control_id: str) -> None:
        """Generate and tell a bedtime story."""
        story = await self._generate_story()
        await self._speak_on_call(call_control_id, story, pause=500)

    async def _generate_story(self) -> str:
        """Return queued story if set, otherwise generate via AI or backup."""
        if self._data.queued_story:
            story = self._data.queued_story
            self._data.queued_story = None
            _LOGGER.info("Using queued story (%d chars)", len(story))
            return story

        try:
            return await self._generate_story_ai_task()
        except Exception as e:
            _LOGGER.warning("AI task story generation failed: %s, using backup", e)

        return random.choice(BACKUP_STORIES).strip()

    async def _generate_story_ai_task(self) -> str:
        """Generate story using Home Assistant's ai_task service."""
        story_length = self._data.story_length
        word_counts: dict[str, int] = {
            "short": 200,
            "medium": 350,
            "long": 500,
        }
        max_words = word_counts[story_length]

        theme = random.choice(STORY_THEMES)

        instructions = (
            f"You are a gentle, warm storyteller creating bedtime stories "
            f"for a 2-and-a-half-year-old girl named Chloe. "
            f"Create a soothing {max_words}-word bedtime story about {theme}. "
            f"Use Chloe's name throughout the story so she feels like the hero. "
            f"Use simple vocabulary, include repetition and rhythm, "
            f"focus on comforting happy themes with no scary elements. "
            f"Use simple words, soft sounds, and a happy ending where everyone is safe. "
            f"Always end with 'Sweet dreams, Chloe!' "
            f"Return only the story text, no titles or headers."
        )

        raw_result = await self.hass.services.async_call(
            "ai_task",
            "generate_data",
            {"task_name": "generate_story", "instructions": instructions},
            blocking=True,
            return_response=True,
        )
        result: dict[str, Any] = dict(raw_result) if raw_result else {}

        story: str = str(result.get("data", "") or "")
        if not story:
            raise ValueError("ai_task returned empty response")

        return story.strip()

    async def _offer_another_story(self, call_control_id: str) -> None:
        """Ask if they want another story."""
        message = (
            "Would you like to hear another story? "
            "Press 1 if you want another story, "
            "or you can hang up and go to sleep. Sweet dreams!"
        )

        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/gather",
            {
                "payload": message,
                "timeout_millis": 10000,
                "minimum_digits": 1,
                "maximum_digits": 1,
                "valid_digits": "1",
            },
        )

    async def _say_goodbye(self, call_control_id: str) -> None:
        """Say goodbye and hang up."""
        goodbye = (
            "Sleep tight, little one! Dial-a-Story will be here whenever "
            "you need a bedtime story. Sweet dreams!"
        )

        await self._speak_on_call(call_control_id, goodbye)
        await asyncio.sleep(3)
        await self._hangup_call(call_control_id)

    async def _speak_on_call(
        self,
        call_control_id: str,
        text: str,
        pause: int = 0,
    ) -> None:
        """Convert text to speech on active call."""
        if self._data.elevenlabs_api_key:
            try:
                await self._speak_elevenlabs(call_control_id, text)
                return
            except Exception as e:
                _LOGGER.warning(
                    "ElevenLabs TTS failed: %s, falling back to Telnyx", e
                )

        voice_pref = self._data.voice_preference
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/speak",
            {
                "payload": text,
                "voice": voice_pref,
                "language": "en-US",
            },
        )

    async def _speak_elevenlabs(
        self, call_control_id: str, text: str
    ) -> None:
        """Generate speech via ElevenLabs and play on call."""
        session = async_get_clientsession(self.hass)
        api_key = self._data.elevenlabs_api_key
        if not api_key:
            raise HomeAssistantError("ElevenLabs API key not configured")

        voice_pref = self._data.voice_preference
        voice_id = ELEVENLABS_VOICES.get(voice_pref, ELEVENLABS_VOICES["female"])

        response = await session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": CONTENT_TYPE_JSON,
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.6,
                    "similarity_boost": 0.75,
                    "style": 0.1,
                },
            },
        )

        if response.status != 200:
            error_text = await response.text()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="elevenlabs_api_error",
                translation_placeholders={"error": error_text},
            )

        audio_bytes = await response.read()
        audio_id = hashlib.md5(
            f"{text}{time.time()}".encode()
        ).hexdigest()

        self._data.audio_cache[audio_id] = audio_bytes

        try:
            external_url = get_url(
                self.hass, prefer_cloud=True, allow_internal=False
            )
        except NoURLAvailableError:
            external_url = get_url(self.hass, prefer_external=True)

        audio_url = (
            f"{external_url}/api/webhook/{WEBHOOK_ID_AUDIO}?id={audio_id}"
        )
        _LOGGER.debug("Playing audio from %s", audio_url)

        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/playback_start",
            {"audio_url": audio_url},
        )

        # Clean up old cache entries (keep last 10)
        cache = self._data.audio_cache
        if len(cache) > 10:
            oldest_keys = list(cache.keys())[:-10]
            for key in oldest_keys:
                del cache[key]

    async def _hangup_call(self, call_control_id: str) -> None:
        """Hang up the call."""
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/hangup", {}
        )

    async def _telnyx_api_call(
        self, endpoint: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Make API call to Telnyx."""
        session = async_get_clientsession(self.hass)
        api_key = self._data.telnyx_api_key

        url = f"https://api.telnyx.com{endpoint}"

        try:
            response = await session.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": CONTENT_TYPE_JSON,
                },
                json=payload,
            )

            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error(
                    "Telnyx API error: %s - %s", response.status, error_text
                )

            result: dict[str, Any] = await response.json()
            return result

        except Exception as e:
            _LOGGER.error("Error calling Telnyx API %s: %s", endpoint, e)
            raise
