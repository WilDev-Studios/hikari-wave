from __future__ import annotations

from hikariwave.internal.dev import log_exception

__all__ = ("AudioSource",)

def validate_content(content: object, name: str, expected: tuple[object]) -> type:
    if not isinstance(content, expected):
        if len(expected) == 1:
            error: str = f"Provided {name} must be `{expected}`"
        elif len(expected) == 2:
            error: str = f"Provided {name} must be `{expected[0]}` or `{expected[1]}`"
        else:
            types: list[str] = [f"`{type_.__name__}`" for type_ in expected]
            error: str = f"Provided {name} must be " + ", ".join(types[:-1]) + f", or {types[-1]}"

        raise TypeError(error)

    try:
        if len(content) == 0:
            error: str = f"Provided {name} can't be empty"
            raise ValueError(error)
    except TypeError as e:
        log_exception(e)
        pass

    return content

def validate_duration(duration: object) -> float:
    if not isinstance(duration, (float, int)):
        error: str = "Provided duration must be `float`"
        raise TypeError(error)

    if duration <= 0:
        error: str = "Provided duration must be greater than `0`"
        raise ValueError(error)

    return float(duration)

def validate_name(name: object) -> str:
    if not isinstance(name, str):
        error: str = "Provided name must be `str`"
        raise TypeError(error)

    if len(name) == 0:
        error: str = "Provided name cannot be empty"
        raise ValueError(error)

    return name

class AudioSource:
    """Base audio source implementation."""

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False

        return self._content == other._content

    def __hash__(self) -> int:
        return hash((type(self), self._content))

    @property
    def bitrate(self) -> str | None:
        """If provided, the bitrate in which this source is played back at."""
        return self._bitrate

    @property
    def channels(self) -> int | None:
        """If provided, the amount of channels this source plays with."""
        return self._channels

    @property
    def duration(self) -> float | None:
        """The duration of the source, if provided/found."""
        return self._duration

    @property
    def name(self) -> str | None:
        """If provided, the name assigned to this source for display purposes."""
        return self._name

    @property
    def volume(self) -> float | str | None:
        """If provided, the overriding volume for this source."""
        return self._volume
