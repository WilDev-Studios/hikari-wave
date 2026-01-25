from enum import IntEnum

__all__ = (
    "BufferConfig",
    "BufferMode",
    "Config",
)

def validate_bitrate(bitrate: object) -> str:
    """
    Validate a user-provided bitrate to specific contraints.

    Parameters
    ----------
    bitrate : object
        The user-provided bitrate.

    Returns
    -------
    str
        The sanitized bitrate.

    Raises
    ------
    TypeError
        If `bitrate` is not a `str`.
    ValueError
        - If `bitrate` does not end with `k`.
        - If `bitrate` is not an integer before the `k`.
        - If `bitrate` integer is not between `6k` and `510k`.
    """

    if not isinstance(bitrate, str):
        error: str = "Provided bitrate must be `str`"
        raise TypeError(error)

    bitrate: str = bitrate.strip().lower()
    if not bitrate.endswith('k'):
        error: str = "Provided bitrate must end with 'k'"
        raise ValueError(error)

    part: str = bitrate[:-1]
    try:
        part: int = int(part)
    except Exception as e:
        error: str = "Provided bitrate must be an integer ending with 'k'"
        raise ValueError(error) from e

    if not (6 <= part <= 510):
        error: str = "Provided bitrate must be between `6k` and `510k`"
        raise ValueError(error)

    return f"{part}k"

def validate_channels(channels: object) -> int:
    """
    Validate user-provided channels to specific constraints.

    Parameters
    ----------
    channels : object
        The user-provided channels.

    Returns
    -------
    int
        The sanitized channels.

    Raises
    ------
    TypeError
        If `channels` is not `int`.
    ValueError
        If `channels` is not `1` or `2`.
    """

    if not isinstance(channels, int):
        error: str = "Provided `channels` must be `int`"
        raise TypeError(error)

    if channels not in (1, 2):
        error: str = "Provided `channels` must be `1` or `2`"
        raise ValueError(error)

    return channels

def validate_volume(volume: object) -> float | int | str:
    """
    Validate user-provided volume to specific contraints.

    Parameters
    ----------
    volume : object
        The user-provided volume.

    Returns
    -------
    float | int | str
        The sanitized volume.

    Raises
    ------
    TypeError
        If `volume` isn't `float`, `int`, or `str`.
    ValueError
        - If `volume` is `float` or `int` and is not positive.
        - If `volume` is `str` and doesn't contain a number, doesn't end with `dB`, or (if provided) doesn't start with `-` or `+`.
    """

    if isinstance(volume, (float, int)):
        if volume < 0:
            error: str = "Provided volume must be positive"
            raise ValueError(error)

        return float(volume)

    if isinstance(volume, str):
        volume: str = volume.strip()
        if not volume.endswith("dB"):
            error: str = "Provided volume must end with 'dB'"
            raise ValueError(error)

        part: str = volume[:-2]
        if not part:
            error: str = "Provided volume must contain a number before 'dB'"
            raise ValueError(error)

        if part[0] in "+-":
            number: str = part[1:]
        else:
            number: str = part

        try:
            float(number)
        except Exception as e:
            error: str = "Provided volume must contain a valid number"
            raise ValueError(error) from e

        return volume

    error: str = "Provided volume must be `float`, `int`, or `str`"
    raise TypeError(error)

class BufferMode(IntEnum):
    """Frame storage buffer modes."""

    MEMORY = 0
    """All buffered frames will be stored in memory (RAM) - Only recommended for high-RAM servers/devices."""
    DISK   = 1
    """All buffered frames will be stored on the disk (storage) with configurable values and amounts - Recommended for most setups."""

class BufferConfig:
    """Configure the frame storage buffer system."""

    __slots__ = ("_mode", "_duration",)

    def __init__(self, mode: BufferMode = BufferMode.MEMORY, *, duration: int = None) -> None:
        """
        Create a new frame storage buffer configuration.

        Parameters
        ----------
        mode : BufferMode
            The frame storage buffer mode - `DISK` is recommended for most devices, `MEMORY` is set by default as it's expected behavior (all audio stored in RAM).
        duration : int
            If `mode` is `BufferMode`.`DISK`, configures the amount of seconds of audio to be stored in each chunk file. `15-30` seconds is recommended, with lower values better for low-RAM and higher for high-RAM.

        Note
        ----
        If `mode` is `BufferMode`.`DISK`, `duration` must be specified.

        Raises
        ------
        TypeError
            - If `mode` is not `BufferMode`.
            - If `duration` is provided and is not `int`.
        ValueError
            - If `mode` is `BufferMode`.`DISK` and `duration` is not provided.
            - If `duration` is provided and is less than `1` while `mode` is `BufferMode.DISK`.
        """

        if not isinstance(mode, BufferMode):
            error: str = "Provided mode must be `BufferMode`"
            raise TypeError(error)

        if duration and not isinstance(duration, int):
            error: str = "Provided duration must be `int`"
            raise TypeError(error)

        if mode == BufferMode.DISK and duration is None:
            error: str = "Duration must be provided when `BufferMode` is `DISK`"
            raise ValueError(error)

        if duration and duration < 1 and mode == BufferMode.DISK:
            error: str = "Provided duration must be at least 1"
            raise ValueError(error)

        self._mode: BufferMode = mode
        self._duration: int = duration

    @property
    def duration(self) -> int:
        """If provided, the amount of seconds of audio each buffer cache file contains."""
        return self._duration

    @property
    def mode(self) -> BufferMode:
        """The frame storage buffer mode."""
        return self._mode

