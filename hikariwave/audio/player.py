from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import auto, IntEnum
from hikariwave.audio.source import AudioSource
from hikariwave.audio.store import FrameStore
from hikariwave.event.types import AudioBeginOrigin, WaveEventType
from hikariwave.internal.constants import Audio
from hikariwave.internal.result import Result, ResultReason
from typing import Any, Callable, Coroutine, TYPE_CHECKING

import asyncio
import logging
import random
import struct
import time

if TYPE_CHECKING:
    from hikariwave.connection import VoiceConnection

__all__ = ("AudioPlayer",)

logger: logging.Logger = logging.getLogger("hikariwave.player")

@dataclass(frozen=True, slots=True)
class QueuedAudio:
    """Audio metadata in player queue."""

    source: AudioSource
    """The audio source to play from."""
    origin: AudioBeginOrigin
    """The beginning origin of this audio."""

class AudioPlaybackState(IntEnum):
    """The current state of the player's playback."""

    BUFFERING = auto()
    """The player is loading the current audio."""
    IDLE = auto()
    """The player is not currently playing any audio."""
    PAUSED = auto()
    """The player is currently paused."""
    PLAYING = auto()
    """The player is currently playing audio."""
    STOPPING = auto()
    """The player is stopping."""

_VALID_TRANSITIONS: dict[AudioPlaybackState, set[AudioPlaybackState]] = {
    AudioPlaybackState.IDLE: {AudioPlaybackState.BUFFERING},
    AudioPlaybackState.BUFFERING: {AudioPlaybackState.PLAYING, AudioPlaybackState.IDLE},
    AudioPlaybackState.PLAYING: {AudioPlaybackState.PAUSED, AudioPlaybackState.STOPPING},
    AudioPlaybackState.PAUSED: {AudioPlaybackState.PLAYING, AudioPlaybackState.STOPPING},
    AudioPlaybackState.STOPPING: {AudioPlaybackState.IDLE},
}

