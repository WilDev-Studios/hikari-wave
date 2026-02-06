<p align="center">
    <img src="https://raw.githubusercontent.com/WilDev-Studios/hikari-wave/main/assets/banner.png" width=650/><br/>
    <b>A lightweight, native voice implementation for hikari-based Discord bots</b><br/><br/>
    <img src="https://img.shields.io/pypi/pyversions/hikari-wave?style=for-the-badge&color=007EC6"/>
    <img src="https://img.shields.io/pypi/v/hikari-wave?style=for-the-badge&color=007EC6"/>
    <img src="https://img.shields.io/pypi/dm/hikari-wave?style=for-the-badge&color=007EC6"/><br/>
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge&color=002F4B"/>
    <img src="https://img.shields.io/readthedocs/hikari-wave?style=for-the-badge&color=002F4B"/>
    <img src="https://img.shields.io/github/actions/workflow/status/WilDev-Studios/hikari-wave/build.yml?branch=main&style=for-the-badge&label=Build/Tests&color=002F4B">
    <img src="https://img.shields.io/pypi/status/hikari-wave?style=for-the-badge&color=002F4B"/>
</p>

## Overview

`hikari-wave` is a standalone voice module for [`hikari`](https://github.com/hikari-py/hikari) that provides **direct voice gateway communication** without requiring external backends like `Lavalink`.

It is designed to be:

- **Simple to use**
- **Fully asynchronous**
- **Native to `hikari`'s architecture**

No separate software. No complex setup. Just voice.

## Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Help/Contact](#help-and-contact)
- [Versioning/Stability Policy](#versioning-stability-policy)

## Features

- Native Discord voice gateway implementation
- Async-first, awaitable API
- Strong typing and documentation throughout (Pylance/MyPy friendly)
- Supplemental voice events for better control and UX
- No external services (no Lavalink, no JVM, etc.)
- Designed specifically for `hikari`'s async model
- Minimal overhead and predictable behavior

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
voice = hikariwave.VoiceClient(bot)

bot.run()
```

Connect to a channel and play audio when you join a channel:

```python
@bot.listen()
async def on_join(event: hikariwave.MemberJoinEvent):
    connection = await voice.connect(event.guild_id, event.channel_id)
    source = FileAudioSource("test.mp3")

    await connection.player.play(source)
```

That's it.

## Implemented Features

- [X] Voice connect / disconnect
- [X] Audio playback
- [X] Move, reconnect, resume
- [X] Player utilities (queue, shuffle, next/previous, volume, etc.)
- Audio Sources:
    - [X] Files
    - [X] URLs
    - [X] In-memory buffers
    - [X] YouTube
- [X] Discord Audio/Video End-to-End Encryption (`DAVE`)

## Documentation

Full documentation is available at:
[https://hikari-wave.wildevstudios.net/](https://hikari-wave.wildevstudios.net/)

## Library Lifecycle

See https://hikari-wave.wildevstudios.net/en/latest/pages/lifecycle for the full list of deprecated and experimental features.

## Help and Contact

Feel free to join the [hikari](https://discord.gg/hikari) Discord server under the `#wave` channel for assistance.

## Versioning & Stability Policy

`hikari-wave` follows **Semantic Versioning** with a clear and practical stability model designed to balance rapid development with reliability.

### Version Format

`MAJOR.MINOR.PATCH`

### Patch Releases (`x.y.z`)

- Bug fixes and internal improvements only
- No breaking changes
- Always considered **stable**
- No alpha (`a`) or beta (`b`) suffixes

Patch releases are safe to upgrade to without code changes.

### Minor Releases (`x.y.0`)

- Introduce new features, subsystems, or configuration options
- Existing public APIs generally preserved, but behavior may expand
- May include **short-lived alpha/beta pre-releases** before stabilization

Example releases flow:
`1.0.0a1 -> 1.0.0b1 -> 1.0.0 -> 1.0.1`
Pre-releases exist to gather feedback and catch issues early. Once stabilized, the same version is released as a stable minor.

### Pre-Releases (`a`/`b`)

- Used only for **new minor/major versions**
- Intended for developers who want early access to new features/versions
- Not recommended for production unless you are testing upcoming functionality

### Recommendation

If you want maximum stability:

- Pin to stable releases
- Avoid alpha/beta versions

If you want early access to new features:

- Opt into pre-releases and report issues

## Deprecation Policy

To ensure stability while allowing `hikari-wave` to evolve, the project follows a structured and transparent deprecation process.

### What is considered deprecated?

A feature may be deprecated if it:

- Has a better or more flexible replacement
- Causes long-term maintenance or performance issues
- Conflicts with newer architectural changes

### Deprecation Process

When a feature is deprecated:

1. **Explicit Announcement**

- The deprecation is documented in:
    - The changelog
    - The documentation (API docs)
- A clear migration path is provided when possible

2. **Runtime Warnings**

- Deprecated features may emit a `DeprecationWarning`
- Warnings are non-fatal and do not break existing code

### Removal Timeline

- **Pre-`1.0.0`**
    - Breaking removals may occur at any time
    - Deprecations will still receive advance notice whenever possible
- **`1.0.0`+**
    - Deprecated features will not be removed until the next **major version**

### Experimental Features

- APIs marked as **experimental** are exempt from the deprecation process
- Experimental features may change or be removed without notice
- Experimental status will always be clearly documented

### User Responsibility

Users are encouraged to:

- Monitor release notes and changelogs
- Address deprecation warnings promptly
- Test against pre-releases when relying on newer or evolving features

## Contributing

Bug reports and feature requests are welcome via GitHub Issues.
Clear reproduction steps and context are appreciated.

## License

MIT License &copy; 2025 WilDev Studios
