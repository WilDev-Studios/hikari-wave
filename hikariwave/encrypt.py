from __future__ import annotations

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from hikariwave.constants import Audio

import nacl.secret as secret
import struct

__all__ = ("Encrypt",)

class Encrypt:
    """Container class for all supported, non-deprecated encryption modes."""

    @staticmethod
    def aead_aes256_gcm_rtpsize(secret_key: bytes, nonce: int, header: bytes, audio: bytes) -> bytes:
        """
        Encrypt audio using `aead_aes256_gcm_rtpsize`.
        
        Parameters
        ----------
        secret_key : bytes
            32-byte AES encryption key provided by Discord.
        nonce : int
            32-bit packet counter.
        header : bytes
            RTP header (12 bytes).
        audio : bytes
            Opus audio payload.
        
        Returns
        -------
        bytes
            The encrypted audio packet.
        """

        aesgcm: AESGCM = AESGCM(secret_key)

        packet_nonce: bytes = struct.pack(">I", nonce) + b"\x00" * 8
        nonce = (nonce + 1) % Audio.BIT_32U

        encrypted: bytes = aesgcm.encrypt(packet_nonce, audio, header)

        return header + encrypted + packet_nonce[8:]

    @staticmethod
    def aead_xchacha20_poly1305_rtpsize(secret_key: bytes, nonce: int, header: bytes, audio: bytes) -> bytes:
        """
        Encrypt audio using `aead_xchacha20_poly1305_rtpsize`.
        
        Parameters
        ----------
        secret_key : bytes
            32-byte AES encryption key provided by Discord.
        nonce : int
            32-bit packet counter.
        header : bytes
            RTP header (12 bytes).
        audio : bytes
            Opus audio payload.
        
        Returns
        -------
        bytes
            The encrypted audio packet.
        """
        
        box: secret.Aead = secret.Aead(secret_key)

        packet_nonce: bytearray = bytearray(24)
        packet_nonce[:4] = struct.pack(">I", nonce)
        nonce = (nonce + 1) % Audio.BIT_32U

        return header + box.encrypt(audio, header, bytes(packet_nonce)).ciphertext + packet_nonce[:4]