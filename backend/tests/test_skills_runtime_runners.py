"""FilmEntityExtractorAgent 与 FilmShotlistStoryboarderAgent 实现类的单元测试。"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult

from app.chains.agents import FilmEntityExtractorAgent, FilmShotlistStoryboarderAgent
from app.schemas.skills.film import FilmEntityExtractionResult, FilmShotlistResult


# ---------- Mock agents ----------


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


# ---------- FilmEntityExtractorAgent ----------


class TestFilmEntityExtractor:
    """FilmEntityExtractorAgent 单元测试。"""

    def test_format_output_plain_json(self) -> None:
        model = _mock_entity_model()
        extractor = FilmEntityExtractorAgent(model)
        raw = '{"source_id": "e1", "chunks": [], "characters": [], "locations": [], "props": [], "notes": [], "uncertainties": []}'
        result = extractor.format_output(raw)
        assert isinstance(result, FilmEntityExtractionResult)
        assert result.source_id == "e1"
        assert result.characters == []
        assert result.locations == []
        assert result.props == []

    def test_format_output_markdown_wrapped_json(self) -> None:
        model = _mock_entity_model()
        extractor = FilmEntityExtractorAgent(model)
        raw = '```json\n{"source_id": "e2", "chunks": [], "characters": [], "locations": [], "props": [], "notes": [], "uncertainties": []}\n```'
        result = extractor.format_output(raw)
        assert isinstance(result, FilmEntityExtractionResult)
        assert result.source_id == "e2"

    def test_format_output_invalid_json_raises(self) -> None:
        model = _mock_entity_model()
        extractor = FilmEntityExtractorAgent(model)
        with pytest.raises((ValueError, Exception)):  # json.JSONDecodeError or pydantic.ValidationError
            extractor.format_output("not valid json")

    def test_extract_end_to_end(self) -> None:
        model = _mock_entity_model()
        extractor = FilmEntityExtractorAgent(model)
        result = extractor.extract(
            source_id="novel_ch01",
            language="zh",
            chunks_json='[{"chunk_id":"c1","text":"张三走进客厅"}]',
        )
        assert isinstance(result, FilmEntityExtractionResult)
        assert result.source_id == "novel_ch01"
        assert result.chunks == ["c1"]

    @pytest.mark.asyncio
    async def test_aextract_end_to_end(self) -> None:
        model = _mock_entity_model()
        extractor = FilmEntityExtractorAgent(model)
        result = await extractor.aextract(source_id="novel_ch01", language="zh", chunks_json="[]")
        assert isinstance(result, FilmEntityExtractionResult)
        assert result.source_id == "novel_ch01"


# ---------- FilmShotlistStoryboarderAgent ----------


class TestFilmShotlistStoryboarder:
    """FilmShotlistStoryboarderAgent 单元测试。"""

    def test_format_output_valid_breakdown(self) -> None:
        model = _mock_shotlist_model()
        storyboarder = FilmShotlistStoryboarderAgent(model)
        raw = (
            '{"breakdown": {"source_id": "ch01", "chunks": [], "characters": [], '
            '"locations": [], "props": [], "scenes": [], "shots": [], '
            '"transitions": [], "notes": [], "uncertainties": []}}'
        )
        result = storyboarder.format_output(raw)
        assert isinstance(result, FilmShotlistResult)
        assert result.breakdown.source_id == "ch01"
        assert result.breakdown.shots == []
        assert result.breakdown.scenes == []

    def test_extract_end_to_end(self) -> None:
        model = _mock_shotlist_model()
        storyboarder = FilmShotlistStoryboarderAgent(model)
        result = storyboarder.extract(
            source_id="novel_ch01",
            source_title="第一章",
            language="zh",
            chunks_json="[]",
        )
        assert isinstance(result, FilmShotlistResult)
        assert result.breakdown.source_id == "novel_ch01"
        assert result.breakdown.scenes == []
        assert result.breakdown.shots == []

    @pytest.mark.asyncio
    async def test_aextract_end_to_end(self) -> None:
        model = _mock_shotlist_model()
        storyboarder = FilmShotlistStoryboarderAgent(model)
        result = await storyboarder.aextract(
            source_id="novel_ch01",
            source_title="",
            language="zh",
            chunks_json="[]",
        )
        assert isinstance(result, FilmShotlistResult)
        assert result.breakdown.source_id == "novel_ch01"
