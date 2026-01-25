from __future__ import annotations

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from hikariwave.internal.constants import Audio

import nacl.secret as secret
import struct

__all__ = ()

class Encrypt:
    """Container class for all supported, non-deprecated encryption modes."""

    SUPPORTED: tuple[str, ...] = ("aead_aes256_gcm_rtpsize", "aead_xchacha20_poly1305_rtpsize",)
    """A list of all currently supported, non-deprecated, complete, and tested encryption modes."""

    @staticmethod
    def decrypt_aead_aes256_gcm_rtpsize(secret_key: bytes, audio: bytes) -> bytes:
        """
        Decrypt audio using `aead_aes256_gcm_rtpsize`.

        Parameters
        ----------
        secret_key : bytes
            32-byte AES encryption key provided by Discord.
        audio : bytes
            Opus audio payload.

        Returns
        -------
        bytes
            The decrypted audio packet.
        """

        header_size = 12

        if (audio[0] & 0x10) != 0:
            header_size = 16

        decrypted: bytes = AESGCM(secret_key).decrypt(
            audio[-4:] + (b"\x00" * 8),
            audio[header_size:-4],
            audio[:header_size],
        )

        if (audio[0] & 0x10) != 0:
            return decrypted[struct.unpack(">H", audio[14:16])[0] * 4:]

        return decrypted

    @staticmethod
    def decrypt_aead_xchacha20_poly1305_rtpsize(secret_key: bytes, audio: bytes) -> bytes:
        """
        Decrypt audio using `aead_xchacha20_poly1305_rtpsize`.

        Parameters
        ----------
        secret_key : bytes
            32-byte AES encryption key provided by Discord.
        audio : bytes
            Opus audio payload.

        Returns
        -------
        bytes
            The decrypted audio packet.
        """

        header_size = 12

        if (audio[0] & 0x10) != 0:
            header_size = 16

        nonce: bytearray = bytearray(24)
        nonce[:4] = audio[-4:]

        decrypted: bytes = secret.Aead(secret_key).decrypt(
            audio[header_size:-4],
            audio[:header_size],
            bytes(nonce),
        )

        if (audio[0] & 0x10) != 0:
            return decrypted[struct.unpack(">H", audio[14:16])[0] * 4:]

        return decrypted

    @staticmethod
    def encrypt_aead_aes256_gcm_rtpsize(secret_key: bytes, nonce: int, header: bytes, audio: bytes) -> bytes:
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

        packet_nonce: bytes = struct.pack("<I", nonce) + (b"\x00" * 8)
        nonce = (nonce + 1) % Audio.BIT_32U

        return header + AESGCM(secret_key).encrypt(packet_nonce, audio, header) + packet_nonce[:4]

    @staticmethod
    def encrypt_aead_xchacha20_poly1305_rtpsize(secret_key: bytes, nonce: int, header: bytes, audio: bytes) -> bytes:
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

        packet_nonce: bytearray = bytearray(24)
        packet_nonce[:4] = struct.pack("<I", nonce)
        nonce = (nonce + 1) % Audio.BIT_32U

        return header + secret.Aead(secret_key).encrypt(audio, header, bytes(packet_nonce)).ciphertext + packet_nonce[:4]
