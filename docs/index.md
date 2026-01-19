<p align="center">
    <img src="https://raw.githubusercontent.com/WilDev-Studios/hikari-wave/main/assets/banner.png" width=650/>
</p>

<p align="center">
    <img src="https://img.shields.io/pypi/pyversions/hikari-wave?style=for-the-badge"/>
    <img src="https://img.shields.io/pypi/dm/hikari-wave?style=for-the-badge"/>
    <img src="https://readthedocs.org/projects/hikari-wave/badge/?version=latest&style=for-the-badge"/>
</p>

<p align="center"><b>A lightweight, native voice implementation for hikari-based Discord bots</b></p>

<p align="center">
    <b>Latest:</b> <code>0.5.0a1</code>
    &nbsp;|&nbsp;
    <b>Python:</b> <code>3.10+</code>
</p>

## Overview

`hikari-wave` is a standalone voice module for [`hikari`](https://github.com/hikari-py/hikari) that provides **direct voice gateway communication** without requiring external backends like `Lavalink`.

It is designed to be:

- **Simple to use**
- **Fully asynchronous**
- **Native to `hikari`'s architecture**

No separate software. No complex setup. Just voice.

## Features

- Native Discord voice gateway implementation
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
voice = hikariwave.VoiceClient(bot)

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

    await connection.player.play(source)
```

That's it.

## Status

- [X] Voice connect / disconnect
- [X] Audio playback
- [X] Move, reconnect, resume
- [X] Player utilities (queue, shuffle, next/previous, volume, etc.)
- Audio Sources:
    - [X] Files
    - [X] URLs
    - [X] In-memory buffers
    - [X] YouTube
- [X] Discord `DAVE`

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
`0.4.0a1 -> 0.4.0b1 -> 0.4.0 -> 0.4.1`
Pre-releases exist to gather feedback and catch issues early. Once stabilized, the same version is released as a stable minor.

### Pre-Releases (`a`/`b`)

- Used only for **new minor versions**
- Intended for developers who want early access to new features
- Not recommended for production unless you are testing upcoming functionality.

### Backward Compatibility

- Until `1.0.0`, backward compatibility is **best-effort**
- Breaking changes may occur in minor versions, but will:
    - Be clearly documented
    - Never be silent
    - Typically go through pre-releases first

Once `1.0.0` is reached, stricter compatibility guarantees will apply.

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
- Was part of an experimental or early design
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

3. **Grace Period**

- Deprecated features will remain available for at least **one full minor release**
- Removal will not occur in the same release they are deprecated

### Removal Timeline

- **Pre-`1.0.0`**
    - Breaking removals may occur in minor releases
    - Deprecations will still receive advance notice whenever possible
- **`1.0.0`+**
    - Deprecated features will not be removed until the next **major version**
    - Patch releases will *never* remove deprecated functionality

### Backward Compatibility Guarantees

- Patch releases (`x.y.z`) will:
    - Never introduce breaking changes
    - Never remove deprecated features
- Minor releases (`x.y.0`) may:
    - Introduce deprecations
    - Include pre-releases (`a`/`b`) for feedback before stabilization

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
