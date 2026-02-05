from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import asyncio
import logging

__all__ = ("TaskManager",)

logger: logging.Logger = logging.getLogger("hikari-wave.tasks")

class TaskManager:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def __completed(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)

        logger.debug(f"Task has completed: {task.get_name()}")

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(f"Task {task.get_name()} crashed")

    def create(self, coroutine: Callable[[Any], Coroutine[Any, Any, None]], *, name: str | None = None) -> asyncio.Task[None]:
        task: asyncio.Task[None] = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)

        logger.debug(f"New task has been created: {task.get_name()}")

        task.add_done_callback(self.__completed)
        return task
