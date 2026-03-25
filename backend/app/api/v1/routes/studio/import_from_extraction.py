"""从信息提取结果导入 Studio：创建资产、角色、镜头与关联。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.skills.script_processing import StudioScriptExtractionDraft
from app.dependencies import get_db
from app.models.studio import (
    Actor,
    Chapter,
    ImportCharacterDraft,
    ImportCostumeDraft,
    ImportDraftShotOccurrence,
    ImportDraftType,
    ImportPropDraft,
    ImportSceneDraft,
    Character,
    CharacterPropLink,
    Costume,
    Prop,
    Project,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    Scene,
    Shot,
    ShotCharacterLink,
    ShotDetail,
    ShotDialogLine,
)
from app.utils.project_links import upsert_project_link
from app.schemas.common import ApiResponse, success_response
from app.schemas.studio.shots import CameraAngle, CameraMovement, CameraShotType, DialogueLineMode, VFXType


router = APIRouter()


OnConflict = Literal["error"]


@dataclass(frozen=True)
class _IdMaps:
    scene_by_name: dict[str, str]
    prop_by_name: dict[str, str]
    costume_by_name: dict[str, str]
    character_by_name: dict[str, str]
    shot_by_index: dict[int, str]


class ImportFromExtractionRequest(StudioScriptExtractionDraft):
    """导入请求：直接复用 StudioScriptExtractionDraft 结构。"""

    on_conflict: OnConflict = "error"
    force_overwrite: bool = False


class ImportFromExtractionResponse(BaseModel):  # type: ignore[name-defined]
    """导入响应：创建统计与 name->id 映射。"""

    created: dict[str, int]
    ids: dict[str, dict[str, str]]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _split_scene_names(scene_name: str | None) -> list[str]:
    """支持复合场景名：按常见分隔符拆分并去重保序。"""
    if not scene_name:
        return []
    s = scene_name.strip()
    if not s:
        return []
    tokens = [s]
    for sep in ("/", "／", "、", ",", "，"):
        next_tokens: list[str] = []
        for t in tokens:
            next_tokens.extend(t.split(sep))
        tokens = next_tokens
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        name = t.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


async def _resolve_scene_ids(
    db: AsyncSession,
    *,
    scene_name_raw: str | None,
    scene_by_name: dict[str, str],
    force_overwrite: bool,
) -> list[str]:
    """将镜头 scene_name 解析为一个或多个 scene_id。

    规则：
    - 支持复合名称拆分（如 `小河边/回家路上`）；
    - 优先命中本次导入已创建/更新的 scene_by_name；
    - force_overwrite=true 时允许回查 DB；
    - 返回去重后的可解析 scene_id 列表（允许部分 token 未命中）。
    """
    names = _split_scene_names(scene_name_raw)
    if not names:
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for name in names:
        scene_id = scene_by_name.get(name)
        if scene_id is None and force_overwrite:
            scene_id = await _get_asset_id_by_name(db, Scene, name=name)
        if scene_id and scene_id not in seen:
            seen.add(scene_id)
            ids.append(scene_id)
    return ids


async def _ensure_project_and_chapter(db: AsyncSession, project_id: str, chapter_id: str) -> None:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=400, detail=f"Project not found: {project_id}")
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=400, detail=f"Chapter not found: {chapter_id}")
    if chapter.project_id != project_id:
        raise HTTPException(status_code=400, detail="chapter_id does not belong to project_id")


async def _ensure_unique_asset_name(
    db: AsyncSession,
    model: Any,  # noqa: ANN401
    *,
    name: str,
) -> None:
    stmt = select(model.id).where(model.name == name)
    exists = (await db.execute(stmt)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail=f"{model.__name__} name already exists: {name}")


async def _ensure_unique_character_name(db: AsyncSession, *, project_id: str, name: str) -> None:
    stmt = select(Character.id).where(Character.project_id == project_id, Character.name == name)
    exists = (await db.execute(stmt)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail=f"Character name already exists in project: {name}")


async def _get_asset_id_by_name(
    db: AsyncSession,
    model: Any,  # noqa: ANN401
    *,
    name: str,
) -> str | None:
    stmt = select(model.id).where(model.name == name)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_character_id_by_name(db: AsyncSession, *, project_id: str, name: str) -> str | None:
    stmt = select(Character.id).where(Character.project_id == project_id, Character.name == name)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_draft_id_by_name(
    db: AsyncSession,
    model: Any,  # noqa: ANN401
    *,
    project_id: str,
    name: str,
) -> str | None:
    stmt = select(model.id).where(model.project_id == project_id, model.name == name)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_asset_by_name(db: AsyncSession, model: Any, *, name: str) -> Any:  # noqa: ANN401
    stmt = select(model).where(model.name == name)
    return (await db.execute(stmt)).scalars().one_or_none()


async def _delete_shot_draft_occurrences(db: AsyncSession, *, project_id: str, shot_id: str) -> None:
    await db.execute(
        delete(ImportDraftShotOccurrence).where(
            ImportDraftShotOccurrence.project_id == project_id,
            ImportDraftShotOccurrence.shot_id == shot_id,
        )
    )


async def _delete_shot_links(db: AsyncSession, *, shot_id: str) -> None:
    await db.execute(delete(ProjectSceneLink).where(ProjectSceneLink.shot_id == shot_id))
    await db.execute(delete(ProjectPropLink).where(ProjectPropLink.shot_id == shot_id))
    await db.execute(delete(ProjectCostumeLink).where(ProjectCostumeLink.shot_id == shot_id))
    await db.execute(delete(ShotCharacterLink).where(ShotCharacterLink.shot_id == shot_id))
    await db.execute(delete(ShotDialogLine).where(ShotDialogLine.shot_detail_id == shot_id))


async def _delete_character_prop_links(db: AsyncSession, *, character_id: str) -> None:
    await db.execute(delete(CharacterPropLink).where(CharacterPropLink.character_id == character_id))


@router.post(
    "/import-from-extraction",
    response_model=ApiResponse[ImportFromExtractionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="从信息提取草稿导入 Studio 数据",
    description=(
        "接收 StudioScriptExtractionDraft（name-based，不含 id），由接口生成 ID 并在一个事务内创建："
        "Scene/Prop/Costume/Character/Shot/ShotDetail/Links/ShotDialogLine。"
        "默认不覆盖：遇到同项目同名或同章节镜头 index 冲突即回滚报错并提示重复。"
        "设置 force_overwrite=true 时，将覆盖更新已存在数据并重建相关 links/对白。"
    ),
)
async def import_from_extraction(
    body: ImportFromExtractionRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ImportFromExtractionResponse]:
    await _ensure_project_and_chapter(db, body.project_id, body.chapter_id)

    # 需求口径：仅写入草稿与 shot 分镜（Shot/ShotDetail/ShotDialogLine），不写入资产表与资产关联链接表
    write_asset_tables = False

    # 默认不覆盖：预检冲突并提示重复
    if not body.force_overwrite:
        for s in body.shots:
            stmt = select(Shot.id).where(Shot.chapter_id == body.chapter_id, Shot.index == s.index)
            if (await db.execute(stmt)).scalar_one_or_none() is not None:
                raise HTTPException(status_code=400, detail=f"Shot index already exists in chapter: {s.index}")

        if write_asset_tables:
            for a in body.scenes:
                await _ensure_unique_asset_name(db, Scene, name=a.name)
            for a in body.props:
                await _ensure_unique_asset_name(db, Prop, name=a.name)
            for a in body.costumes:
                await _ensure_unique_asset_name(db, Costume, name=a.name)
            for c in body.characters:
                await _ensure_unique_character_name(db, project_id=body.project_id, name=c.name)

    scene_by_name: dict[str, str] = {}
    prop_by_name: dict[str, str] = {}
    costume_by_name: dict[str, str] = {}
    character_by_name: dict[str, str] = {}
    shot_by_index: dict[int, str] = {}

    created_counts: dict[str, int] = {
        "scenes": 0,
        "props": 0,
        "costumes": 0,
        "characters": 0,
        "shots": 0,
        "shot_details": 0,
        "shot_scene_links": 0,
        "shot_prop_links": 0,
        "shot_costume_links": 0,
        "shot_character_links": 0,
        "shot_dialog_lines": 0,
        "character_prop_links": 0,
        "updated_scenes": 0,
        "updated_props": 0,
        "updated_costumes": 0,
        "updated_characters": 0,
        "updated_shots": 0,
        "draft_scenes": 0,
        "draft_props": 0,
        "draft_costumes": 0,
        "draft_characters": 0,
        "updated_draft_scenes": 0,
        "updated_draft_props": 0,
        "updated_draft_costumes": 0,
        "updated_draft_characters": 0,
        "draft_shot_occurrences": 0,
    }

    # --- Upsert import drafts（用于“拍摄准备”页关联展示） ---
    scene_draft_by_name: dict[str, str] = {}
    prop_draft_by_name: dict[str, str] = {}
    costume_draft_by_name: dict[str, str] = {}
    character_draft_by_name: dict[str, str] = {}

    for a in body.scenes:
        existing_draft_id = await _get_draft_id_by_name(db, ImportSceneDraft, project_id=body.project_id, name=a.name)
        if existing_draft_id is not None:
            scene_draft_by_name[a.name] = existing_draft_id
            if body.force_overwrite:
                obj = await db.get(ImportSceneDraft, existing_draft_id)
                assert obj is not None
                obj.description = a.description
                obj.tags = a.tags
                obj.raw_extra = {}
                created_counts["updated_draft_scenes"] += 1
        else:
            draft_id = _new_id("scene_draft")
            scene_draft_by_name[a.name] = draft_id
            db.add(
                ImportSceneDraft(
                    id=draft_id,
                    project_id=body.project_id,
                    name=a.name,
                    description=a.description,
                    tags=a.tags,
                    raw_extra={},
                )
            )
            created_counts["draft_scenes"] += 1

    for a in body.props:
        existing_draft_id = await _get_draft_id_by_name(db, ImportPropDraft, project_id=body.project_id, name=a.name)
        if existing_draft_id is not None:
            prop_draft_by_name[a.name] = existing_draft_id
            if body.force_overwrite:
                obj = await db.get(ImportPropDraft, existing_draft_id)
                assert obj is not None
                obj.description = a.description
                obj.tags = a.tags
                obj.raw_extra = {}
                created_counts["updated_draft_props"] += 1
        else:
            draft_id = _new_id("prop_draft")
            prop_draft_by_name[a.name] = draft_id
            db.add(
                ImportPropDraft(
                    id=draft_id,
                    project_id=body.project_id,
                    name=a.name,
                    description=a.description,
                    tags=a.tags,
                    raw_extra={},
                )
            )
            created_counts["draft_props"] += 1

    for a in body.costumes:
        existing_draft_id = await _get_draft_id_by_name(db, ImportCostumeDraft, project_id=body.project_id, name=a.name)
        if existing_draft_id is not None:
            costume_draft_by_name[a.name] = existing_draft_id
            if body.force_overwrite:
                obj = await db.get(ImportCostumeDraft, existing_draft_id)
                assert obj is not None
                obj.description = a.description
                obj.tags = a.tags
                obj.raw_extra = {}
                created_counts["updated_draft_costumes"] += 1
        else:
            draft_id = _new_id("costume_draft")
            costume_draft_by_name[a.name] = draft_id
            db.add(
                ImportCostumeDraft(
                    id=draft_id,
                    project_id=body.project_id,
                    name=a.name,
                    description=a.description,
                    tags=a.tags,
                    raw_extra={},
                )
            )
            created_counts["draft_costumes"] += 1

    for c in body.characters:
        existing_draft_id = await _get_draft_id_by_name(
            db,
            ImportCharacterDraft,
            project_id=body.project_id,
            name=c.name,
        )
        if existing_draft_id is not None:
            character_draft_by_name[c.name] = existing_draft_id
            if body.force_overwrite:
                obj = await db.get(ImportCharacterDraft, existing_draft_id)
                assert obj is not None
                obj.description = c.description
                obj.tags = c.tags
                obj.raw_extra = {}
                created_counts["updated_draft_characters"] += 1
        else:
            draft_id = _new_id("char_draft")
            character_draft_by_name[c.name] = draft_id
            db.add(
                ImportCharacterDraft(
                    id=draft_id,
                    project_id=body.project_id,
                    name=c.name,
                    description=c.description,
                    tags=c.tags,
                    raw_extra={},
                )
            )
            created_counts["draft_characters"] += 1

    await db.flush()

    # --- Create / overwrite assets ---
    if write_asset_tables:
        for a in body.scenes:
            existing_id = await _get_asset_id_by_name(db, Scene, name=a.name)
            if existing_id is not None and body.force_overwrite:
                obj = await db.get(Scene, existing_id)
                assert obj is not None
                obj.description = a.description
                obj.tags = a.tags
                obj.prompt_template_id = a.prompt_template_id
                obj.view_count = a.view_count
                scene_by_name[a.name] = existing_id
                created_counts["updated_scenes"] += 1
            else:
                scene_id = _new_id("scene")
                scene_by_name[a.name] = scene_id
                db.add(
                    Scene(
                        id=scene_id,
                        name=a.name,
                        description=a.description,
                        tags=a.tags,
                        prompt_template_id=a.prompt_template_id,
                        view_count=a.view_count,
                    )
                )
                created_counts["scenes"] += 1

        for a in body.props:
            existing_id = await _get_asset_id_by_name(db, Prop, name=a.name)
            if existing_id is not None and body.force_overwrite:
                obj = await db.get(Prop, existing_id)
                assert obj is not None
                obj.description = a.description
                obj.tags = a.tags
                obj.prompt_template_id = a.prompt_template_id
                obj.view_count = a.view_count
                prop_by_name[a.name] = existing_id
                created_counts["updated_props"] += 1
            else:
                prop_id = _new_id("prop")
                prop_by_name[a.name] = prop_id
                db.add(
                    Prop(
                        id=prop_id,
                        name=a.name,
                        description=a.description,
                        tags=a.tags,
                        prompt_template_id=a.prompt_template_id,
                        view_count=a.view_count,
                    )
                )
                created_counts["props"] += 1

        for a in body.costumes:
            existing_id = await _get_asset_id_by_name(db, Costume, name=a.name)
            if existing_id is not None and body.force_overwrite:
                obj = await db.get(Costume, existing_id)
                assert obj is not None
                obj.description = a.description
                obj.tags = a.tags
                obj.prompt_template_id = a.prompt_template_id
                obj.view_count = a.view_count
                costume_by_name[a.name] = existing_id
                created_counts["updated_costumes"] += 1
            else:
                costume_id = _new_id("costume")
                costume_by_name[a.name] = costume_id
                db.add(
                    Costume(
                        id=costume_id,
                        name=a.name,
                        description=a.description,
                        tags=a.tags,
                        prompt_template_id=a.prompt_template_id,
                        view_count=a.view_count,
                    )
                )
                created_counts["costumes"] += 1

        await db.flush()

        # --- Create / overwrite characters ---
        for c in body.characters:
            costume_id = costume_by_name.get(c.costume_name) if c.costume_name else None
            existing_id = await _get_character_id_by_name(db, project_id=body.project_id, name=c.name)
            if existing_id is not None and body.force_overwrite:
                obj = await db.get(Character, existing_id)
                assert obj is not None
                obj.description = c.description
                obj.actor_id = None
                obj.costume_id = costume_id
                character_by_name[c.name] = existing_id
                created_counts["updated_characters"] += 1
                await _delete_character_prop_links(db, character_id=existing_id)
            else:
                char_id = _new_id("char")
                character_by_name[c.name] = char_id
                db.add(
                    Character(
                        id=char_id,
                        project_id=body.project_id,
                        name=c.name,
                        description=c.description,
                        actor_id=None,
                        costume_id=costume_id,
                    )
                )
                created_counts["characters"] += 1

        await db.flush()

        # --- CharacterPropLink ---
        for c in body.characters:
            if not c.prop_names:
                continue
            char_id = character_by_name[c.name]
            for idx, prop_name in enumerate(c.prop_names):
                prop_id = prop_by_name.get(prop_name)
                if prop_id is None:
                    raise HTTPException(status_code=400, detail=f"Unknown prop_name referenced by character: {prop_name}")
                db.add(
                    CharacterPropLink(
                        character_id=char_id,
                        prop_id=prop_id,
                        index=idx,
                        note="",
                    )
                )
                created_counts["character_prop_links"] += 1

        await db.flush()

    # --- Create / overwrite shots + details ---
    scene_id_cache: dict[str, str | None] = {}
    for s in body.shots:
        existing_shot_id = (await db.execute(
            select(Shot.id).where(Shot.chapter_id == body.chapter_id, Shot.index == s.index)
        )).scalar_one_or_none()
        if existing_shot_id is not None and body.force_overwrite:
            obj = await db.get(Shot, existing_shot_id)
            assert obj is not None
            obj.title = s.title
            obj.script_excerpt = s.script_excerpt
            shot_id = existing_shot_id
            shot_by_index[s.index] = shot_id
            created_counts["updated_shots"] += 1
        else:
            shot_id = _new_id("shot")
            shot_by_index[s.index] = shot_id
            db.add(
                Shot(
                    id=shot_id,
                    chapter_id=body.chapter_id,
                    index=s.index,
                    title=s.title,
                    thumbnail="",
                    status="pending",
                    script_excerpt=s.script_excerpt,
                    generated_video_file_id=None,
                )
            )
            created_counts["shots"] += 1

        # 不创建 Scene 资产，只尝试按 name 读取已存在的 Scene
        scene_id: str | None = None
        for scene_token in _split_scene_names(s.scene_name):
            if scene_token not in scene_id_cache:
                scene_id_cache[scene_token] = await _get_asset_id_by_name(db, Scene, name=scene_token)
            if scene_id_cache[scene_token]:
                scene_id = scene_id_cache[scene_token]
                break
        detail = await db.get(ShotDetail, shot_id)
        if detail is None:
            db.add(
                ShotDetail(
                    id=shot_id,
                    camera_shot=CameraShotType.ms,
                    angle=CameraAngle.eye_level,
                    movement=CameraMovement.static,
                    scene_id=scene_id,
                    duration=0,
                    mood_tags=[],
                    atmosphere="",
                    follow_atmosphere=True,
                    has_bgm=False,
                    vfx_type=VFXType.none,
                    vfx_note="",
                    description="",
                    prompt_template_id=None,
                    first_frame_prompt="",
                    last_frame_prompt="",
                    key_frame_prompt="",
                )
            )
            created_counts["shot_details"] += 1
        else:
            detail.scene_id = scene_id

    await db.flush()

    # --- Create shot dialog lines（不创建 project_link/shot character links） ---
    character_id_cache: dict[str, str | None] = {}
    for s in body.shots:
        shot_id = shot_by_index[s.index]
        if body.force_overwrite:
            await _delete_shot_links(db, shot_id=shot_id)
            await _delete_shot_draft_occurrences(db, project_id=body.project_id, shot_id=shot_id)

        # --- Upsert draft occurrences（用于“拍摄准备”页按镜头筛选） ---
        seen_scene: set[str] = set()
        for scene_token in _split_scene_names(s.scene_name):
            if scene_token in seen_scene:
                continue
            seen_scene.add(scene_token)
            draft_id = scene_draft_by_name.get(scene_token)
            if draft_id is None:
                # 仅草稿写入时：缺失的草稿不依赖资产表回查，直接创建最小 draft
                if write_asset_tables and body.force_overwrite:
                    scene_obj = await _get_asset_by_name(db, Scene, name=scene_token)
                    if scene_obj is not None:
                        draft_id = _new_id("scene_draft")
                        scene_draft_by_name[scene_token] = draft_id
                        db.add(
                            ImportSceneDraft(
                                id=draft_id,
                                project_id=body.project_id,
                                name=scene_token,
                                description=scene_obj.description,
                                tags=scene_obj.tags,
                                raw_extra={},
                            )
                        )
                        created_counts["draft_scenes"] += 1
                if draft_id is None:
                    draft_id = _new_id("scene_draft")
                    scene_draft_by_name[scene_token] = draft_id
                    db.add(
                        ImportSceneDraft(
                            id=draft_id,
                            project_id=body.project_id,
                            name=scene_token,
                            description="",
                            tags=[],
                            raw_extra={},
                        )
                    )
                    created_counts["draft_scenes"] += 1
            db.add(
                ImportDraftShotOccurrence(
                    id=_new_id("occ"),
                    project_id=body.project_id,
                    chapter_id=body.chapter_id,
                    shot_id=shot_id,
                    draft_type=ImportDraftType.scene,
                    draft_id=draft_id,
                )
            )
            created_counts["draft_shot_occurrences"] += 1

        seen_char: set[str] = set()
        for char_name in s.character_names:
            if char_name in seen_char:
                continue
            seen_char.add(char_name)
            draft_id = character_draft_by_name.get(char_name)
            if draft_id is None:
                if write_asset_tables and body.force_overwrite:
                    char_stmt = select(Character).where(Character.project_id == body.project_id, Character.name == char_name)
                    char_obj = (await db.execute(char_stmt)).scalars().one_or_none()
                    if char_obj is not None:
                        draft_id = _new_id("char_draft")
                        character_draft_by_name[char_name] = draft_id
                        db.add(
                            ImportCharacterDraft(
                                id=draft_id,
                                project_id=body.project_id,
                                name=char_name,
                                description=char_obj.description,
                                tags=[],
                                raw_extra={},
                            )
                        )
                        created_counts["draft_characters"] += 1
                if draft_id is None:
                    draft_id = _new_id("char_draft")
                    character_draft_by_name[char_name] = draft_id
                    db.add(
                        ImportCharacterDraft(
                            id=draft_id,
                            project_id=body.project_id,
                            name=char_name,
                            description="",
                            tags=[],
                            raw_extra={},
                        )
                    )
                    created_counts["draft_characters"] += 1
            db.add(
                ImportDraftShotOccurrence(
                    id=_new_id("occ"),
                    project_id=body.project_id,
                    chapter_id=body.chapter_id,
                    shot_id=shot_id,
                    draft_type=ImportDraftType.character,
                    draft_id=draft_id,
                )
            )
            created_counts["draft_shot_occurrences"] += 1

        seen_prop: set[str] = set()
        for prop_name in s.prop_names:
            if prop_name in seen_prop:
                continue
            seen_prop.add(prop_name)
            draft_id = prop_draft_by_name.get(prop_name)
            if draft_id is None:
                if write_asset_tables and body.force_overwrite:
                    prop_obj = await _get_asset_by_name(db, Prop, name=prop_name)
                    if prop_obj is not None:
                        draft_id = _new_id("prop_draft")
                        prop_draft_by_name[prop_name] = draft_id
                        db.add(
                            ImportPropDraft(
                                id=draft_id,
                                project_id=body.project_id,
                                name=prop_name,
                                description=prop_obj.description,
                                tags=prop_obj.tags,
                                raw_extra={},
                            )
                        )
                        created_counts["draft_props"] += 1
                if draft_id is None:
                    draft_id = _new_id("prop_draft")
                    prop_draft_by_name[prop_name] = draft_id
                    db.add(
                        ImportPropDraft(
                            id=draft_id,
                            project_id=body.project_id,
                            name=prop_name,
                            description="",
                            tags=[],
                            raw_extra={},
                        )
                    )
                    created_counts["draft_props"] += 1
            db.add(
                ImportDraftShotOccurrence(
                    id=_new_id("occ"),
                    project_id=body.project_id,
                    chapter_id=body.chapter_id,
                    shot_id=shot_id,
                    draft_type=ImportDraftType.prop,
                    draft_id=draft_id,
                )
            )
            created_counts["draft_shot_occurrences"] += 1

        seen_costume: set[str] = set()
        for costume_name in s.costume_names:
            if costume_name in seen_costume:
                continue
            seen_costume.add(costume_name)
            draft_id = costume_draft_by_name.get(costume_name)
            if draft_id is None:
                if write_asset_tables and body.force_overwrite:
                    costume_obj = await _get_asset_by_name(db, Costume, name=costume_name)
                    if costume_obj is not None:
                        draft_id = _new_id("costume_draft")
                        costume_draft_by_name[costume_name] = draft_id
                        db.add(
                            ImportCostumeDraft(
                                id=draft_id,
                                project_id=body.project_id,
                                name=costume_name,
                                description=costume_obj.description,
                                tags=costume_obj.tags,
                                raw_extra={},
                            )
                        )
                        created_counts["draft_costumes"] += 1
                if draft_id is None:
                    draft_id = _new_id("costume_draft")
                    costume_draft_by_name[costume_name] = draft_id
                    db.add(
                        ImportCostumeDraft(
                            id=draft_id,
                            project_id=body.project_id,
                            name=costume_name,
                            description="",
                            tags=[],
                            raw_extra={},
                        )
                    )
                    created_counts["draft_costumes"] += 1
            db.add(
                ImportDraftShotOccurrence(
                    id=_new_id("occ"),
                    project_id=body.project_id,
                    chapter_id=body.chapter_id,
                    shot_id=shot_id,
                    draft_type=ImportDraftType.costume,
                    draft_id=draft_id,
                )
            )
            created_counts["draft_shot_occurrences"] += 1

        for line in s.dialogue_lines:
            speaker_id: str | None = None
            target_id: str | None = None
            if line.speaker_name:
                if line.speaker_name not in character_id_cache:
                    character_id_cache[line.speaker_name] = await _get_character_id_by_name(
                        db, project_id=body.project_id, name=line.speaker_name
                    )
                speaker_id = character_id_cache[line.speaker_name]
            if line.target_name:
                if line.target_name not in character_id_cache:
                    character_id_cache[line.target_name] = await _get_character_id_by_name(
                        db, project_id=body.project_id, name=line.target_name
                    )
                target_id = character_id_cache[line.target_name]
            db.add(
                ShotDialogLine(
                    shot_detail_id=shot_id,
                    index=line.index,
                    text=line.text,
                    line_mode=DialogueLineMode(line.line_mode),
                    speaker_character_id=speaker_id,
                    target_character_id=target_id,
                    speaker_name=line.speaker_name,
                    target_name=line.target_name,
                )
            )
            created_counts["shot_dialog_lines"] += 1

    await db.flush()

    payload = ImportFromExtractionResponse(
        created=created_counts,
        ids={
            "scenes": scene_by_name,
            "props": prop_by_name,
            "costumes": costume_by_name,
            "characters": character_by_name,
            "scene_drafts": scene_draft_by_name,
            "prop_drafts": prop_draft_by_name,
            "costume_drafts": costume_draft_by_name,
            "character_drafts": character_draft_by_name,
            "shots": {str(k): v for k, v in shot_by_index.items()},
        },
    )
    return success_response(payload, code=201)

