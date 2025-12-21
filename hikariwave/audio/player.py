from __future__ import annotations

from collections import deque
from hikariwave.audio.source import AudioSource
from hikariwave.audio.store import FrameStore
from hikariwave.event.types import WaveEventType
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

class AudioPlayer:
    """Responsible for all audio."""

    __slots__ = (
        "_connection", "_store", "_ended", "_skip", "_resumed",
        "_sequence", "_timestamp", "_nonce",
        "_queue", "_history", "_priority_source", "_current",
        "_player_task", "_lock", "_track_completed", "_volume",
    )

    def __init__(self, connection: VoiceConnection, max_history: int = 20) -> None:
        """
        Create a new audio player.
        
        Parameters
        ----------
        connection : VoiceConnection
            The active voice connection.
        max_history : int
            Maximum number of tracks to keep in history.
        """
        
        self._connection: VoiceConnection = connection
        self._store: FrameStore = FrameStore(False) # until further tested and functional

        self._ended: asyncio.Event = asyncio.Event()
        self._skip: asyncio.Event = asyncio.Event()
        self._resumed: asyncio.Event = asyncio.Event()
        self._resumed.set()

        self._sequence: int = 0
        self._timestamp: int = 0
        self._nonce: int = 0

        self._queue: deque[AudioSource] = deque()
        self._history: deque[AudioSource] = deque(maxlen=max_history)
        self._priority_source: AudioSource = None
        self._current: AudioSource = None

        self._player_task: asyncio.Task = None
        self._lock: asyncio.Lock = asyncio.Lock()

        self._track_completed: bool = False
        self._volume: float | str | None = None

    def _generate_rtp(self) -> bytes:
        header: bytearray = bytearray(12)
        header[0] = 0x80
        header[1] = 0x78
        struct.pack_into(">H", header, 2, self._sequence)
        struct.pack_into(">I", header, 4, self._timestamp)
        struct.pack_into(">I", header, 8, self._connection._ssrc)

        return bytes(header)

    async def _play_internal(self, source: AudioSource) -> bool:
        self._ended.clear()
        self._skip.clear()
        self._track_completed = False

        source._volume = source._volume or self._volume

        await self._connection._gateway.set_speaking(True)
        await self._connection._client._ffmpeg.submit(source, self._store)
        
        self._connection._client._event_factory.emit(
            WaveEventType.AUDIO_BEGIN,
            self._connection._channel_id,
            self._connection._guild_id,
            source,
        )
        
        await self._store.wait()

        frame_duration: float = Audio.FRAME_LENGTH / 1000
        frame_count: int = 0
        start_time: float = time.perf_counter()

        while not self._ended.is_set() and not self._skip.is_set():
            if not self._resumed.is_set():
                await self._send_silence()
                await self._resumed.wait()

                frame_count = 0
                start_time = time.perf_counter()
                continue

            opus: bytes = await self._store.fetch_frame()
            if opus is None:
                self._track_completed = True
                break

            header: bytes = self._generate_rtp()
            encrypted: bytes = self._connection._mode(self._connection._secret, self._nonce, header, opus)
            await self._connection._server.send(encrypted)

            self._sequence = (self._sequence + 1) % Audio.BIT_16U
            self._timestamp = (self._timestamp + Audio.SAMPLES_PER_FRAME) % Audio.BIT_32U
            frame_count += 1

            target: float = start_time + (frame_count * frame_duration)
            sleep: float = target - time.perf_counter()

            if sleep > 0:
                await asyncio.sleep(sleep)
            elif sleep < -0.020:
                logger.debug(f"Frame {frame_count} is {-sleep:.3f}s behind schedule")
        
        if self._skip.is_set() and not self._ended.is_set():
            self._track_completed = False

        await self._send_silence()
        await self._connection._gateway.set_speaking(False)

        return self._track_completed

    async def _player_loop(self) -> None:
        while True:
            source: AudioSource = None

            async with self._lock:
                if self._priority_source:
                    source = self._priority_source
                    self._priority_source = None
                elif self._queue:
                    source = self._queue.popleft()
                else:
                    self._current = None
                    self._player_task = None
                    return
            
                self._current = source
            
            completed: bool = await self._play_internal(source)

            async with self._lock:
                self._connection._client._event_factory.emit(
                    WaveEventType.AUDIO_END,
                    self._connection._channel_id,
                    self._connection._guild_id,
                    self._current,
                )

                if completed or (self._skip.is_set() and not self._ended.is_set()):
                    self._history.append(source)

    async def _send_silence(self) -> None:
        send: Callable[[bytes], Coroutine[Any, Any, None]] = self._connection._server.send
        for _ in range(5):
            await send(b"\xF8\xFF\xFE")

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
            self._queue.append(source)

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
    def history(self) -> list[AudioSource]:
        """Get all audio previously played."""

        return list(self._history)

    @property
    def is_playing(self) -> bool:
        """If the player has audio currently playing."""
        return self._current is not None and self._resumed.is_set()

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

            self._skip.set()
            self._resumed.set()
        
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

        if not self._resumed.is_set():
            return Result.failed(ResultReason.PAUSED)

        self._resumed.clear()

        await self._connection._gateway.set_speaking(False)
        
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
                self._skip.set()

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
            self._queue.appendleft(previous)

            if self._current:
                self._skip.set()
                self._resumed.set()
            
        return Result.succeeded()

    @property
    def queue(self) -> list[AudioSource]:
        """Get all audio currently in queue."""

        return list(self._queue)

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
            try:
                self._queue.remove(source)
            except ValueError:
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
        
        if self._resumed.is_set():
            return Result.failed(ResultReason.PLAYING)

        await self._connection._gateway.set_speaking(True)
        
        self._resumed.set()
        return Result.succeeded()

    def set_volume(self, volume: float | str | None = None) -> None:
        """
        Set the default volume of this player.
        Can be `None`, any scaled value (`1.0`, `2.0`, `0.5`, etc.) or dB-based (`-3dB`, `0.5dB`, etc.).
        
        Parameters
        ----------
        volume : float | str | None
            The volume to set as a default for this player.
        
        Raises
        ------
        TypeError
            If `volume` is provided and it's not `float`, `int`, or `str`.
        """

        if volume is not None and not isinstance(volume, (float, int, str)):
            error: str = "Provided volume must be a `float`, `int`, or `str`"
            raise TypeError(error)
        
        self._volume = volume

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
            
            temp: list[AudioSource] = list(self._queue)
            random.shuffle(temp)
            self._queue.clear()
            self._queue.extend(temp)
        
        return Result.succeeded()

    async def stop(self) -> Result:
        """
        Stop the current audio.

        Returns
        -------
        Result
            If the operation was successful, with reason provided if otherwise.
        """
        
        self._ended.set()
        self._skip.set()
        self._resumed.set()

        async with self._lock:
            self._queue.clear()
            self._priority_source = None
            self._current = None
        
        await self._connection._gateway.set_speaking(False)
        
        return Result.succeeded()
    
    @property
    def volume(self) -> float | str | None:
        """If set, the player's default volume."""
        return self._volume