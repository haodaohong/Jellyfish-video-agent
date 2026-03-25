from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from langchain_core.runnables import Runnable

from app.chains.agents import FilmEntityExtractorAgent, FilmShotlistStoryboarderAgent
from app.schemas.skills.film import FilmEntityExtractionResult, FilmShotlistResult
from app.dependencies import get_llm
from app.schemas.common import ApiResponse, success_response

from .common import EntityExtractRequest, ShotlistExtractRequest

router = APIRouter()


@router.post(
    "/extract/entities",
    response_model=ApiResponse[FilmEntityExtractionResult],
    summary="关键信息抽取",
    description="从小说文本中抽取人物、地点、道具，忠实原文、可追溯证据。",
)
def extract_entities(
    body: EntityExtractRequest,
    llm: Runnable = Depends(get_llm),
) -> ApiResponse[FilmEntityExtractionResult]:
    """FilmEntityExtractorAgent：人物/地点/道具抽取。"""
    extractor = FilmEntityExtractorAgent(llm)
    chunks_json = json.dumps(
        [{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks],
        ensure_ascii=False,
    )
    result = extractor.extract(
        source_id=body.source_id,
        language=body.language or "zh",
        chunks_json=chunks_json,
    )
    return success_response(result)


@router.post(
    "/extract/shotlist",
    response_model=ApiResponse[FilmShotlistResult],
    summary="分镜抽取",
    description="将小说片段转为可拍镜头表（景别/机位/运镜/转场/VFX）。",
)
def extract_shotlist(
    body: ShotlistExtractRequest,
    llm: Runnable = Depends(get_llm),
) -> ApiResponse[FilmShotlistResult]:
    """FilmShotlistStoryboarderAgent：场景/镜头/转场抽取。"""
    storyboarder = FilmShotlistStoryboarderAgent(llm)
    chunks_json = json.dumps(
        [{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks],
        ensure_ascii=False,
    )
    result = storyboarder.extract(
        source_id=body.source_id,
        source_title=body.source_title or "",
        language=body.language or "zh",
        chunks_json=chunks_json,
    )
    return success_response(result)