class AudioPlayer:
    """Responsible for all audio."""

    __slots__ = (
        "_connection", "_store",
        "_state",
        "_sequence", "_timestamp", "_nonce", "_frames",
        "_queue", "_history", "_priority_source", "_current",
        "_player_task", "_lock",
        "_volume", "_priority",
        "_stop_event", "_skip_event", "_resume_event",
    )

    def __init__(self, connection: VoiceConnection) -> None:
        """
        Create a new audio player.
        
        Parameters
        ----------
        connection : VoiceConnection
            The active voice connection.
        """
        
        self._connection: VoiceConnection = connection
        self._store: FrameStore = FrameStore(self._connection)

        self._state: AudioPlaybackState = AudioPlaybackState.IDLE

        self._sequence: int = 0
        self._timestamp: int = 0
        self._nonce: int = 0
        self._frames: int = 0

        self._queue: deque[QueuedAudio] = deque(maxlen=self._connection._config.max_queue)
        self._history: deque[AudioSource] = deque(maxlen=self._connection._config.max_history)
        self._priority_source: AudioSource = None
        self._current: AudioSource = None

        self._player_task: asyncio.Task = None
        self._lock: asyncio.Lock = asyncio.Lock()

        self._volume: float | str | None = None
        self._priority: bool = False

        self._stop_event: asyncio.Event = asyncio.Event()
        self._skip_event: asyncio.Event = asyncio.Event()
        self._resume_event: asyncio.Event = asyncio.Event()
        self._resume_event.set()

    def _generate_rtp(self) -> bytes:
        header: bytearray = bytearray(12)
        header[0] = 0x80
        header[1] = 0x78
        struct.pack_into(">H", header, 2, self._sequence)
        struct.pack_into(">I", header, 4, self._timestamp)
        struct.pack_into(">I", header, 8, self._connection._ssrc)

        return bytes(header)

    async def _play_internal(self, source: AudioSource, origin: AudioBeginOrigin) -> bool:
        completed: bool = False

        try:
            self._stop_event.clear()
            self._skip_event.clear()
            setattr(source, "_volume", getattr(source, "_volume", None) or self._volume)

            await self._connection._client._ffmpeg.submit(source, self._connection)
            await self._store.wait()
            
            self._set_state(AudioPlaybackState.PLAYING)
            await self._connection._gateway.set_speaking(True, self._priority)
            
            self._connection._client._event_factory.emit(
                WaveEventType.AUDIO_BEGIN,
                self._connection._channel_id,
                self._connection._guild_id,
                source,
                origin,
            )

            frame_duration: float = Audio.FRAME_LENGTH / 1000
            frames_per_second: int = round(1 / frame_duration)
            last_second: int = -1

            self._frames: int = 0
            start_time: float = time.perf_counter()

            while not self._stop_event.is_set() and not self._skip_event.is_set():
                if not self._resume_event.is_set():
                    await asyncio.sleep(0.01)
                    continue

                opus: bytes = await self._store.fetch_frame()
                if opus is None:
                    completed = True
                    return True

                header: bytes = self._generate_rtp()
                encrypted: bytes = self._connection._mode(
                    self._connection._secret,
                    self._nonce,
                    header,
                    opus
                )
                await self._connection._server.send(encrypted)

                self._sequence = (self._sequence + 1) % Audio.BIT_16U
                self._timestamp = (self._timestamp + Audio.SAMPLES_PER_FRAME) % Audio.BIT_32U
                self._frames += 1
                
                target: float = start_time + (self._frames * frame_duration)
                sleep: float = target - time.perf_counter()

                if sleep > 0:
                    await asyncio.sleep(sleep)
                elif sleep < -0.020:
                    logger.debug(f"Frame {self._frames} is {-sleep:.3f}s behind schedule")
                
                elapsed_seconds: int = self._frames // frames_per_second
                if elapsed_seconds > last_second:
                    last_second = elapsed_seconds

                    self._connection._client._event_factory.emit(
                        WaveEventType.AUDIO_SECOND,
                        self._connection._channel_id,
                        self._connection._guild_id,
                        source,
                        elapsed_seconds,
                    )
        finally:
            if self._state == AudioPlaybackState.BUFFERING:
                self._set_state(AudioPlaybackState.IDLE)
        
        return completed

    async def _player_loop(self) -> None:
        try:
            while True:
                self._set_state(AudioPlaybackState.BUFFERING)

                async with self._lock:
                    if self._priority_source:
                        source = self._priority_source
                        origin = AudioBeginOrigin.PLAY
                        self._priority_source = None
                    elif self._queue:
                        queued: QueuedAudio = self._queue.popleft()
                        source = queued.source
                        origin = queued.origin
                    else:
                        self._current = None
                        self._set_state(AudioPlaybackState.IDLE)

                        return
                
                    self._current = source
                
                await self._store.clear()
                completed: bool = await self._play_internal(source, origin)
                await self._connection._gateway.set_speaking(False)

                async with self._lock:
                    self._set_state(AudioPlaybackState.STOPPING)

                    if completed:
                        self._history.append(source)

                    ended: AudioSource = self._current
                    self._current = None
                    self._set_state(AudioPlaybackState.IDLE)

                    self._connection._client._event_factory.emit(
                        WaveEventType.AUDIO_END,
                        self._connection._channel_id,
                        self._connection._guild_id,
                        ended,
                    )
        except asyncio.CancelledError:
            pass

    async def _send_silence(self) -> None:
        send: Callable[[bytes], Coroutine[Any, Any, None]] = self._connection._server.send
        for _ in range(5):
            await send(b"\xF8\xFF\xFE")

    def _set_state(self, state: AudioPlaybackState) -> None:
        if state not in _VALID_TRANSITIONS[self._state]:
            error: str = f"Invalid state transition: {self._state.name} -> {state.name}"
            raise RuntimeError(error)
        
        self._state = state

    async def add_queue(self, source: AudioSource) -> Result:
        """
        Add an audio source to the queue.
        
        Parameters
        ----------
        source : AudioSource
            The source of the audio to add.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.

        Raises
        ------
        TypeError
            If the provided source doesn't inherit `AudioSource`.
        """

        if not isinstance(source, AudioSource):
            error: str = "Provided audio source doesn't inherit from `AudioSource`"
            raise TypeError(error)

        async with self._lock:
            self._queue.append(QueuedAudio(source, AudioBeginOrigin.QUEUE))

            if not self._player_task or self._player_task.done():
                self._player_task = asyncio.create_task(self._player_loop())
        
        return Result.succeeded()

    async def clear_queue(self) -> Result:
        """
        Clear all audio from the queue.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """

        async with self._lock:
            if len(self._queue) < 1:
                return Result.failed(ResultReason.EMPTY_QUEUE)
            
            self._queue.clear()
        
        return Result.succeeded()

    @property
    def connection(self) -> VoiceConnection:
        """The active connection that is responsible for this player."""
        return self._connection

    @property
    def current(self) -> AudioSource | None:
        """The currently playing audio, if present."""
        return self._current

    @property
    def elapsed(self) -> float:
        """The amount of seconds of the current audio that has been elapsed."""
        return self._frames * (Audio.FRAME_LENGTH / 1000)

    @property
    def history(self) -> list[AudioSource]:
        """Get all audio previously played."""

        return list(self._history)

    @property
    def is_playing(self) -> bool:
        """If the player has audio currently playing."""
        return self._state == AudioPlaybackState.PLAYING

    async def next(self) -> Result:
        """
        Play the next audio in queue.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """

        async with self._lock:
            if self._current is None:
                return Result.failed(ResultReason.NO_TRACK)
    
            if len(self._queue) < 1:
                return Result.failed(ResultReason.EMPTY_QUEUE)

            self._skip_event.set()
            self._resume_event.set()
        
        return Result.succeeded()

    async def pause(self) -> Result:
        """
        Pause the current audio.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """

        if self._current is None:
            return Result.failed(ResultReason.NO_TRACK)

        if not self._resume_event.is_set():
            return Result.failed(ResultReason.PAUSED)

        self._resume_event.clear()
        self._set_state(AudioPlaybackState.PAUSED)

        await self._send_silence()
        await self._connection._gateway.set_speaking(False, self._priority)
        
        return Result.succeeded()

    async def play(self, source: AudioSource) -> Result:
        """
        Play audio from a source.
        
        Parameters
        ----------
        source : AudioSource
            The source of the audio to play
        
        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.

        Raises
        ------
        TypeError
            If the provided source doesn't inherit `AudioSource`.
        """

        if not isinstance(source, AudioSource):
            error: str = "Provided source must inherit `AudioSource`"
            raise TypeError(error)

        async with self._lock:
            self._priority_source = source

            if self._current is not None:
                self._skip_event.set()

            if not self._player_task or self._player_task.done():
                self._player_task = asyncio.create_task(self._player_loop())
        
        return Result.succeeded()

    async def previous(self) -> Result:
        """
        Play the latest previously played audio.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """

        async with self._lock:
            if len(self._history) < 1:
                return Result.failed(ResultReason.EMPTY_HISTORY)
            
            previous: AudioSource = self._history.pop()
            self._queue.appendleft(QueuedAudio(previous, AudioBeginOrigin.HISTORY))

            if self._current:
                self._skip_event.set()
                self._resume_event.set()
            
        return Result.succeeded()

    @property
    def progress(self) -> float:
        """Percentage of the current audio that has been completed (`0.0`-`1.0`)."""

        if self._current is None:
            return 0.0
        
        duration: float = getattr(self._current, "duration", None)
        if not duration:
            return 0.0
        
        return min(1.0, self.elapsed / duration)

    @property
    def queue(self) -> list[AudioSource]:
        """Get all audio currently in queue."""

        return [audio.source for audio in self._queue]

    @property
    def remaining(self) -> float:
        """The amount of seconds remaining for the current audio."""
        
        if self._current is None:
            return 0.0
        
        duration: float = getattr(self._current, "duration", None)
        if duration is None:
            return 0.0
        
        return max(0.0, duration - self.elapsed)

    async def remove_queue(self, source: AudioSource) -> Result:
        """
        Remove an audio source from the queue.
        
        Parameters
        ----------
        source : AudioSource
            The source of the audio to remove.
        
        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        
        Raises
        ------
        TypeError
            If the provided source doesn't inherit `AudioSource`.
        """

        if not isinstance(source, AudioSource):
            error: str = "Provided source must inherit `AudioSource`"
            raise TypeError(error)

        async with self._lock:
            found: bool = False

            for audio in self._queue:
                if audio.source != source:
                    continue

                self._queue.remove(audio)
                found = True
                break

            if not found:
                return Result.failed(ResultReason.NOT_FOUND)
        
        return Result.succeeded()

    async def resume(self) -> Result:
        """
        Resume the current audio.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """
        
        if self._resume_event.is_set():
            return Result.failed(ResultReason.PLAYING)

        await self._connection._gateway.set_speaking(True, self._priority)
        
        self._resume_event.set()
        self._set_state(AudioPlaybackState.PLAYING)
        return Result.succeeded()

    def set_priority(self, priority: bool) -> None:
        """
        Set if this player should play with priority voice enabled.
        
        Parameters
        ----------
        priority : bool 
            If the player should playback this audio with a prioritized speaking status.
        
        Raises
        ------
        TypeError
            If `priority` isn't `bool`.
        """

        if not isinstance(priority, bool):
            error: str = "Provided priority must be `bool`"
            raise TypeError(error)
        
        self._priority = priority

    def set_volume(self, volume: float | str | None = None) -> None:
        """
        Set the default volume of this player.
        Can be `None`, any scaled value (`1.0`, `2.0`, `0.5`, etc.) or dB-based (`-3dB`, `0.5dB`, etc.).
        
        Parameters
        ----------
        volume : float | str | None
            The volume to set as a default for this player - `None` uses connection/client configuration.
        
        Raises
        ------
        TypeError
            If `volume` is provided and it's not `float`, `int`, or `str`.
        """

        if volume is not None and not isinstance(volume, (float, int, str)):
            error: str = "Provided volume must be a `float`, `int`, or `str`"
            raise TypeError(error)
        
        self._volume = volume if volume is not None else self._connection._config._volume

    async def shuffle(self) -> Result:
        """
        Shuffle all audio currently in queue.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """

        async with self._lock:
            if len(self._queue) < 1:
                return Result.failed(ResultReason.EMPTY_QUEUE)
            
            temp: list[QueuedAudio] = list(self._queue)
            random.shuffle(temp)
            self._queue.clear()
            self._queue.extend(temp)
        
        return Result.succeeded()

    @property
    def state(self) -> AudioPlaybackState:
        """The current state of this player."""
        return self._state

    async def stop(self) -> Result:
        """
        Stop the current audio.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """
        
        self._stop_event.set()
        self._skip_event.set()
        self._resume_event.set()

        async with self._lock:
            self._queue.clear()
            self._priority_source = None
            self._current = None
        
        await self._connection._gateway.set_speaking(False, self._priority)
        await self._store.clear()

        return Result.succeeded()
    
    @property
    def volume(self) -> float | str | None:
        """If set, the player's default volume."""
        return self._volume