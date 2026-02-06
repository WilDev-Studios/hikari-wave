from __future__ import annotations

def verify_type(obj: object, _type: type, name: str) -> None:
    """
    Verify that the provided object is an instance of the type.

    Parameters
    ----------
    obj : object
        The object instance to check the type.
    _type : type
        The object type to check for.
    name : str
        The name of this object in a generated exception, if an issue occurs.

    Raises
    ------
    TypeError
        If the provided object is not an instance of the type.
    """

    if isinstance(obj, _type):
        return

    error: str = f"Provided {name} must be `{_type.__name__}`"
    raise TypeError(error)
