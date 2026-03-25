from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult

from app.chains.agents import FilmEntityExtractorAgent, FilmShotlistStoryboarderAgent
from app.core.tasks.extra_tasks import FilmEntityExtractionTask, FilmShotlistTask


class _MockChatModel(BaseChatModel):
    def __init__(self, response: str) -> None:
        super().__init__()
        self._response = response

    @property
    def _llm_type(self) -> str:  # pragma: no cover
        return "mock-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # type: ignore[override]
        msg = AIMessage(content=self._response)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _mock_entity_model() -> BaseChatModel:
    return _MockChatModel(
        '{"source_id": "novel_ch01", "chunks": ["c1"], "characters": [], '
        '"locations": [], "props": [], "notes": [], "uncertainties": []}'
    )


def _mock_shotlist_model() -> BaseChatModel:
    return _MockChatModel(
        '{"breakdown": {"source_id": "novel_ch01", "chunks": [], '
        '"characters": [], "locations": [], "props": [], "scenes": [], '
        '"shots": [], "transitions": [], "notes": [], "uncertainties": []}}'
    )


@pytest.mark.asyncio
async def test_film_entity_extraction_task_async_result() -> None:
    model = _mock_entity_model()
    extractor = FilmEntityExtractorAgent(model)
    task = FilmEntityExtractionTask(
        extractor,
        input_dict={"source_id": "novel_ch01", "language": "zh", "chunks_json": "[]"},
    )

    assert await task.is_done() is False
    assert await task.get_result() is None

    await task.run()
    assert await task.is_done() is True
    result = await task.get_result()
    assert result is not None
    assert result.source_id == "novel_ch01"

    st = await task.status()
    assert st["done"] is True
    assert st["has_result"] is True
    assert st["error"] == ""


@pytest.mark.asyncio
async def test_film_shotlist_task_async_result() -> None:
    model = _mock_shotlist_model()
    storyboarder = FilmShotlistStoryboarderAgent(model)
    task = FilmShotlistTask(
        storyboarder,
        input_dict={"source_id": "novel_ch01", "source_title": "", "language": "zh", "chunks_json": "[]"},
    )

    await task.run()
    result = await task.get_result()
    assert result is not None
    assert result.breakdown.source_id == "novel_ch01"


@pytest.mark.asyncio
async def test_task_records_error_when_skill_invalid() -> None:
    model = _mock_entity_model()
    extractor = FilmEntityExtractorAgent(model)
    task = FilmEntityExtractionTask(
        extractor,
        input_dict={"source_id": "novel_ch01", "language": "zh", "chunks_json": "[]"},
    )

    # 这里不再测试“无效 skill_id”，因为动态 skill 机制已被移除。
    await task.run()
    assert await task.get_result() is not None

