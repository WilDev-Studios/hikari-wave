import logging
import os

__all__ = ()

DEV_MODE: bool = None

logger: logging.Logger = logging.getLogger("hikari-wave.dev")

def init_dev() -> None:
    """
    Initialize developer mode logic.
    """

    global DEV_MODE

    DEV_MODE = os.getenv("HIKARIWAVE_DEV") not in (None, '', '0', "false")

    if DEV_MODE:
        logger.warning("hikari-wave developer mode is set. All exceptions (control or otherwise) will be logged")

def log_exception(exc: BaseException, *, context: str | None = None) -> None:
    """
    Log an exception with the internal logger.

    Parameters
    ----------
    exc : BaseException
        The exception that was raised.
    context : str | None
        Any necessary context associated with this error.
    """

    if not DEV_MODE:
        return

    logger.exception("Exception%s", f"  ({context})" if context else '', exc_info=exc)
