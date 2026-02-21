from __future__ import annotations

from dataclasses import dataclass
from hikariwave.internal.constants import Opcode
from hikariwave.internal.dev import log_exception
from hikariwave.internal.error import GatewayError
from typing import TYPE_CHECKING, TypeAlias

import davey
import logging
import struct

if TYPE_CHECKING:
    from hikariwave.networking.gateway import VoiceGateway

__all__ = ()

logger: logging.Logger = logging.getLogger("hikari-wave.dave")

TransitionID: TypeAlias = int
ProtocolVersion: TypeAlias = int

@dataclass(frozen=True, slots=True)
class DAVETransition:
    """Represents a pending `DAVE` protocol transition."""

    transition_id: int
    """The unique identifier for this transition."""
    epoch_id: int | None = None
    """The MLS epoch ID for epoch transitions - `None` for downgrades."""

class DAVEManager:
    """Manages `DAVE` protocol operations."""

    __slots__ = (
        "_gateway", "_session",
        "_pending_transitions",
        "_last_transition_id",
        "_protocol_version",
        "_downgraded",
    )

    def __init__(
        self,
        gateway: VoiceGateway,
    ) -> None:
        """
        Create a `DAVE` protocol manager.

        Parameters
        ----------
        gateway : VoiceGateway
            The voice gateway connection.
        """

        self._gateway: VoiceGateway = gateway
        self._session: davey.DaveSession | None = None

        self._pending_transitions: dict[TransitionID, ProtocolVersion] = {}
        self._last_transition_id: int | None = None
        self._protocol_version: int = 0
        self._downgraded: bool = False

    @staticmethod
    def parse_frame(frame: bytes) -> tuple[int, Opcode, bytes]:
        """
        Parse a `DAVE` frame into a sequence, opcode, and payload.

        Parameters
        ----------
        frame : bytes
            The raw payload from the gateway.

        Returns
        -------
        tuple[int, Opcode, bytes]
            The sequence, operation code, and payload from the frame.

        Raises
        ------
        GatewayError
            If the frame was too short to parse.
        """

        if len(frame) < 3:
            error: str = "DAVE binary frame too short"
            raise GatewayError(error)

        return *struct.unpack_from(">HB", frame, 0), frame[3:]

    async def __reinit(self) -> None:
        if self._protocol_version > 0:
            if self._session:
                self._session.reinit(self._protocol_version, int(self._gateway._connection._client._bot_id), int(self._gateway._connection._channel_id))
                logger.debug(f"Session reinitialized for protocol version {self._protocol_version}")
            else:
                self._session = davey.DaveSession(self._protocol_version, int(self._gateway._connection._client._bot_id), int(self._gateway._connection._channel_id))
                logger.debug(f"Session initialized for protocol version {self._protocol_version}")

            await self.__send_key_package()
        else:
            self._session.reset()
            self._session.set_passthrough_mode(True, 10)

            logger.debug("DAVE session reset")

    async def __send_commit_welcome(
        self,
        commit_welcome: davey.CommitWelcome,
    ) -> None:
        opcode_byte: bytes = bytes([Opcode.DAVE_MLS_COMMIT_WELCOME])
        commit_length: bytes = struct.pack(">H", len(commit_welcome.commit))

        payload: bytes = opcode_byte + commit_length + commit_welcome.commit

        if commit_welcome.welcome is not None:
            welcome_length: bytes = struct.pack(">H", len(commit_welcome.welcome))
            payload += welcome_length + commit_welcome.welcome
        else:
            payload += struct.pack(">H", 0)

        await self._gateway._websocket.send_bytes(payload)

    async def __send_invalid_commit_welcome(
        self,
    ) -> None:
        if self._session:
            self._session.reset()

        await self._gateway._websocket.send_json({
            "op": Opcode.DAVE_MLS_INVALID_COMMIT_WELCOME,
            'd': {},
        })

        await self.__send_key_package()

    async def __send_key_package(self) -> None:
        if not self._session:
            logger.warning("Cannot send key package: no DAVE session initialized")
            return

        key_package: bytes = self._session.get_serialized_key_package()
        opcode_byte: bytes = bytes([Opcode.DAVE_MLS_KEY_PACKAGE])

        await self._gateway._websocket.send_bytes(opcode_byte + key_package)

    async def __send_transition_ready(
        self,
        transition_id: int,
    ) -> None:
        await self._gateway._websocket.send_json({
            "op": Opcode.DAVE_TRANSITION_READY,
            'd': {
                "transition_id": transition_id,
            }
        })

    def decrypt(
        self,
        user_id: int,
        packet: bytes,
    ) -> bytes:
        """
        Decrypt a `DAVE` E2EE encrypted packet.

        Parameters
        ----------
        user_id : int
            The ID of the user that sent the packet.
        packet : bytes
            The encrypted audio packet.

        Returns
        -------
        bytes
            The decrypted packet - Untouched if `DAVE` not ready.
        """

        if not self.ready:
            return packet

        try:
            return self._session.decrypt(user_id, davey.MediaType.audio, packet)
        except Exception as e:
            log_exception(e)

            logger.error(f"Failed to decrypt packet from user {user_id}: {e}")
            return packet

    def encrypt_opus(
        self,
        opus: bytes,
    ) -> bytes:
        """
        Encrypt an Opus audio packet with `DAVE` E2EE.

        Parameters
        ----------
        opus : bytes
            The Opus audio to encrypt.

        Returns
        -------
        bytes
            The encrypted Opus audio - Untouched if `DAVE` not ready.
        """

        if not self.ready:
            return opus

        try:
            return self._session.encrypt_opus(opus)
        except Exception as e:
            log_exception(e)

            logger.error(f"Failed to encrypt Opus packet: {e}")
            return opus

    def get_verification_code(
        self,
        user_id: int,
    ) -> str | None:
        """
        Get the verification code for another user in the group.

        Parameters
        ----------
        user_id : int
            The ID of the user to verify.

        Returns
        -------
        str | None
            The verification code, or `None` if not available.
        """

        if not self._session or not self.ready:
            return None

        try:
            return self._session.get_verification_code(user_id)
        except Exception as e:
            log_exception(e)

            logger.error(f"Failed to get verification code: {e}")
            return None

    async def handle_commit(
        self,
        payload: bytes
    ) -> None:
        """
        Handle an announced MLS commit.

        Parameters
        ----------
        payload : bytes
            The serialized commit data.
        """

        if not self._session:
            logger.warning("Cannot process commit: no DAVE session initialized")
            return

        transition_id: int = struct.unpack(">H", payload[:2])[0]
        commit: bytes = payload[2:]

        try:
            self._session.process_commit(commit)

            if transition_id == 0:
                self._last_transition_id = transition_id
            else:
                self._pending_transitions[transition_id] = self._protocol_version
                await self.__send_transition_ready(transition_id)
        except Exception as e:
            log_exception(e)

            logger.error(f"Failed to process commit: {e}")
            await self.__send_invalid_commit_welcome()

    async def handle_execute_transition(
        self,
        transition_id: int,
    ) -> None:
        """
        Handle execution of a prepared transition.

        Parameters
        ----------
        transition_id : int
            The transition identifier.
        """

        if transition_id not in self._pending_transitions:
            logger.warning(f"Received execute transition, but no pending transition for {transition_id}")
            return

        old_version: int = self._protocol_version
        self._protocol_version = self._pending_transitions[transition_id]

        if old_version != self._protocol_version and self._protocol_version == 0:
            self._downgraded = True
            logger.debug("DAVE protocol downgraded; E2EE disabled")
        elif transition_id > 0 and self._downgraded:
            self._downgraded = False
            if self._session:
                self._session.set_passthrough_mode(True, 10)

            logger.debug("DAVE session upgraded")

        self._last_transition_id = transition_id
        self._pending_transitions.pop(transition_id, None)

        logger.debug(f"Transition executed: v{old_version} -> v{self._protocol_version}, ID={transition_id}")

    async def handle_prepare_epoch(
        self,
        transition_id: int,
        epoch_id: int,
    ) -> None:
        """
        Handle an epoch transition preparation.

        Parameters
        ----------
        transition_id : int
            The transition identifier.
        epoch_id : int
            The MLS epoch identifier.
        """

        logger.debug(f"Preparing DAVE epoch transition: TransitionID={transition_id}, EpochID={epoch_id}")

        if epoch_id == 1:
            await self.__reinit()

    async def handle_prepare_transition(
        self,
        transition_id: int,
        protocol_version: int,
    ) -> None:
        """
        Handle a downgrade transition preparation.

        Parameters
        ----------
        transition_id : int
            The transition identifier.
        protocol_version : int
            The protocol version to transition to.
        """

        logger.debug(f"Preparing DAVE protocol downgrade: TransitionID={transition_id}, ProtocolVersion={protocol_version}")

        self._pending_transitions[transition_id] = protocol_version

        if transition_id == 0:
            await self.handle_execute_transition(transition_id)
            return

        if protocol_version == 0 and self._session:
            self._session.set_passthrough_mode(True, 24)

        await self.__send_transition_ready(transition_id)

    async def handle_proposals(
        self,
        payload: bytes,
        expected_user_ids: list[int] | None = None,
    ) -> None:
        """
        Handle MLS proposals from the voice gateway.

        Parameters
        ----------
        payload : bytes
            The raw proposals payload including operation type.
        expected_user_ids: list[int] | None
            Expected user IDs for validation.
        """

        if not self._session:
            logger.warning("Cannot process proposals: no DAVE session initialized")
            return

        optype: int = payload[0]
        proposals: bytes = payload[1:]

        try:
            commit_welcome: davey.CommitWelcome | None = self._session.process_proposals(
                davey.ProposalsOperationType.append if optype == 0 else davey.ProposalsOperationType.revoke,
                proposals,
                expected_user_ids,
            )

            if commit_welcome:
                await self.__send_commit_welcome(commit_welcome)
        except Exception as e:
            log_exception(e)

            logger.error(f"Exception while processing proposals: {e}", exc_info=True)

    async def handle_welcome(
        self,
        payload: bytes,
    ) -> None:
        """
        Handle an MLS welcome message.

        Parameters
        ----------
        payload : bytes
            The raw payload including transition_id.
        """

        if not self._session:
            logger.warning("Cannot process welcome: no DAVE session initialized")
            return

        transition_id: int = struct.unpack(">H", payload[:2])[0]
        welcome: bytes = payload[2:]

        try:
            self._session.process_welcome(welcome)

            if transition_id == 0:
                self._last_transition_id = transition_id
            else:
                self._pending_transitions[transition_id] = self._protocol_version
                await self.__send_transition_ready(transition_id)
        except Exception as e:
            log_exception(e)

            logger.error(f"Failed to process welcome {transition_id}: {e}")
            await self.__send_invalid_commit_welcome()

    async def initialize_session(
        self,
        protocol_version: int,
    ) -> None:
        """
        Initialize a new `DAVE` session.

        Parameters
        ----------
        protocol_version : int
            The `DAVE` protocol version to use.
        """

        self._protocol_version = protocol_version

        if protocol_version > 0:
            await self.__reinit()

    @property
    def ready(self) -> bool:
        """Check if `DAVE` is ready for encryption/decryption."""
        return self._session is not None and self._session.ready

    @property
    def session(self) -> davey.DaveSession | None:
        """Get the current `DAVE` session."""
        return self._session

    async def set_external_sender(
        self,
        external_sender_data: bytes,
    ) -> None:
        """
        Set the external sender for the MLS group.

        Parameters
        ----------
        external_sender_data : bytes
            The serialized external sender data from the voice gateway.
        """

        if not self._session:
            logger.warning("Cannot set external sender: no DAVE session initialized")
            return

        self._session.set_external_sender(external_sender_data)

        await self.__send_key_package()

    @property
    def voice_privacy_code(self) -> str | None:
        """
        Get the voice privacy code for the current group.
        """

        if not self._session:
            return None

        return self._session.voice_privacy_code
