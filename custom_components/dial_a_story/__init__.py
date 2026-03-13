"""
Dial-a-Story: AI Bedtime Stories Hotline for Toddlers
Home Assistant Custom Component

HACS-compatible integration for creating a phone number your kids can call
to hear AI-generated bedtime stories.
"""
import asyncio
import hashlib
import logging
import random
import time
from typing import Any, Dict

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url, NoURLAvailableError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "dial_a_story"
WEBHOOK_ID = "dial_a_story"
WEBHOOK_ID_AUDIO = "dial_a_story_audio"
CONF_TELNYX_API_KEY = "telnyx_api_key"
CONF_ELEVENLABS_API_KEY = "elevenlabs_api_key"
CONF_STORY_LENGTH = "story_length"
CONF_VOICE_PREFERENCE = "voice_preference"

# ElevenLabs voice IDs
ELEVENLABS_VOICES = {
    "female": "EXAVITQu4vr4xnSDxMaL",  # Sarah - soft, warm
    "male": "pNInz6obpgDQGcFmaJgB",  # Adam - deep, narration
}

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_TELNYX_API_KEY): cv.string,
                vol.Optional(CONF_ELEVENLABS_API_KEY): cv.string,
                vol.Optional(CONF_STORY_LENGTH, default="medium"): vol.In(
                    ["short", "medium", "long"]
                ),
                vol.Optional(CONF_VOICE_PREFERENCE, default="female"): vol.In(
                    ["male", "female"]
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# Story themes appropriate for 2-5 year olds
STORY_THEMES = [
    "a friendly dinosaur who loves to share toys",
    "a magical train that visits the moon and stars",
    "a brave little bunny exploring a beautiful garden",
    "a silly elephant who can't stop sneezing bubbles",
    "a kind robot who helps animals find their way home",
    "a curious kitten's first adventure outside",
    "a gentle whale who sings lullabies to fish",
    "a happy cloud that makes rainbow rain",
    "a sleepy teddy bear finding the perfect bedtime",
    "a tiny firefly making friends in the forest",
]

# Backup stories in case LLM is unavailable
BACKUP_STORIES = [
    """Once upon a time, the moon was very sleepy. All day long, the moon watched
    the sun play in the sky. 'I want to play too!' said the moon. But the sun smiled
    and said, 'Moon, you have the most important job. You watch over all the children
    while they sleep and keep them safe with your gentle light.' The moon felt so proud!
    That night, the moon shone brightly and sang a soft lullaby to all the sleeping
    children. And everyone slept peacefully. Sweet dreams, little one!""",

    """In a cozy garden, there lived a little bunny named Benny. Benny loved to hop
    and play, but sometimes the garden seemed big at night. One evening, Benny's mama
    said, 'Benny, you are so brave!' Benny didn't feel brave. But then he heard a tiny
    voice - it was a little firefly! 'I'm scared of the dark,' the firefly said. Benny
    held the firefly's little hand. Together they weren't scared anymore. They became
    best friends and always helped each other feel brave. Sweet dreams, little one!""",

    """There was once a kind little cloud named Fluffy. Fluffy loved to float in the
    sky and watch the children play below. One day, Fluffy wanted to help the flowers
    grow, so she made the gentlest, softest rain. The flowers danced and said 'Thank you!'
    Then Fluffy made a beautiful rainbow! All the animals came out to see it. They said,
    'Fluffy, you're the best cloud ever!' And Fluffy smiled and floated happily in the
    sky. Sweet dreams, little one!""",
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Dial-a-Story component."""
    conf = config.get(DOMAIN, {})

    hass.data[DOMAIN] = {
        "telnyx_api_key": conf.get(CONF_TELNYX_API_KEY),
        "elevenlabs_api_key": conf.get(CONF_ELEVENLABS_API_KEY),
        "story_length": conf.get(CONF_STORY_LENGTH, "medium"),
        "voice_preference": conf.get(CONF_VOICE_PREFERENCE, "female"),
        "active_calls": {},
        "audio_cache": {},  # hash -> audio bytes
    }

    webhook.async_register(
        hass, DOMAIN, "Dial-a-Story", WEBHOOK_ID, handle_webhook,
        allowed_methods=["POST"],
        local_only=False,
    )

    webhook.async_register(
        hass, DOMAIN, "Dial-a-Story Audio", WEBHOOK_ID_AUDIO, handle_audio_webhook,
        allowed_methods=["GET"],
        local_only=False,
    )

    _LOGGER.info("Dial-a-Story initialized successfully")
    return True


async def handle_audio_webhook(
    hass: HomeAssistant, webhook_id: str, request
) -> None:
    """Serve cached audio files to Telnyx."""
    from aiohttp import web

    audio_id = request.query.get("id")
    if not audio_id or audio_id not in hass.data[DOMAIN]["audio_cache"]:
        return web.Response(status=404)

    audio_bytes = hass.data[DOMAIN]["audio_cache"][audio_id]
    return web.Response(
        body=audio_bytes,
        content_type="audio/mpeg",
        headers={"Content-Length": str(len(audio_bytes))},
    )


async def handle_webhook(
    hass: HomeAssistant, webhook_id: str, request
) -> None:
    """Handle incoming webhook from Telnyx."""
    from aiohttp import web

    try:
        data = await request.json()
        event_type = data.get("data", {}).get("event_type")
        payload = data.get("data", {}).get("payload", {})

        _LOGGER.info(f"Received Telnyx event: {event_type}")

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
        _LOGGER.error(f"Error handling webhook: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)}, status=500
        )


class _CallHandler:
    """Handle Telnyx call events."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def handle_call_initiated(self, payload: Dict[str, Any]):
        """Handle when a new call comes in."""
        call_control_id = payload.get("call_control_id")
        from_number = payload.get("from")

        _LOGGER.info(f"New call from {from_number}, control_id: {call_control_id}")

        self.hass.data[DOMAIN]["active_calls"][call_control_id] = {
            "from": from_number,
            "story_count": 0,
            "state": "initiated",
        }

        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/answer",
            {}
        )

    async def handle_call_answered(self, payload: Dict[str, Any]):
        """Handle when call is answered - play greeting."""
        call_control_id = payload.get("call_control_id")

        call_state = self.hass.data[DOMAIN]["active_calls"].get(call_control_id)
        if not call_state:
            return

        call_state["state"] = "answered"

        greeting = (
            "Hello! Welcome to Dial-a-Story, your magical story friend! "
            "I'm so happy you called. Let me tell you a wonderful bedtime story!"
        )

        await self._speak_on_call(call_control_id, greeting)

    async def handle_speak_ended(self, payload: Dict[str, Any]):
        """Handle when TTS finishes speaking."""
        call_control_id = payload.get("call_control_id")

        call_state = self.hass.data[DOMAIN]["active_calls"].get(call_control_id)
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

    async def handle_gather_ended(self, payload: Dict[str, Any]):
        """Handle DTMF input (key press) from caller."""
        call_control_id = payload.get("call_control_id")
        digits = payload.get("digits", "")

        call_state = self.hass.data[DOMAIN]["active_calls"].get(call_control_id)
        if not call_state:
            return

        if call_state.get("state") == "offering_another" and digits == "1":
            call_state["state"] = "telling_story"
            call_state["story_count"] += 1

            if call_state["story_count"] >= 3:
                await self._speak_on_call(
                    call_control_id,
                    "You've had three wonderful stories tonight! Time to rest now. Sweet dreams!"
                )
                await asyncio.sleep(3)
                await self._hangup_call(call_control_id)
            else:
                await self._speak_on_call(
                    call_control_id,
                    "Wonderful! Here's another story for you!"
                )
                await asyncio.sleep(1)
                await self._tell_story(call_control_id)
        else:
            await self._say_goodbye(call_control_id)

    async def handle_call_hangup(self, payload: Dict[str, Any]):
        """Handle call ending."""
        call_control_id = payload.get("call_control_id")

        if call_control_id in self.hass.data[DOMAIN]["active_calls"]:
            call_info = self.hass.data[DOMAIN]["active_calls"][call_control_id]
            _LOGGER.info(
                f"Call ended from {call_info.get('from')}, "
                f"told {call_info.get('story_count', 0)} stories"
            )
            del self.hass.data[DOMAIN]["active_calls"][call_control_id]

    async def _tell_story(self, call_control_id: str):
        """Generate and tell a bedtime story."""
        story = await self._generate_story()
        await self._speak_on_call(call_control_id, story, pause=500)

    async def _generate_story(self) -> str:
        """Generate a story using HA ai_task service or use backup."""
        try:
            return await self._generate_story_ai_task()
        except Exception as e:
            _LOGGER.warning(f"AI task story generation failed: {e}, using backup")

        return random.choice(BACKUP_STORIES).strip()

    async def _generate_story_ai_task(self) -> str:
        """Generate story using Home Assistant's ai_task service."""
        story_length = self.hass.data[DOMAIN]["story_length"]
        word_counts = {"short": 200, "medium": 350, "long": 500}
        max_words = word_counts[story_length]

        theme = random.choice(STORY_THEMES)

        instructions = (
            f"You are a gentle, warm storyteller creating bedtime stories "
            f"for children aged 2-5 years old. "
            f"Create a soothing {max_words}-word bedtime story about {theme}. "
            f"Use simple vocabulary, include repetition and rhythm, "
            f"focus on comforting happy themes with no scary elements. "
            f"Use simple words, soft sounds, and a happy ending where everyone is safe. "
            f"Always end with 'Sweet dreams, little one!' "
            f"Return only the story text, no titles or headers."
        )

        result = await self.hass.services.async_call(
            "ai_task",
            "generate_data",
            {"task_name": "generate_story", "instructions": instructions},
            blocking=True,
            return_response=True,
        )

        story = result.get("data", "")
        if not story:
            raise ValueError("ai_task returned empty response")

        return story.strip()

    async def _offer_another_story(self, call_control_id: str):
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
            }
        )

    async def _say_goodbye(self, call_control_id: str):
        """Say goodbye and hang up."""
        goodbye = (
            "Sleep tight, little one! "
            "Dial-a-Story will be here whenever you need a bedtime story. "
            "Sweet dreams!"
        )

        await self._speak_on_call(call_control_id, goodbye)
        await asyncio.sleep(3)
        await self._hangup_call(call_control_id)

    async def _speak_on_call(self, call_control_id: str, text: str, pause: int = 0):
        """Convert text to speech on active call."""
        elevenlabs_key = self.hass.data[DOMAIN].get("elevenlabs_api_key")

        if elevenlabs_key:
            try:
                await self._speak_elevenlabs(call_control_id, text)
                return
            except Exception as e:
                _LOGGER.warning(f"ElevenLabs TTS failed: {e}, falling back to Telnyx")

        voice_pref = self.hass.data[DOMAIN]["voice_preference"]
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/speak",
            {
                "payload": text,
                "voice": voice_pref,
                "language": "en-US",
            }
        )

    async def _speak_elevenlabs(self, call_control_id: str, text: str):
        """Generate speech via ElevenLabs and play on call."""
        session = async_get_clientsession(self.hass)
        api_key = self.hass.data[DOMAIN]["elevenlabs_api_key"]
        voice_pref = self.hass.data[DOMAIN]["voice_preference"]
        voice_id = ELEVENLABS_VOICES.get(voice_pref, ELEVENLABS_VOICES["female"])

        response = await session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
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
            raise RuntimeError(f"ElevenLabs API error: {response.status} - {error_text}")

        audio_bytes = await response.read()
        audio_id = hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()

        self.hass.data[DOMAIN]["audio_cache"][audio_id] = audio_bytes

        try:
            external_url = get_url(
                self.hass, prefer_cloud=True, allow_internal=False
            )
        except NoURLAvailableError:
            external_url = get_url(self.hass, prefer_external=True)

        audio_url = f"{external_url}/api/webhook/{WEBHOOK_ID_AUDIO}?id={audio_id}"
        _LOGGER.debug(f"Playing audio from {audio_url}")

        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/playback_start",
            {"audio_url": audio_url}
        )

        # Clean up old cache entries (keep last 10)
        cache = self.hass.data[DOMAIN]["audio_cache"]
        if len(cache) > 10:
            oldest_keys = list(cache.keys())[:-10]
            for key in oldest_keys:
                del cache[key]

    async def _hangup_call(self, call_control_id: str):
        """Hang up the call."""
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/hangup",
            {}
        )

    async def _telnyx_api_call(self, endpoint: str, payload: Dict[str, Any]):
        """Make API call to Telnyx."""
        session = async_get_clientsession(self.hass)
        api_key = self.hass.data[DOMAIN]["telnyx_api_key"]

        url = f"https://api.telnyx.com{endpoint}"

        try:
            response = await session.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error(f"Telnyx API error: {response.status} - {error_text}")

            return await response.json()

        except Exception as e:
            _LOGGER.error(f"Error calling Telnyx API {endpoint}: {e}")
            raise
