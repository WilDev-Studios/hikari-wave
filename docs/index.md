# hikari-wave

A lightweight, native voice implementation for `hikari`-based Discord bots.

- **Latest:** `0.0.1a4`
- **Python:** `3.10+`

[![Python](https://img.shields.io/pypi/pyversions/hikari-wave?style=for-the-badge)](https://pypi.org/project/hikari-wave/)
[![PyPI](https://img.shields.io/pypi/v/hikari-wave?style=for-the-badge)](https://pypi.org/project/hikari-wave/)
[![Downloads](https://img.shields.io/pypi/dd/hikari-wave?style=for-the-badge)](https://pypi.org/project/hikari-wave/)
[![Documentation Status](https://readthedocs.org/projects/hikari-wave/badge/?version=latest&style=for-the-badge)](https://hikari-wave.readthedocs.io/en/latest/?badge=latest)

## Overview

`hikari-wave` is a standalone voice module for [`hikari`](https://github.com/hikari-py.hikari) that provides **direct voice gateway communication** without requiring external backends like `Lavalink`.

It is designed to be:

- **Simple to use**
- **Fully asynchronous**
- **Native to `hikari`'s architecture**

No separate servers. No complex setup. Just voice.

## Features

- Native Discord voice gateway implementation
- No third-party services required (`FFmpeg` only)
- Clean, async-first API
- Strong typing and documentation throughout
- Supplemental voice events for better control and UX

## Installation

```bash
pip install hikari-wave
```

Ensure [FFmpeg](https://ffmpeg.org/download.html) is installed and available in your system `PATH`.

## Quick Start

Create a basic voice client bot:

```python
import hikari

bot = hikari.GatewayBot("TOKEN")
client = hikariwave.VoiceClient(bot)

bot.run()
```

Connect to voice when a member joins:

```python
@bot.listen(hikariwave.MemberJoinVoiceEvent)
async def on_join(event):
    await voice.connect(event.guild_id, event.channel_id)
```

Play audio:

```python
@bot.listen(hikariwave.MemberJoinVoiceEvent)
async def on_join(event):
    connection = await voice.connect(event.guild_id, event.channel_id)
    source = FileAudioSource("test.mp3")

    await connection.play(source)
```

That's it.

## Status

- [X] Voice connect / disconnect
- [X] Audio playback
- [X] Move, reconnect, resume
- [X] Player utilities (queue, shuffle, next/previous)
- Audio Sources:
    - [X] Files
    - [X] URLs
    - [X] In-memory buffers
    - [ ] Media sites (YouTube, SoundCloud, etc.) (planned)
- [ ] Discord `DAVE` (planned)

## Contributing

Bug reports and feature requests are welcome via GitHub Issues.
Clear reproduction steps and context are appreciated.

## License

MIT License &copy; 2025 WilDev Studios
