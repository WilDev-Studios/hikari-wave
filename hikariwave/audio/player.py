from __future__ import annotations

from hikariwave.constants import Audio
from hikariwave.audio.source import AudioSource, FileAudioSource
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

    def __init__(self, connection: VoiceConnection) -> None:
        """
        Create a new audio player.
        
        Parameters
        ----------
        connection : VoiceConnection
            The active voice connection.
        """
        
        self.connection: VoiceConnection = connection

        self.ended: asyncio.Event = asyncio.Event()
        self.resumed: asyncio.Event = asyncio.Event()
        self.resumed.set()

        self.sequence: int = 0
        self.timestamp: int = 0
        self.nonce: int = 0

        self.play_task: asyncio.Task = None
    
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

    async def _play_internal(self, source: AudioSource) -> None:
        self.ended.clear()

        try:
            await self.connection.gateway.set_speaking(True)
    
            if isinstance(source, FileAudioSource):
                await self.connection.client.ffmpeg.start(source.filepath)
            else:
                await self.connection.client.ffmpeg.start(await source.read())
            
            frame_duration: float = Audio.FRAME_LENGTH / 1000
            frame_count: int = 0
            start_time: float = time.perf_counter()

            while not self.ended.is_set():
                if not self.resumed.is_set():
                    await self._send_silence()
                    await self.resumed.wait()

                    frame_count = 0
                    start_time = time.perf_counter()
                    continue

                pcm: bytes = await self.connection.client.ffmpeg.decode(Audio.FRAME_SIZE)

                if not pcm or len(pcm) < Audio.FRAME_SIZE:
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

                next_frame_time: float = start_time + (frame_count * frame_duration)
                current_time: float = time.perf_counter()
                sleep_time: float = next_frame_time - current_time

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                elif sleep_time < -0.020:
                    logger.debug(f"Frame {frame_count} is {-sleep_time:.3f}s behind schedule")
        finally:
            try:
                await self._send_silence()
            except:...

            try:
                await self.connection.gateway.set_speaking(False)
            except:...

    async def _send_silence(self) -> None:
        for _ in range(5): await self.connection.server.send(b"\xF8\xFF\xFE")

    async def pause(self) -> None:
        """
        Pause the current audio.
        """

        self.resumed.clear()
        await self.connection.gateway.set_speaking(False)

    async def play(self, source: AudioSource) -> None:
        """
        Play audio from a source.
        
        Parameters
        ----------
        source : AudioSource
            The source of the audio to play.
        """
        
        if self.play_task and not self.play_task.done():
            await self.stop()

            try:
                await asyncio.wait_for(self.play_task, 1)
            except:...

            await asyncio.sleep(0.05)
        
        self.play_task = asyncio.create_task(self._play_internal(source))
        await self.play_task
    
    async def resume(self) -> None:
        """
        Resume the current audio.
        """
        
        await self.connection.gateway.set_speaking(True)
        self.resumed.set()

    async def stop(self) -> None:
        """
        Stop the current audio.
        """
        
        self.ended.set()
        self.resumed.set()

        await self.connection.gateway.set_speaking(False)