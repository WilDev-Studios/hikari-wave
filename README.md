# hikari-wave

Voice module for `hikari`-based Discord bots

- Latest Version `UNRELEASED`
- Supports Python `3.10+`

[![Documentation Status](https://readthedocs.org/projects/hikari-wave/badge/?version=latest&style=for-the-badge)](https://hikari-wave.readthedocs.io/en/latest/?badge=latest)

## What is hikari-wave?

`hikari-wave` is a standalone module for `hikari` (an asynchronous Discord API for building bots) that allows developers to easily manipulate voice-related systems and logic. Much like `discord.py`, `hikari-wave` uses `aiohttp` to communicate with Discord on the backend, while most other `hikari`-based bots use `Lavalink` as a backend, which requires a separate install.

## What are hikari-wave's features?

- Doesn't require third-party installs besides `ffmpeg`
- Easy to use, asynchronous API
- Heavily type-hinted and type-safe

## How do I use hikari-wave?

- Install `hikari-wave` via `PyPI`: `pip install hikari-wave`
- Import it into your program using `import hikariwave`

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
import hikari
import hikariwave

bot: hikari.GatewayBot = hikari.GatewayBot(TOKEN_HERE)
voice: hikariwave.VoiceClient = hikariwave.VoiceClient(bot)

@bot.listen(hikari.VoiceStateUpdateEvent)
async def voice_state_update(event: hikari.VoiceStateUpdateEvent) -> None:
    if event.state.user_id == bot.get_me().id: # Don't update if it's the bot, only others
        return
    
    if event.state.channel_id:
        await voice.connect(event.guild_id, event.state.channel_id)
    else:
        await voice.disconnect(event.guild_id)

bot.run()
```

## Feature Checklist

- [x] Gateway Connections and Channel Join/Leave
- [ ] Disconnect Handling via Resumed Sessions
- [ ] Audio Streaming from Sources
- [x] Audio Encryption Algorithms
- [ ] Discord Audio/Video End-2-End Encryption (DAVE) Support (Required in the future)

## Contributing

Thanks for your interest in contributing to this project! Contributions are always welcome!
Whether you want to submit a bug report, fix a bug, add a new feature, or remove parts of the program, we welcome your contributions.

### How to Contribute

1. Fork this repository
    - Fork this repository to your own GitHub account by clicking the "Fork" button at the top-right of this page.
2. Clone your fork
    - Clone the forked repository to your local machine using the following command:
    - `git clone https://github.com/your-username/your-fork.git`
3. Create a new branch
    - Before making any changes, create a new branch with a descriptive name for your work/changes. For example:
    - `git checkout -b feature-name`
4. Make your changes
    - Implement your changes, whether it's fixing bugs, improving documentation, or adding new features.
    - Be sure to write clear, concise commit messages explaining the changes you've made.
5. Commit your changes
    - Once your changes are ready, commit them to your local branch:
    - `git add .`
    - `git commit -m "Add feature-name"`
6. Push your changes
    - Push your changes to your forked repository:
    - `git push origin feature-name`
7. Create a pull request
    - Open a pull request on the original repository from your fork.
    - Ensure that your pull request explains the purpose of the changes and any relevant context.
    - If applicable, include links to relevant issues.

### Reporting Bugs

- If you find a bug or issue, please open an issue on the `Issues` page above.
- Be sure to provide detailed information to help us understand and reproduce the problem.

### Feature Requests

- We welcome suggestions for new features.
- If you have an idea, please open an issue on the `Issues` page above to discuss it first.
- This ensures that we're all on the same page and helps us prioritize improvements.

### Thanks for Contributing

Your contributions make this project better and more useful for everyone! Thank you for taking the time to improve this project!

## License

This project is licensed under the [MIT License](https://github.com/WilDev-Studios/hikari-wave/blob/main/LICENSE). Copyright &copy; 2025 WilDev Studios. All rights reserved.
