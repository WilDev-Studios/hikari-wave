from __future__ import annotations

from dataclasses import dataclass
from hikariwave.event.events.member import (
    MemberDeafEvent,
    MemberJoinEvent,
    MemberLeaveEvent,
    MemberMoveEvent,
    MemberMuteEvent,
)
from typing import TYPE_CHECKING, TypeAlias

import hikari

if TYPE_CHECKING:
    from hikariwave.client import VoiceClient

__all__ = ()

ChannelID: TypeAlias = hikari.Snowflake
MemberID:  TypeAlias = hikari.Snowflake
SSRC:      TypeAlias = int

Deafened: TypeAlias = bool
Muted:    TypeAlias = bool

@dataclass(slots=True)
class VoiceChannelMetadata:
    """Metadata container for a voice channel."""

    active: set[hikari.Snowflake]
    """A set of all actively speaking users in this channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild this channel is in."""
    id: hikari.Snowflake
    """The ID of this channel."""
    members: dict[hikari.Snowflake, hikari.Member]
    """All members within this channel."""

class Cache:
    """Cache management implementation."""

    def __init__(self, client: VoiceClient) -> None:
        """
        Create a new cache management instance.

        Parameters
        ----------
        client : VoiceClient
            The controlling voice system client.
        """

        self._client: VoiceClient = client
        self._client._bot.subscribe(hikari.VoiceStateUpdateEvent, self.__state_update)

        # global
        self._states: dict[MemberID, tuple[Muted, Deafened]] = {}

        # specific
        self._members: dict[MemberID, ChannelID] = {}
        self._channels: dict[ChannelID, VoiceChannelMetadata] = {}

        self._ssrcs:  dict[MemberID, SSRC] = {}
        self._ssrcsr: dict[SSRC, MemberID] = {}

    async def __member_join(
        self,
        member: hikari.Member,
        state: hikari.VoiceState,
        new_channel_id: hikari.Snowflake,
    ) -> None:
        member.is_deaf = state.is_guild_deafened or state.is_self_deafened
        member.is_mute = state.is_guild_muted or state.is_self_muted
        self._states[member.id] = (member.is_mute, member.is_deaf)

        if new_channel_id in self._channels:
            metadata: VoiceChannelMetadata = self._channels[new_channel_id]
            metadata.members[member.id] = member
            self._members[member.id] = new_channel_id

        self._client._event_factory.emit(
            MemberJoinEvent,
            channel_id=new_channel_id,
            guild_id=member.guild_id,
            member=member,
        )

    async def __member_leave(
        self,
        member: hikari.Member,
        old_channel_id: hikari.Snowflake,
    ) -> None:
        self._states.pop(member.id, None)

        if old_channel_id in self._channels:
            metadata: VoiceChannelMetadata = self._channels[old_channel_id]
            del metadata.members[member.id]
            del self._members[member.id]

            ssrc: int | None = self._ssrcs.pop(member.id, None)
            if ssrc:
                del self._ssrcsr[ssrc]

        self._client._event_factory.emit(
            MemberLeaveEvent,
            channel_id=old_channel_id,
            guild_id=member.guild_id,
            member=member,
        )

    async def __member_move(
        self,
        member: hikari.Member,
        old_channel_id: hikari.Snowflake,
        new_channel_id: hikari.Snowflake,
    ) -> None:
        if old_channel_id in self._channels:
            metadata: VoiceChannelMetadata = self._channels[old_channel_id]
            del metadata.members[member.id]
            del self._members[member.id]

            ssrc: int | None = self._ssrcs.pop(member.id, None)
            if ssrc:
                del self._ssrcsr[ssrc]

        if new_channel_id in self._channels:
            metadata: VoiceChannelMetadata = self._channels[new_channel_id]
            metadata.members[member.id] = member
            self._members[member.id] = new_channel_id

            ssrc: int | None = self._ssrcs.pop(member.id, None)
            if ssrc:
                del self._ssrcsr[ssrc]

        self._client._event_factory.emit(
            MemberMoveEvent,
            channel_id=new_channel_id,
            guild_id=member.guild_id,
            member=member,
            old_channel_id=old_channel_id,
        )

    async def __member_update(
        self,
        member: hikari.Member,
        state: hikari.VoiceState,
        new_channel_id: hikari.Snowflake,
    ) -> None:
        member.is_deaf = state.is_guild_deafened or state.is_self_deafened
        member.is_mute = state.is_guild_muted or state.is_self_muted

        old_mute, old_deaf = self._states[member.id]

        if new_channel_id in self._channels:
            metadata: VoiceChannelMetadata = self._channels[new_channel_id]
            metadata.members[member.id] = member

        if old_mute != member.is_mute:
            self._client._event_factory.emit(
                MemberMuteEvent,
                channel_id=new_channel_id,
                guild_id=member.guild_id,
                is_mute=member.is_mute,
                member=member,
            )

        if old_deaf != member.is_deaf:
            self._client._event_factory.emit(
                MemberDeafEvent,
                channel_id=new_channel_id,
                guild_id=member.guild_id,
                is_deaf=member.is_deaf,
                member=member,
            )

        self._states[member.id] = (member.is_mute, member.is_deaf)

    async def __state_update(self, event: hikari.VoiceStateUpdateEvent) -> None:
        state: hikari.VoiceState = event.state
        member: hikari.Member = state.member

        if state.user_id == self._client._bot.get_me().id or not member:
            return

        old_channel_id: hikari.Snowflake | None = self._members.get(member.id)
        new_channel_id: hikari.Snowflake | None = state.channel_id

        if not old_channel_id and new_channel_id:
            await self.__member_join(member, state, new_channel_id)
        elif old_channel_id and new_channel_id and old_channel_id != new_channel_id:
            await self.__member_move(member, old_channel_id, new_channel_id)
        elif old_channel_id and not new_channel_id:
            await self.__member_leave(member, old_channel_id)
        elif old_channel_id and new_channel_id and old_channel_id == new_channel_id:
            await self.__member_update(member, state)

    def check_ssrc_connected(self, ssrc: int) -> bool:
        """
        Check if the provided SSRC maps to a connected user.

        Parameters
        ----------
        ssrc : int
            The SSRC of the user.

        Returns
        -------
        bool
            If the SSRC maps to a user, thus being connected.
        """

        return ssrc in self._ssrcsr

    def clear(self) -> None:
        """
        Clear all internal data.
        """

        self._channels.clear()
        self._members.clear()

        self._ssrcs.clear()
        self._ssrcsr.clear()

        self._states.clear()

    def delete_channel_metadata(self, channel_id: hikari.Snowflake) -> VoiceChannelMetadata | None:
        """
        Delete metadata for a specific channel.

        Parameters
        ----------
        channel_id : hikari.Snowflake
            The ID of the channel to clear.

        Returns
        -------
        VoiceChannelMetadata | None
            The deleted metadata, if found.
        """

        return self._channels.pop(channel_id, None)

    def delete_member(self, member_id: hikari.Snowflake) -> None:
        """
        Delete a member mapping to a channel.

        Parameters
        ----------
        member_id : hikari.Snowflake
            The ID of the member to remove.
        """

        del self._members[member_id]

    def delete_ssrc(self, member_id: hikari.Snowflake) -> None:
        """
        Delete/disassociate a SSRC with a member.

        Parameters
        ----------
        member_id : hikari.Snowflake
            The ID of the member to disassociate SSRCs with.
        """

        ssrc: int | None = self._ssrcs.pop(member_id, None)

        if not ssrc:
            return

        self._ssrcsr.pop(ssrc, None)

    def get_channel_member_ids(self, channel_id: hikari.Snowflake) -> list[hikari.Snowflake]:
        """
        Get a list of all members within a channel.

        Parameters
        ----------
        channel_id : hikari.Snowflake
            The ID of the channel.

        Returns
        -------
        list[hikari.Snowflake]
            All members within the channel.
        """

        metadata: VoiceChannelMetadata | None = self._channels.get(channel_id)
        if not metadata:
            return []

        return metadata.members.keys()

    def get_channel_metadata(self, channel_id: hikari.Snowflake) -> VoiceChannelMetadata | None:
        """
        Get the metadata for a channel.

        Parameters
        ----------
        channel_id : hikari.Snowflake
            The ID of the channel.

        Returns
        -------
        VoiceChannelMetadata | None
            The channel metadata, if found.
        """

        return self._channels.get(channel_id)

    def get_member_channel(self, member_id: hikari.Snowflake) -> hikari.Snowflake | None:
        """
        Get the channel a member is in.

        Parameters
        ----------
        member_id : hikari.Snowflake
            The ID of the member.

        Returns
        -------
        hikari.Snowflake | None
            The ID of the channel, if found.
        """

        return self._members.get(member_id)

    def get_ssrc_member(self, ssrc: int) -> hikari.Snowflake | None:
        """
        Get the member associated with a SSRC.

        Parameters
        ----------
        ssrc : int
            The SSRC of the member.

        Returns
        -------
        hikari.Snowflake | None
            The ID of the member associated with this SSRC.
        """

        return self._ssrcsr.get(ssrc)

    def set_channel_metadata(self, channel_id: hikari.Snowflake, metadata: VoiceChannelMetadata) -> None:
        """
        Set the metadata for a channel.

        Parameters
        ----------
        channel_id : hikari.Snowflake
            The ID of the channel.
        metadata : VoiceChannelMetadata
            The metadata for this channel.
        """

        self._channels[channel_id] = metadata

    def set_member_channel(self, member_id: hikari.Snowflake, channel_id: hikari.Snowflake) -> None:
        """
        Set the channel that a member is in.

        Parameters
        ----------
        member_id : hikari.Snowflake
            The ID of the member.
        channel_id : hikari.Snowflake
            The ID of the channel.
        """

        self._members[member_id] = channel_id

    def set_member_ssrc(self, member_id: hikari.Snowflake, ssrc: int) -> None:
        """
        Associate a SSRC with a member.

        Parameters
        ----------
        member_id : hikari.Snowflake
            The ID of the member.
        ssrc : int
            The SSRC to associate.
        """

        self._ssrcs[member_id] = ssrc
        self._ssrcsr[ssrc] = member_id

    def set_member_state(self, member_id: hikari.Snowflake, mute: bool, deaf: bool) -> None:
        """
        Set the state of a member.

        Parameters
        ----------
        member_id : hikari.Snowflake
            The ID of the member.
        mute : bool
            If this member is muted.
        deaf : bool
            If this member is deafened.
        """

        self._states[member_id] = (mute, deaf)
