"""将 core/agents 的抽取器封装为 BaseTask 任务。

目的：
- 让 FilmEntityExtractorAgent / FilmShotlistStoryboarderAgent 可以直接作为 TaskManager 的任务单元
- run() 采用 async_result 模式：返回 None，结果通过 get_result() 获取
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from app.chains.agents import FilmEntityExtractorAgent, FilmShotlistStoryboarderAgent
from app.schemas.skills.film import FilmEntityExtractionResult, FilmShotlistResult
from app.core.task_manager.types import BaseTask


class FilmEntityExtractionTask(BaseTask):
    """人物/地点/道具抽取任务（async_result 模式）。"""

    def __init__(
        self,
        extractor: FilmEntityExtractorAgent,
        *,
        input_dict: dict[str, Any],
    ) -> None:
        self._extractor = extractor
        self._input_dict = input_dict
        self._result: FilmEntityExtractionResult | None = None
        self._error: str = ""

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        try:
            self._result = await self._extractor.aextract(**self._input_dict)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._result = None
        return None

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return {
            "task": "film_entity_extraction",
            "done": await self.is_done(),
            "has_result": self._result is not None,
            "error": self._error,
        }

    async def is_done(self) -> bool:  # type: ignore[override]
        return self._result is not None or bool(self._error)

    async def get_result(self) -> FilmEntityExtractionResult | None:  # type: ignore[override]
        return self._result


class FilmShotlistTask(BaseTask):
    """分镜/镜头表抽取任务（async_result 模式）。"""

    def __init__(
        self,
        storyboarder: FilmShotlistStoryboarderAgent,
        *,
        input_dict: dict[str, Any],
    ) -> None:
        self._storyboarder = storyboarder
        self._input_dict = input_dict
        self._result: FilmShotlistResult | None = None
        self._error: str = ""

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        try:
            self._result = await self._storyboarder.aextract(**self._input_dict)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._result = None
        return None

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return {
            "task": "film_shotlist",
            "done": await self.is_done(),
            "has_result": self._result is not None,
            "error": self._error,
        }

    async def is_done(self) -> bool:  # type: ignore[override]
        return self._result is not None or bool(self._error)

    async def get_result(self) -> FilmShotlistResult | None:  # type: ignore[override]
        return self._result

