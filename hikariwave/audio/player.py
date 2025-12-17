from __future__ import annotations

from collections import deque
from hikariwave.audio.source import AudioSource, FileAudioSource
from hikariwave.constants import Audio
from hikariwave.event.types import WaveEventType
from typing import TYPE_CHECKING

import asyncio
import logging
import nacl.secret as secret
import random
import struct
import time

if TYPE_CHECKING:
    from hikariwave.connection import VoiceConnection

logger: logging.Logger = logging.getLogger("hikariwave.player")

class AudioPlayer:
    """Responsible for all audio."""

    def __init__(self, connection: VoiceConnection, max_history: int = 20) -> None:
        """
        Create a new audio player.
        
        Parameters
        ----------
        connection : VoiceConnection
            The active voice connection.
        max_history : int
            Maximum number of tracks to keep in history - Default `20`.
        """
        
        self._connection: VoiceConnection = connection

        self._ended: asyncio.Event = asyncio.Event()
        self._skip: asyncio.Event = asyncio.Event()
        self._resumed: asyncio.Event = asyncio.Event()
        self._resumed.set()

        self._sequence: int = 0
        self._timestamp: int = 0
        self._nonce: int = 0

        self._queue: deque[AudioSource] = deque()
        self._history: deque[AudioSource] = deque(maxlen=max_history)
        self._direct_source: AudioSource = None
        self._current: AudioSource = None

        self._player_task: asyncio.Task = None
        self._lock: asyncio.Lock = asyncio.Lock()

        self._track_completed: bool = False

    def _encrypt_aead_xchacha20_poly1305_rtpsize(self, header: bytes, audio: bytes) -> bytes:
        box: secret.Aead = secret.Aead(self._connection._secret)

        nonce: bytearray = bytearray(24)
        nonce[:4] = struct.pack(">I", self._nonce)

        self._nonce = (self._nonce + 1) % Audio.BIT_32U

        return header + box.encrypt(audio, header, bytes(nonce)).ciphertext + nonce[:4]

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

        try:
            await self._connection._gateway.set_speaking(True)
    
            if isinstance(source, FileAudioSource):
                await self._connection._client._ffmpeg.start(source._filepath)
            else:
                await self._connection._client._ffmpeg.start(await source.read())
            
            self._connection._client._event_factory.emit(
                WaveEventType.AUDIO_BEGIN,
                self._connection._channel_id,
                self._connection._guild_id,
                source,
            )
            
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

                opus: bytes = await self._connection._client._ffmpeg.read()

                if not opus:
                    self._track_completed = True
                    break

                header: bytes = self._generate_rtp()
                encrypted: bytes = getattr(self, f"_encrypt_{self._connection._mode}")(header, opus)
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
        except Exception as e:
            logger.error(f"Error during playback: {e}")
            return False
        finally:        
            try:
                await self._connection._client._ffmpeg.stop()
                await self._send_silence()
                await self._connection._gateway.set_speaking(False)
            except Exception as e:
                logger.error(f"Error in playback cleanup: {e}")

    async def _player_loop(self) -> None:
        while True:
            source: AudioSource = None

            async with self._lock:
                if self._direct_source:
                    source = self._direct_source
                    self._direct_source = None
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
        for _ in range(5): await self._connection._server.send(b"\xF8\xFF\xFE")

    async def add_queue(self, source: AudioSource) -> None:
        """
        Add an audio source to the queue.
        
        Parameters
        ----------
        source : AudioSource
            The source of the audio to add.
        """

        async with self._lock:
            self._queue.append(source)

            if not self._player_task or self._player_task.done():
                self._player_task = asyncio.create_task(self._player_loop())

    async def clear_queue(self) -> None:
        """
        Clear all audio from the queue.
        """

        async with self._lock:
            self._queue.clear()

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

    async def next(self) -> None:
        """
        Play the next audio in queue.
        """

        async with self._lock:
            if self._current is None:
                return
    
            self._skip.set()

    async def pause(self) -> None:
        """
        Pause the current audio.
        """

        self._resumed.clear()

        try:
            await self._connection._gateway.set_speaking(False)
        except Exception as e:
            logger.error(f"Error setting speaking state in pause: {e}")

    async def play(self, source: AudioSource) -> None:
        """
        Play audio from a source.
        
        Parameters
        ----------
        source : AudioSource
            The source of the audio to play
        """

        async with self._lock:
            self._direct_source = source

            if self._current is not None:
                self._skip.set()

            if not self._player_task or self._player_task.done():
                self._player_task = asyncio.create_task(self._player_loop())

    async def previous(self) -> None:
        """
        Play the latest previously played audio.
        """

        async with self._lock:
            if not self._history:
                return
            
            previous: AudioSource = self._history.pop()

            self._queue.appendleft(previous)

            if self._current is not None:
                self._skip.set()

    @property
    def queue(self) -> list[AudioSource]:
        """Get all audio currently in queue."""

        return list(self._queue)

    async def remove_queue(self, source: AudioSource) -> None:
        """
        Remove an audio source from the queue.
        
        Parameters
        ----------
        source : AudioSource
            The source of the audio to remove.
        """

        async with self._lock:
            try:
                self._queue.remove(source)
            except ValueError:
                pass

    async def resume(self) -> None:
        """
        Resume the current audio.
        """
        
        try:
            await self._connection._gateway.set_speaking(True)
        except Exception as e:
            logger.error(f"Error setting speaking state in resume: {e}")
        
        self._resumed.set()

    async def shuffle(self) -> None:
        """
        Shuffle all audio currently in queue.
        """

        async with self._lock:
            temp: list[AudioSource] = list(self._queue)
            random.shuffle(temp)
            self._queue.clear()
            self._queue.extend(temp)

    async def stop(self) -> None:
        """
        Stop the current audio.
        """
        
        async with self._lock:
            self._queue.clear()
            self._direct_source = None
            self._current = None
        
        self._ended.set()
        self._skip.set()
        self._resumed.set()

        try:
            await self._connection._gateway.set_speaking(False)
        except Exception as e:
            logger.error(f"Error setting speaking state in stop: {e}")