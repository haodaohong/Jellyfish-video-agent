from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from langchain_core.runnables import Runnable
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.agents import FilmEntityExtractorAgent, FilmShotlistStoryboarderAgent
from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.dependencies import get_db, get_llm
from app.schemas.common import ApiResponse, success_response

from .common import (
    EntityExtractTaskRequest,
    ShotlistExtractTaskRequest,
    TaskCreated,
    _CreateOnlyTask,
    bind_task,
    ensure_single_bind_target,
)

router = APIRouter()


@router.post(
    "/tasks/entities",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="关键信息抽取（任务版）",
)
async def create_entity_extract_task(
    body: EntityExtractTaskRequest,
    llm: Runnable = Depends(get_llm),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    target_type, target_id = ensure_single_bind_target(body)

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})

    chunks_json = json.dumps([{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks], ensure_ascii=False)
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        run_args={
            "source_id": body.source_id,
            "language": body.language or "zh",
            "chunks_json": chunks_json,
        },
    )
    await bind_task(
        db,
        task_id=task_record.id,
        target_type=target_type,
        target_id=target_id,
        relation_type="entities",
    )

    async def _runner(task_id: str, input_dict: dict) -> None:
        async with async_session_maker() as session:
            try:
                store2 = SqlAlchemyTaskStore(session)
                await store2.set_status(task_id, TaskStatus.running)
                await store2.set_progress(task_id, 10)
                extractor = FilmEntityExtractorAgent(llm)
                result = await extractor.aextract(**input_dict)
                await store2.set_result(task_id, result.model_dump())
                await store2.set_progress(task_id, 100)
                await store2.set_status(task_id, TaskStatus.succeeded)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                async with async_session_maker() as s2:
                    store3 = SqlAlchemyTaskStore(s2)
                    await store3.set_error(task_id, str(exc))
                    await store3.set_status(task_id, TaskStatus.failed)
                    await s2.commit()

    import asyncio

    asyncio.create_task(
        _runner(
            task_record.id,
            {"source_id": body.source_id, "language": body.language or "zh", "chunks_json": chunks_json},
        )
    )
    return success_response(TaskCreated(task_id=task_record.id), code=201)


@router.post(
    "/tasks/shotlist",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="分镜抽取（任务版）",
)
async def create_shotlist_task(
    body: ShotlistExtractTaskRequest,
    llm: Runnable = Depends(get_llm),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    target_type, target_id = ensure_single_bind_target(body)

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})

    chunks_json = json.dumps([{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks], ensure_ascii=False)
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        run_args={
            "source_id": body.source_id,
            "source_title": body.source_title or "",
            "language": body.language or "zh",
            "chunks_json": chunks_json,
        },
    )
    await bind_task(
        db,
        task_id=task_record.id,
        target_type=target_type,
        target_id=target_id,
        relation_type="shotlist",
    )

    async def _runner(task_id: str, input_dict: dict) -> None:
        async with async_session_maker() as session:
            try:
                store2 = SqlAlchemyTaskStore(session)
                await store2.set_status(task_id, TaskStatus.running)
                await store2.set_progress(task_id, 10)
                storyboarder = FilmShotlistStoryboarderAgent(llm)
                result = await storyboarder.aextract(**input_dict)
                await store2.set_result(task_id, result.model_dump())
                await store2.set_progress(task_id, 100)
                await store2.set_status(task_id, TaskStatus.succeeded)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                async with async_session_maker() as s2:
                    store3 = SqlAlchemyTaskStore(s2)
                    await store3.set_error(task_id, str(exc))
                    await store3.set_status(task_id, TaskStatus.failed)
                    await s2.commit()

    import asyncio

    asyncio.create_task(
        _runner(
            task_record.id,
            {
                "source_id": body.source_id,
                "source_title": body.source_title or "",
                "language": body.language or "zh",
                "chunks_json": chunks_json,
            },
        )
    )
    return success_response(TaskCreated(task_id=task_record.id), code=201)