class FFmpegConfig:
    """Configure the FFmpeg system."""

    __slots__ = ("_max_core", "_max_total",)

    def __init__(self, max_per_core: int = 1, max_total: int = 8) -> None:
        """
        Create a new `FFmpeg` configuration. This configuration only affects the global state of the voice system, not per-connection.

        Parameters
        ----------
        max_per_core : int
            The maximum amount of spawned `FFmpeg` processes per logical CPU/processor core.
        max_total : int
            The maximum amount of spawned `FFmpeg` processes that can exist at any one time.
        """

        self._max_core: int = max_per_core
        self._max_total: int = max_total

    @property
    def max_per_core(self) -> int:
        """The maximum amount of spawned `FFmpeg` processes per logic CPU/processor core."""
        return self._max_core

    @property
    def max_total(self) -> int:
        """The maximum amount of spawned `FFmpeg` processes that can exist at any one time."""
        return self._max_total

class Config:
    """Global or per-connection configuration settings."""

    __slots__ = (
        "_bitrate",
        "_buffer",
        "_channels",
        "_ffmpeg",
        "_max_history",
        "_max_queue",
        "_record",
        "_volume",
    )

    def __init__(
        self,
        *,
        bitrate: str = "96k",
        buffer: BufferConfig = None,
        channels: int = 2,
        ffmpeg: FFmpegConfig = None,
        max_history: int = None,
        max_queue: int = None,
        record: bool = False,
        volume: float | int | str = 1.0,
    ) -> None:
        """
        Create a global or per-connection configuration object.

        Parameters
        ----------
        bitrate : str
            If provided, the playback bitrate of all audio in KB/s.
        buffer : BufferConfig
            If provided, the frame storage buffer configuration.
        channels : int
            If provided, the amount of audio channels that are used.
        ffmpeg : FFmpegConfig
            If provided, the `FFmpeg` system configuration.
        max_history : int
            If provided, the maximum amount of audio sources recorded in audio player history.
        max_queue : int
            If provided, the maximum amount of audio sources that can be in audio player queues.
        record : bool
            If provided, sets if you can collect/handle/record members' voice packets and handle via `MemberSpeechEvent`.
        volume : float | int | str
            If provided, the volume of all audio - Reference FFmpeg volume audio filtering.

        Raises
        ------
        TypeError
            - If `bitrate` is provided and is not `str`.
            - If `buffer` is provided and is not `BufferConfig`.
            - If `channels` is provided and is not `int`.
            - If `ffmpeg` is provided and is not `FFmpegConfig`.
            - If `max_history` is provided and is not `int`.
            - If `max_queue` is provided and is not `int`.
            - If `record` is provided and is not `bool`.
            - If `volume` is provided and is not `float`, `int`, or `str`.
        ValueError
            - If `bitrate` is provided and not between `6k` and `510k`.
            - If `channels` is provided and not `1` or `2`.
            - If `max_history` is provided and not at least `1`.
            - If `max_queue` is provided and not at least `1`.
            - If `volume` is provided and is `float` or `int` and is not positive or is `str` and doesn't contain a number, doesn't end with `dB`, or (if provided) doesn't start with '-' or '+'.
        """

        if buffer is not None and not isinstance(buffer, BufferConfig):
            error: str = "Provided buffer must be `BufferConfig`"
            raise TypeError(error)

        if ffmpeg is not None and not isinstance(ffmpeg, FFmpegConfig):
            error: str = "Provided ffmpeg must be `FFmpegConfig`"
            raise TypeError(error)

        if max_history is not None:
            if not isinstance(max_history, int):
                error: str = "Provided max_history must be `int`"
                raise TypeError(error)

            if max_history < 1:
                error: str = "Provided max_history must be at least `1`"
                raise ValueError(error)

        if max_queue is not None:
            if not isinstance(max_queue, int):
                error: str = "Provided max_queue must be `int`"
                raise TypeError(error)

            if max_queue < 1:
                error: str = "Provided max_queue must be at least `1`"
                raise ValueError(error)

        if record is not None and not isinstance(record, bool):
            error: str = "Provided record must be `bool`"
            raise TypeError(error)

        self._bitrate: str = validate_bitrate(bitrate)
        self._buffer: BufferConfig = buffer if buffer is not None else BufferConfig()
        self._channels: int = validate_channels(channels)
        self._ffmpeg: FFmpegConfig = ffmpeg if ffmpeg is not None else FFmpegConfig()
        self._max_history: int | None = max_history
        self._max_queue: int | None = max_queue
        self._record: bool = record
        self._volume: float | int | str = validate_volume(volume)

    @property
    def bitrate(self) -> str:
        """The playback bitrate of all audio in KB/s."""
        return self._bitrate

    @property
    def buffer(self) -> BufferConfig:
        """The frame storage buffer configuration."""
        return self._buffer

    @property
    def channels(self) -> int:
        """The amount of audio channels that are used."""
        return self._channels

    @property
    def ffmpeg(self) -> FFmpegConfig:
        """The `FFmpeg` system configuration - Only applicable globally, not per-connection."""
        return self._ffmpeg

    @property
    def max_history(self) -> int | None:
        """If set, the maximum amount of audio sources that can be recorded in audio player history."""
        return self._max_history

    @property
    def max_queue(self) -> int | None:
        """If set, the maximum amount of audio sources that can be queued in the audio player."""
        return self._max_queue

    @property
    def record(self) -> bool:
        "If you are collecting/handling/recording members' voice packets and handling via `MemberSpeechEvent`."""
        return self._record

    @property
    def volume(self) -> float | int | str:
        """The default volume of all audio sources."""
        return self._volume
