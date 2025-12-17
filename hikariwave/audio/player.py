from __future__ import annotations

from collections import deque
from hikariwave.audio.source import AudioSource, FileAudioSource
from hikariwave.constants import Audio
from hikariwave.event.types import WaveEventType
from typing import TYPE_CHECKING

import asyncio
import logging
import nacl.secret as secret
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
        
        self.connection: VoiceConnection = connection

        self._ended: asyncio.Event = asyncio.Event()
        self._skip: asyncio.Event = asyncio.Event()
        self._resumed: asyncio.Event = asyncio.Event()
        self._resumed.set()

        self.sequence: int = 0
        self.timestamp: int = 0
        self.nonce: int = 0

        self._queue: deque[AudioSource] = deque()
        self._history: deque[AudioSource] = deque(maxlen=max_history)
        self._direct_source: AudioSource = None
        self.current: AudioSource = None

        self._player_task: asyncio.Task = None
        self._lock: asyncio.Lock = asyncio.Lock()

        self._track_completed: bool = False

    def _encrypt_aead_xchacha20_poly1305_rtpsize(self, header: bytes, audio: bytes) -> bytes:
        box: secret.Aead = secret.Aead(self.connection.secret)

        nonce: bytearray = bytearray(24)
        nonce[:4] = struct.pack(">I", self.nonce)

        self.nonce = (self.nonce + 1) % Audio.BIT_32U

        return header + box.encrypt(audio, header, bytes(nonce)).ciphertext + nonce[:4]

    def _generate_rtp(self) -> bytes:
        header: bytearray = bytearray(12)
        header[0] = 0x80
        header[1] = 0x78
        struct.pack_into(">H", header, 2, self.sequence)
        struct.pack_into(">I", header, 4, self.timestamp)
        struct.pack_into(">I", header, 8, self.connection.ssrc)

        return bytes(header)

    async def _play_internal(self, source: AudioSource) -> bool:
        self._ended.clear()
        self._skip.clear()
        self._track_completed = False

        try:
            await self.connection.gateway.set_speaking(True)
    
            if isinstance(source, FileAudioSource):
                await self.connection.client.ffmpeg.start(source.filepath)
            else:
                await self.connection.client.ffmpeg.start(await source.read())
            
            self.connection.client.event_factory.emit(
                WaveEventType.AUDIO_BEGIN,
                self.connection.channel_id,
                self.connection.guild_id,
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

                pcm: bytes = await self.connection.client.ffmpeg.decode(Audio.FRAME_SIZE)

                if not pcm or len(pcm) < Audio.FRAME_SIZE:
                    self._track_completed = True
                    break

                opus: bytes = await self.connection.client.opus.encode(pcm)

                if not opus:
                    break

                header: bytes = self._generate_rtp()
                encrypted: bytes = getattr(self, f"_encrypt_{self.connection.mode}")(header, opus)
                await self.connection.server.send(encrypted)

                self.sequence = (self.sequence + 1) % Audio.BIT_16U
                self.timestamp = (self.timestamp + Audio.SAMPLES_PER_FRAME) % Audio.BIT_32U
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
                await self._send_silence()
                await self.connection.gateway.set_speaking(False)
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
                    self.current = None
                    self._player_task = None
                    return
            
                self.current = source
            
            completed: bool = await self._play_internal(source)

            async with self._lock:
                self.connection.client.event_factory.emit(
                    WaveEventType.AUDIO_END,
                    self.connection.channel_id,
                    self.connection.guild_id,
                    self.current,
                )

                if completed or (self._skip.is_set() and not self._ended.is_set()):
                    self._history.append(source)

    async def _send_silence(self) -> None:
        for _ in range(5): await self.connection.server.send(b"\xF8\xFF\xFE")

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
    def history(self) -> list[AudioSource]:
        """Get all audio previously played."""

        return list(self._history)

    async def next(self) -> None:
        """
        Play the next audio in queue.
        """

        async with self._lock:
            if self.current is None:
                return
    
            self._skip.set()

    async def pause(self) -> None:
        """
        Pause the current audio.
        """

        self._resumed.clear()

        try:
            await self.connection.gateway.set_speaking(False)
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

            if self.current is not None:
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

            if self.current is not None:
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
            await self.connection.gateway.set_speaking(True)
        except Exception as e:
            logger.error(f"Error setting speaking state in resume: {e}")
        
        self._resumed.set()

    async def stop(self) -> None:
        """
        Stop the current audio.
        """
        
        async with self._lock:
            self._queue.clear()
            self._direct_source = None
            self.current = None
        
        self._ended.set()
        self._skip.set()
        self._resumed.set()

        try:
            await self.connection.gateway.set_speaking(False)
        except Exception as e:
            logger.error(f"Error setting speaking state in stop: {e}")