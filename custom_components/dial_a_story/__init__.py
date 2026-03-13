"""
Dial-a-Story: AI Bedtime Stories Hotline for Toddlers
Home Assistant Custom Component

HACS-compatible integration for creating a phone number your kids can call
to hear AI-generated bedtime stories.
"""
import asyncio
import logging
import random
from typing import Any, Dict

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import CONF_API_KEY

_LOGGER = logging.getLogger(__name__)

DOMAIN = "dial_a_story"
CONF_TELNYX_API_KEY = "telnyx_api_key"
CONF_OPENAI_API_KEY = "openai_api_key"
CONF_STORY_LENGTH = "story_length"
CONF_VOICE_PREFERENCE = "voice_preference"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_TELNYX_API_KEY): cv.string,
                vol.Optional(CONF_OPENAI_API_KEY): cv.string,
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
        "openai_api_key": conf.get(CONF_OPENAI_API_KEY),
        "story_length": conf.get(CONF_STORY_LENGTH, "medium"),
        "voice_preference": conf.get(CONF_VOICE_PREFERENCE, "female"),
        "active_calls": {},  # Track active calls and state
    }
    
    # Register webhook view
    hass.http.register_view(DialAStoryWebhookView(hass))
    
    _LOGGER.info("Dial-a-Story initialized successfully")
    return True


class DialAStoryWebhookView(HomeAssistantView):
    """Handle Telnyx webhook callbacks."""
    
    url = "/api/webhook/dial_a_story"
    name = "api:webhook:dial_a_story"
    requires_auth = False
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the webhook view."""
        self.hass = hass
    
    async def post(self, request):
        """Handle incoming webhook from Telnyx."""
        try:
            data = await request.json()
            event_type = data.get("data", {}).get("event_type")
            payload = data.get("data", {}).get("payload", {})
            
            _LOGGER.info(f"Received Telnyx event: {event_type}")
            
            if event_type == "call.initiated":
                await self._handle_call_initiated(payload)
            elif event_type == "call.answered":
                await self._handle_call_answered(payload)
            elif event_type == "call.speak.ended":
                await self._handle_speak_ended(payload)
            elif event_type == "call.gather.ended":
                await self._handle_gather_ended(payload)
            elif event_type == "call.hangup":
                await self._handle_call_hangup(payload)
            
            return self.json({"status": "ok"})
            
        except Exception as e:
            _LOGGER.error(f"Error handling webhook: {e}", exc_info=True)
            return self.json({"status": "error", "message": str(e)}, status_code=500)
    
    async def _handle_call_initiated(self, payload: Dict[str, Any]):
        """Handle when a new call comes in."""
        call_control_id = payload.get("call_control_id")
        from_number = payload.get("from")
        
        _LOGGER.info(f"New call from {from_number}, control_id: {call_control_id}")
        
        # Initialize call state
        self.hass.data[DOMAIN]["active_calls"][call_control_id] = {
            "from": from_number,
            "story_count": 0,
            "state": "initiated",
        }
        
        # Answer the call
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/answer",
            {}
        )
    
    async def _handle_call_answered(self, payload: Dict[str, Any]):
        """Handle when call is answered - play greeting."""
        call_control_id = payload.get("call_control_id")
        
        call_state = self.hass.data[DOMAIN]["active_calls"].get(call_control_id)
        if not call_state:
            return
        
        call_state["state"] = "answered"
        
        # Play welcoming greeting
        greeting = (
            "Hello! Welcome to Dial-a-Story, your magical story friend! "
            "I'm so happy you called. Let me tell you a wonderful bedtime story!"
        )
        
        await self._speak_on_call(call_control_id, greeting)
    
    async def _handle_speak_ended(self, payload: Dict[str, Any]):
        """Handle when TTS finishes speaking."""
        call_control_id = payload.get("call_control_id")
        
        call_state = self.hass.data[DOMAIN]["active_calls"].get(call_control_id)
        if not call_state:
            return
        
        current_state = call_state.get("state")
        
        if current_state == "answered":
            # Greeting finished, now tell story
            call_state["state"] = "telling_story"
            await self._tell_story(call_control_id)
            
        elif current_state == "telling_story":
            # Story finished, ask if they want another
            call_state["state"] = "offering_another"
            await self._offer_another_story(call_control_id)
            
        elif current_state == "offering_another":
            # They didn't press anything, say goodbye
            await self._say_goodbye(call_control_id)
    
    async def _handle_gather_ended(self, payload: Dict[str, Any]):
        """Handle DTMF input (key press) from caller."""
        call_control_id = payload.get("call_control_id")
        digits = payload.get("digits", "")
        
        call_state = self.hass.data[DOMAIN]["active_calls"].get(call_control_id)
        if not call_state:
            return
        
        if call_state.get("state") == "offering_another" and digits == "1":
            # They want another story!
            call_state["state"] = "telling_story"
            call_state["story_count"] += 1
            
            # Limit to 3 stories per call to manage costs
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
            # Any other input or no input, say goodbye
            await self._say_goodbye(call_control_id)
    
    async def _handle_call_hangup(self, payload: Dict[str, Any]):
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
        # Try to generate with LLM first, fall back to backup stories
        story = await self._generate_story()
        
        await self._speak_on_call(call_control_id, story, pause=500)
    
    async def _generate_story(self) -> str:
        """Generate a story using OpenAI or use backup."""
        openai_key = self.hass.data[DOMAIN].get("openai_api_key")
        
        if openai_key:
            try:
                return await self._generate_story_openai()
            except Exception as e:
                _LOGGER.warning(f"OpenAI story generation failed: {e}, using backup")
        
        # Use backup story
        return random.choice(BACKUP_STORIES).strip()
    
    async def _generate_story_openai(self) -> str:
        """Generate story using OpenAI API."""
        session = async_get_clientsession(self.hass)
        openai_key = self.hass.data[DOMAIN]["openai_api_key"]
        
        story_length = self.hass.data[DOMAIN]["story_length"]
        word_counts = {"short": 200, "medium": 350, "long": 500}
        max_words = word_counts[story_length]
        
        theme = random.choice(STORY_THEMES)
        
        system_prompt = """You are a gentle, warm storyteller creating bedtime stories 
        for children aged 2-5 years old. Use simple vocabulary, include repetition and 
        rhythm, focus on comforting happy themes with no scary elements. Always end with 
        'Sweet dreams, little one!'"""
        
        user_prompt = f"""Create a soothing {max_words}-word bedtime story about {theme}. 
        Use simple words, soft sounds, and a happy ending where everyone is safe."""
        
        response = await session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_words * 2,
                "temperature": 0.8,
            },
        )
        
        result = await response.json()
        story = result["choices"][0]["message"]["content"]
        
        return story.strip()
    
    async def _offer_another_story(self, call_control_id: str):
        """Ask if they want another story."""
        message = (
            "Would you like to hear another story? "
            "Press 1 if you want another story, "
            "or you can hang up and go to sleep. Sweet dreams!"
        )
        
        # Use gather to wait for DTMF input
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/gather",
            {
                "payload": message,
                "timeout_millis": 10000,  # 10 seconds to respond
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
        voice_pref = self.hass.data[DOMAIN]["voice_preference"]
        
        # Telnyx voice options
        voice_map = {
            "female": "female",
            "male": "male",
        }
        
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/speak",
            {
                "payload": text,
                "voice": voice_map.get(voice_pref, "female"),
                "language": "en-US",
            }
        )
        
        if pause > 0:
            await asyncio.sleep(pause / 1000)
    
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
