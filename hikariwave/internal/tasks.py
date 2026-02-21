from __future__ import annotations

from collections.abc import Callable, Coroutine
from hikariwave.internal.dev import log_exception
from typing import Any

import asyncio
import logging

__all__ = ()

logger: logging.Logger = logging.getLogger("hikari-wave.tasks")

class TaskManager:
    __slots__ = ("_tasks",)

    def __init__(self) -> None:
        """
        Create a new task manager/handler.
        """

        self._tasks: set[asyncio.Task[None]] = set()

    def __completed(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)

        logger.debug(f"Task completed: {task.get_name()}")

        try:
            task.result()
        except asyncio.CancelledError as e:
            log_exception(e)
            pass
        except Exception as e:
            log_exception(e)
            logger.exception(f"Task crashed: {task.get_name()}")

        self.__update()

    def __update(self) -> None:
        logger.debug(f"Current tasks: {[task.get_name() for task in self._tasks]}")

    def create(self, coroutine: Callable[[Any], Coroutine[Any, Any, None]], *, name: str | None = None) -> asyncio.Task[None]:
        """
        Create/spawn a new async task.

        Parameters
        ----------
        coroutine : Callable[[Any], Coroutine[Any, Any, None]]
            The asynchronous method to create as a task.
        name : str
            The visible name of this task.

        Returns
        -------
        asyncio.Task[None]
            The created/spawned task.
        """

        task: asyncio.Task[None] = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)

        logger.debug(f"Task created: {task.get_name()}")
        self.__update()

        task.add_done_callback(self.__completed)
        return task
