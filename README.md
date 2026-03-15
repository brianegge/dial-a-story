# 📖 Dial-a-Story

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

**AI-powered bedtime stories hotline for kids ages 2-5**

Give your toddler a phone number they can call anytime to hear a fresh, AI-generated bedtime story! Works with Home Assistant, Telnyx, and optional OpenAI integration.

---

## ✨ Features

- 📞 **Real phone number** your kid can dial
- 🤖 **AI-generated stories** (or 3 quality backup stories)
- 🎙️ **Text-to-speech** reads stories aloud
- 🔁 **Multi-story support** (up to 3 per call)
- 💰 **Super cheap** (~$3-5/month)
- 🔒 **Privacy-first** (all processing in your Home Assistant)
- 📊 **Call logging** to track usage

---

## 💰 Cost Breakdown

**Monthly:**
- Phone number: $1
- Calls (5/day, 3min avg): ~$1
- TTS: ~$1.50
- OpenAI (optional): ~$1.50

**Total: $3-5/month** vs Spotify Kids at $10/month!

---

## 🚀 Quick Start

### Prerequisites

1. **Telnyx account** (sign up at [telnyx.com](https://telnyx.com/sign-up))
2. **Telnyx phone number** ($1/month - buy in portal)
3. **Telnyx API key** (get from [portal](https://portal.telnyx.com/#/app/api-keys))
4. **Home Assistant** with HTTPS access (Nabu Casa or reverse proxy)
5. **OpenAI API key** (optional, for better stories)

### Installation via HACS

1. **Add custom repository:**
   - HACS → Integrations → ⋮ Menu → Custom repositories
   - Repository: `https://github.com/brianegge/dial-a-story`
   - Category: Integration
   - Click Add

2. **Install:**
   - Search for "Dial-a-Story" in HACS
   - Click Install
   - Restart Home Assistant

3. **Add the integration:**
   - Go to **Settings → Devices & Services → Add Integration**
   - Search for "Dial-a-Story"
   - Enter your Telnyx API key and configure options
   - The integration will validate your API key before completing setup

4. **Get your webhook URL:**
   - Nabu Casa: `https://YOUR_INSTANCE.ui.nabu.casa/api/webhook/dial_a_story`
   - Self-hosted: `https://your-domain.com/api/webhook/dial_a_story`

5. **Configure Telnyx:**
   - Go to [Voice → TeXML Applications](https://portal.telnyx.com/#/app/call-control/texml)
   - Create Application → Name: "Dial-a-Story"
   - Webhook URL: (your HA webhook URL from above)
   - Save
   - Assign your phone number to this application

6. **Test it!** Call your Telnyx number and listen to a story 🎉

### Removing the Integration

This integration follows standard integration removal. Go to **Settings → Devices & Services**, click the three dots on Dial-a-Story, and select **Delete**.

---

## 📋 Configuration Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `telnyx_api_key` | Yes | - | Your Telnyx API key |
| `openai_api_key` | No | - | OpenAI key for AI stories (uses backups if omitted) |
| `story_length` | No | `medium` | Story length: `short` (~200 words), `medium` (~350), `long` (~500) |
| `voice_preference` | No | `female` | TTS voice: `male` or `female` |

---

## 🎯 How It Works

1. Kid calls your Telnyx number
2. Telnyx sends webhook to your Home Assistant
3. HA answers with friendly greeting
4. Story is generated (AI or backup)
5. TTS reads story aloud
6. Asks if they want another (max 3 per call)
7. Says goodnight and hangs up

---

## 🛡️ Security & Privacy

- ✅ No authentication required (webhooks work by design)
- ✅ Telnyx validates webhook signatures
- ✅ No personal data stored
- ✅ Call logs local to Home Assistant
- ✅ Stories not saved (generated fresh each time)

---

## 🐛 Troubleshooting

### Call doesn't connect

1. Check Home Assistant logs: Settings → System → Logs
2. Verify Telnyx API key is correct
3. Test webhook manually:
   ```bash
   curl -X POST https://YOUR_HA_URL/api/webhook/dial_a_story \
     -H "Content-Type: application/json" \
     -d '{"data":{"event_type":"call.initiated","payload":{"call_control_id":"test","from":"+15551234567"}}}'
   ```

### No greeting plays

- Verify webhook URL in Telnyx matches your HA instance
- Check HA firewall allows inbound HTTPS
- Look for errors in HA logs

### Stories are boring

- Add OpenAI API key for AI-generated stories
- Adjust `story_length` to match kid's attention span
- Edit `STORY_THEMES` in code for custom topics

### Kids lose interest

- Reduce `story_length` to `short`
- Try different `voice_preference`
- Make it part of a bedtime routine

---

## 🔧 Advanced Customization

### Add Your Own Story Themes

Edit `custom_components/dial_a_story/__init__.py` and modify `STORY_THEMES`:

```python
STORY_THEMES = [
    "a friendly dinosaur who loves to share toys",
    "YOUR CUSTOM THEME HERE",
    # ... add more
]
```

### Add Custom Backup Stories

Edit `BACKUP_STORIES` array in the same file.

### Change Voice

Telnyx supports male/female voices. For more options, check [Telnyx TTS docs](https://developers.telnyx.com/docs/api/v2/call-control/Call-Commands#CallSpeak).

---

## 📊 Call Logging

All calls are logged in Home Assistant. Check logs with:

```
Settings → System → Logs
```

Search for "dial_a_story" to see call events.

---

## 💡 Tips for Success

1. **Pick a memorable number** (repeating digits, etc.)
2. **Practice together** first few times
3. **Make it a ritual** - "Time to call Dial-a-Story!"
4. **Monitor costs** via Telnyx billing dashboard
5. **Update themes seasonally** (holidays, seasons, etc.)

---

## 🤝 Contributing

Contributions welcome! Please open an issue or PR on GitHub.

### Ideas for Enhancement

- Multi-language support
- Custom character voices (ElevenLabs integration)
- Parent dashboard showing favorite stories
- Scheduled callback reminders
- Voice clone parent's voice

---

## 📄 License

MIT License - use it, fork it, share it!

---

## 🙏 Credits

Built with:
- [Home Assistant](https://www.home-assistant.io/)
- [Telnyx](https://telnyx.com/) (phone service)
- [OpenAI](https://openai.com/) (optional story generation)

Created by [@brianegge](https://github.com/brianegge) for his 2-year-old 💙

---

## ⭐ Support

If this helps your family, please star the repo! It helps other parents discover it.

Got questions? [Open an issue](https://github.com/brianegge/dial-a-story/issues) or ping me on the [Home Assistant Discord](https://discord.gg/home-assistant).

---

**Sweet dreams! 🌙✨**
