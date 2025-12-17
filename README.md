# hikari-wave

Voice module for `hikari`-based Discord bots

- Latest Version `0.0.1a3`
- Supports Python `3.10+`

[![Documentation Status](https://readthedocs.org/projects/hikari-wave/badge/?version=latest&style=for-the-badge)](https://hikari-wave.readthedocs.io/en/latest/?badge=latest)

## What is hikari-wave?

`hikari-wave` is a standalone module for `hikari` (an asynchronous Discord API for building bots) that allows developers to easily manipulate voice-related systems and logic. Much like `discord.py`, `hikari-wave` implements a custom communication layer to communicate with Discord on the backend, while most other `hikari`-based bots use `Lavalink` as a backend, which requires a separate install.

## What are hikari-wave's features?

- Doesn't require third-party installs besides [FFmpeg](https://ffmpeg.org/download.html).
- Easy to use, asynchronous API
- Heavily type-hinted and type-safe
- Supplemental events for further development ease and QoL

## How do I use hikari-wave?

- Install `hikari-wave` via `PyPI`: `pip install hikari-wave`
- Import it into your program using `import hikariwave`
- Verify [FFmpeg](https://ffmpeg.org/download.html) is installed and discoverable in your system's `PATH`.

## Documentation

[You can find our documentation here](https://hikari-wave.wildevstudios.net/).

## Getting Started

You need a basic `hikari` bot set up, like below:

```python
import hikari

bot: hikari.GatewayBot = hikari.GatewayBot(TOKEN_HERE)
bot.run()
```

This won't do anything besides sit and look pretty. The following will make the bot connect/disconnect if a user joins/leaves a voice channel:

```python
# imports and bot/client definition

@bot.listen(hikariwave.MemberJoinVoiceEvent)
async def member_joined_voice(event: hikariwave.MemberJoinVoiceEvent) -> None:
    await voice.connect(event.guild_id, event.channel_id)

@bot.listen(hikariwave.MemberLeaveVoiceEvent)
async def member_left_voice(event: hikariwave.MemberLeaveVoiceEvent) -> None:
    await voice.disconnect(guild_id=event.guild_id)
    # OR - can work for either guild or channel, for convenience
    await voice.disconnect(channel_id=event.channel_id)

bot.run()
```

To make this play audio, get the connection and then play:

```python
@bot.listen(hikariwave.MemberJoinVoiceEvent)
async def member_joined_voice(event: hikariwave.MemberJoinVoiceEvent) -> None:
    connection: hikariwave.VoiceConnection = await voice.connect(event.guild_id, event.channel_id)
    await connection.play_file("test.mp3")
```

Super easy and convenient!

## Implemented Steps

- [x] Connect/Disconnect logic
- [X] Playing audio
- [X] Move/Reconnect/Resume logic
- [X] Supplemental events
- Audio types: files, URLs, etc.
    1. [X] Files
    2. [ ] Web (URLs)
    3. [ ] YouTube
    4. [ ] Others (SoundCloud, buffers, etc.)
- [X] Player QoL (queue, shuffle, prev/next, etc.)
- [ ] DAVE (Discord Audio/Video End-to-End Encryption)

## Reporting Bugs

- If you find a bug or issue, please open an issue on the `Issues` page above.
- Be sure to provide detailed information to help us understand and reproduce the problem.

## Feature Requests

- We welcome suggestions for new features.
- If you have an idea, please open an issue on the `Issues` page above to discuss it first.
- This ensures that we're all on the same page and helps us prioritize improvements.

## Thanks for Contributing

Your contributions make this project better and more useful for everyone! Thank you for taking the time to improve this project!

## License

This project is licensed under the [MIT License](https://github.com/WilDev-Studios/hikari-wave/blob/main/LICENSE). Copyright &copy; 2025 WilDev Studios. All rights reserved.
