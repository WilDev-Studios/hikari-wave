# Changelog

This page provides a high-level overview of changes in each release.
For full details, click a specific version.

!!! success "Help us!"
    If you ever come across an issue during our `alpha`/`beta` stage, **please** notify us ASAP.
    We want to weed out as much issues as possible before our `1.0.0` release.

## 0.5.0 (In Progress)

### 0.5.0a1 (STAGING)

- Fixed player history and queue.
- Fixed player timestamp properties' frame counter.

[View full changelog ->](0.5.0a1.md)

## 0.4.0 (January 10th, 2026)

- New `AudioBeginEvent` `origin` property.
- New `YouTubeAudioSource` `duration` property.
- New player `elapsed`, `remaining`, and `progress` properties.
- New `AudioSecondEvent`.
- Websocket debug logs silenced by default.
- `FileAudioSource` marked as non-production.
- New `MemberSpeechEvent` dispatched when members are speaking.
- New `AudioPlayer` `clear_history` method.

[View full changelog ->](0.4.0.md)

## 0.3.0 (December 31st, 2025)

- Reconnection logic added.
- Priority voice now supported.
- `VoiceWarningEvent` dispatched for high packet loss or jitter.
- New `YouTubeAudioSource`.
- Connection `gateway_latency` renamed to `latency`.

[View full changelog ->](0.3.0.md)

!!! warning "Contains breaking changes"
!!! info
    This release signalled the move from `alpha` to `beta`.

## 0.2.0 (December 21st, 2025)

- Configuration extended globally, per-connection, or per-source.
- `MEMORY`/`DISK` FFmpeg buffer modes.
- Client automatically cleans up when signalled by `hikari`.

[View full changelog ->](0.2.0.md)

## 0.1.0 (December 21st, 2025)

- New client configuration options, including override volume per player or source.
- New client `close` method.
- FFmpeg processes pooled for performance.

[View full changelog ->](0.1.0.md)

## 0.0.1 (December 19th, 2025)

- Initial release.
- New `AudioBeginEvent` and `AudioEndEvent`.
- New audio queue system (player `previous`, `next`, `add_queue`, `remove_queue`, `clear_queue`, `queue`, and `history`).
- New player `shuffle` method.
- Removed `VoiceActiveEvent`, `VoiceInactiveEvent`, `VoicePopulatedEvent`, and `VoiceEmptyEvent`.
- New `BufferAudioSource` and `URLAudioSource`.
- Support for `aead_aes256_gcm_rtpsize` encryption mode.
- `Result` returns from player methods.
- New player `is_playing` property.
- New client `move` method.
- FFmpeg processes now independent of connections.

[View full changelog ->](0.0.1.md)
