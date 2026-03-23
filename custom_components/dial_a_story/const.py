"""Constants for Dial-a-Story integration."""

DOMAIN = "dial_a_story"
WEBHOOK_ID = "dial_a_story"
WEBHOOK_ID_AUDIO = "dial_a_story_audio"
CONF_TELNYX_API_KEY = "telnyx_api_key"
CONF_ELEVENLABS_API_KEY = "elevenlabs_api_key"
CONF_STORY_LENGTH = "story_length"
CONF_VOICE_PREFERENCE = "voice_preference"
SERVICE_SET_STORY = "set_story"
SERVICE_CLEAR_STORY = "clear_story"

# ElevenLabs voice IDs
ELEVENLABS_VOICES = {
    "female": "EXAVITQu4vr4xnSDxMaL",  # Sarah - soft, warm
    "male": "pNInz6obpgDQGcFmaJgB",  # Adam - deep, narration
}
