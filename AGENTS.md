# Agents

Instructions for AI coding agents working on this project.

## Project Structure

- `custom_components/dial_a_story/` — Home Assistant integration source
- `tests/` — pytest test suite

## Architecture

Dial-a-Story is a Home Assistant custom integration that provides an AI-powered bedtime story hotline for young children. It works as follows:

1. **Telnyx telephony**: The integration registers two webhooks — one for call control events (`dial_a_story`) and one for serving cached audio (`dial_a_story_audio`). Telnyx sends call events (initiated, answered, speak ended, gather ended, hangup) to the main webhook.

2. **Call flow**: When a call arrives, `_CallHandler` manages the state machine: answer the call, play a greeting, generate and tell a story, then offer another (up to 3 per call via DTMF input). The call state is tracked in `DialAStoryData.active_calls`.

3. **Story generation**: Stories are generated via Home Assistant's `ai_task.generate_data` service using themed prompts for ages 2-5. If the AI service is unavailable, hardcoded backup stories are used as fallback.

4. **Text-to-speech**: Speech is delivered either through ElevenLabs API (optional, higher quality) with audio cached and served via the audio webhook, or through Telnyx's built-in TTS as fallback.

5. **Config flow**: A single-step UI config flow collects the Telnyx API key (required), ElevenLabs API key (optional), story length, and voice preference. The Telnyx key is validated during setup.

## Key Files

- `custom_components/dial_a_story/__init__.py` — Integration setup, webhook handlers, call state machine, story generation, TTS
- `custom_components/dial_a_story/config_flow.py` — UI configuration flow with Telnyx API key validation
- `custom_components/dial_a_story/const.py` — Domain, webhook IDs, config keys, ElevenLabs voice IDs
- `custom_components/dial_a_story/manifest.json` — Integration metadata (depends on `ai_task` and `webhook`)
- `tests/conftest.py` — Shared pytest fixtures
- `tests/test_config_flow.py` — Config flow tests

## Python Conventions

### Formatting and linting

Configured via `pyproject.toml`:
- **Ruff** for linting and formatting (line length: 120)
- **mypy** for type checking
- Target: Python 3.12+

### Tests

- Async tests with `pytest` (`asyncio_mode = "auto"`)
- Test files: `test_*.py`, async functions: `async def test_*`

## Pull Requests

- Target: `brianegge/homeassistant-dial-a-story`
