"""提取类 Agent：实体抽取、分镜抽取，含影视专用规范化。"""

from __future__ import annotations

from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase
from app.schemas.skills.film import FilmEntityExtractionResult, FilmShotlistResult


# ---------------------------------------------------------------------------
# 影视实体/分镜结果规范化（供 FilmEntityExtractorAgent / FilmShotlistStoryboarderAgent 使用）
# ---------------------------------------------------------------------------


def _normalize_entity_result(data: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 常见字段名/结构映射为 FilmEntityExtractionResult 所需。"""
    data = dict(data)
    for key in ("characters", "locations", "props"):
        if key not in data or not isinstance(data[key], list):
            continue
        out = []
        for item in list(data[key]):
            item = dict(item)
            if "name" not in item and item.get("normalized_name"):
                item["name"] = item["normalized_name"]
            if "evidence" in item:
                ev = item.pop("evidence", [])
                if ev and "first_appearance" not in item:
                    item["first_appearance"] = ev[0] if isinstance(ev[0], dict) else None
            if key != "characters":
                item.pop("aliases", None)
            out.append(item)
        data[key] = out
    if "chunks" not in data:
        data["chunks"] = []
    return data


def _norm_character(c: dict[str, Any]) -> dict[str, Any]:
    c = dict(c)
    if "id" not in c and c.get("character_id"):
        c["id"] = c.pop("character_id")
    return c


def _norm_scene(s: dict[str, Any]) -> dict[str, Any]:
    s = dict(s)
    if "id" not in s and s.get("scene_id"):
        s["id"] = s.pop("scene_id")
    if "summary" not in s and s.get("description"):
        s["summary"] = s.pop("description")
    return s


def _norm_shot(s: dict[str, Any], index: int = 0) -> dict[str, Any]:
    s = dict(s)
    if "id" not in s and s.get("shot_id"):
        s["id"] = s.pop("shot_id")
    if "order" not in s:
        s["order"] = index + 1
    if "evidence_spans" in s:
        s["evidence"] = s.pop("evidence_spans", [])
    if "vfx_type" in s and "vfx" not in s:
        vfx_type = s.pop("vfx_type", "NONE")
        s["vfx"] = [{"vfx_type": vfx_type}]
    return s


def _norm_transition(
    t: dict[str, Any], index: int = 0, shot_ids: list[str] | None = None
) -> dict[str, Any]:
    t = dict(t)
    t.pop("transition_id", None)
    t.pop("evidence_spans", None)
    if "transition" not in t and t.get("transition_type"):
        t["transition"] = t.pop("transition_type")
    if "from_shot_id" not in t or "to_shot_id" not in t:
        shot_ids = shot_ids or []
        if index + 1 < len(shot_ids):
            t.setdefault("from_shot_id", shot_ids[index])
            t.setdefault("to_shot_id", shot_ids[index + 1])
    return t


def _normalize_shotlist_result(data: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 常见字段名/结构映射为 FilmShotlistResult(ProjectCinematicBreakdown) 所需。"""
    if "breakdown" not in data:
        return data
    b = dict(data["breakdown"])
    if "characters" in b:
        b["characters"] = [_norm_character(c) for c in b["characters"]]
    if "scenes" in b:
        b["scenes"] = [_norm_scene(s) for s in b["scenes"]]
    if "shots" in b:
        b["shots"] = [_norm_shot(s, i) for i, s in enumerate(b["shots"])]
    if "transitions" in b:
        shots = b.get("shots") or []
        shot_ids = [
            s.get("id") or (s.get("shot_id") if isinstance(s, dict) else None)
            for s in shots
        ]
        shot_ids = [x for x in shot_ids if x]
        b["transitions"] = [
            _norm_transition(t, i, shot_ids) for i, t in enumerate(b["transitions"])
        ]
    data["breakdown"] = b
    return data


# ---------------------------------------------------------------------------
# 提取类 Agent 实现
# ---------------------------------------------------------------------------

_ENTITY_EXTRACTION_SYSTEM_PROMPT = """\
你是“影视文本信息抽取系统”。你的唯一任务是：从输入小说原文中抽取【人物】【地点】【道具】，并给出可追溯证据。

## 硬性规则（必须遵守）
- 绝对禁止编造：不得凭常识补全姓名、身份、外貌、地点类型、道具用途等；原文没写就不写。
- 只抽取原文明确出现的实体：如果只是“他/她/那里/东西”等代词且无法指代明确实体，不要强行新建实体；可在 uncertainties 说明原因。
- 所有实体的关键字段都应尽量附带 EvidenceSpan（至少给 first_appearance；quote ≤ 200 字，必须是原文摘录）。
- 不要输出 schemas 未定义的字段；输出 JSON，且必须能被 Pydantic 校验（extra=forbid）。
- ID 规则：characters 用 char_001 起；locations 用 loc_001 起；props 用 prop_001 起。保持稳定、不要跳号。
- 同一实体可能有多个称呼：把原文出现的别名放进 aliases；normalized_name 只能来自原文（例如原文既叫“王二”也叫“二哥”）。
- confidence：可选；如果给出必须在 0-1 之间；不确定就留空。

## 输出结构
输出必须是一个 JSON 对象，符合下列模型（字段名必须完全一致）：
- source_id: string
- language?: string
- extraction_version?: string
- schema_version?: string
- chunks: string[]
- characters: Character[]
- locations: Location[]
- props: Prop[]
- notes: string[]
- uncertainties: Uncertainty[]

其中 Character/Location/Prop/EvidenceSpan/Uncertainty 的字段以 schemas 为准：
- EvidenceSpan: { chunk_id, start_char?, end_char?, quote? }
- Uncertainty: { field_path, reason, evidence[] }

## 抽取策略（尽量“忠实 + 可用”）
- 人物：优先抽取具名角色；对“掌柜/车夫/士兵”等泛称，只有在原文多次出现且可作为角色稳定识别时才建人物。
- 地点：出现明确地名/场所名时抽取；若只是“屋里/门外”且无稳定命名，可不抽取或写入 uncertainties。
- 道具：只抽取剧情关键或明确被提及的物件（信件、刀、钥匙、手机等）。不要把“桌椅板凳”当道具堆砌，除非原文强调其关键性。

只输出 JSON，不要输出任何解释性文字。
"""

FILM_ENTITY_EXTRACTION_PROMPT = PromptTemplate(
    input_variables=["source_id", "language", "chunks_json"],
    template="""## 输入
source_id: {source_id}
language: {language}
chunks (JSON 数组，元素含 chunk_id 与 text):
{chunks_json}

## 输出
请输出 FilmEntityExtractionResult 的 JSON。
""",
)

_SHOTLIST_SYSTEM_PROMPT = """\
你是“影视分镜师（Shot List / Storyboard Breakdown）”。你的任务是把给定小说原文拆解为可拍摄的场景与镜头表。

## 硬性规则（必须遵守）
- 绝对禁止编造：不得新增原文不存在的人物/地点/道具/动作/对白/情节；不得凭常识补全。
- 如果原文不确定（比如光线、时间、人物是谁、是否在室内外），请：
  - 在对应字段保持 UNKNOWN/空值，或
  - 写入 uncertainties（field_path + reason + evidence），而不是“猜一个”。
- 所有镜头描述必须“可拍”：明确画面内容与动作，不要抽象文学化抒情。
- 只使用 schemas 中允许的枚举值：
  - ShotType: ECU/CU/MCU/MS/MLS/LS/ELS
  - CameraAngle: EYE_LEVEL/HIGH_ANGLE/LOW_ANGLE/BIRD_EYE/DUTCH/OVER_SHOULDER
  - CameraMovement: STATIC/PAN/TILT/DOLLY_IN/DOLLY_OUT/TRACK/CRANE/HANDHELD/STEADICAM/ZOOM_IN/ZOOM_OUT
  - TransitionType: CUT/DISSOLVE/WIPE/FADE_IN/FADE_OUT/MATCH_CUT/J_CUT/L_CUT
  - VFXType: NONE/PARTICLES/VOLUMETRIC_FOG/CG_DOUBLE/DIGITAL_ENVIRONMENT/MATTE_PAINTING/FIRE_SMOKE/WATER_SIM/DESTRUCTION/ENERGY_MAGIC/COMPOSITING_CLEANUP/SLOW_MOTION_TIME/OTHER
- EvidenceSpan.quote ≤ 200 字，必须来自原文摘录；chunk_id 必须来自输入。
- 只输出 JSON（不要解释、不要 markdown、不要多余文本），并且必须能通过 Pydantic 校验（extra=forbid）。

## 输出结构
输出必须是一个 JSON 对象，符合 FilmShotlistResult：
{
  "breakdown": ProjectCinematicBreakdown
}

## 拆解原则（专业且忠实）
- 先抽取实体表（characters/locations/props），再按叙事推进切分 scenes（场景变化依据：地点/时间/人物组合或叙事段落明显转折）。
- 每个 scene 建议 2-8 个 shot；shot.description 用“行业口吻 + 可拍动作”描述。
- 对白处理：
  - 原文出现引号对白时，尽量拆进 DialogueLine.text（逐句，尽量原句）。
  - speaker/target 不确定可留空，但要把 evidence 填好；必要时在 uncertainties 说明。
  - 旁白/心理独白如果原文明确，可用 VOICE_OVER；画外音用 OFF_SCREEN；电话音用 PHONE。
- 转场 transitions：
  - 同一 scene 内镜头间通常 CUT；明显时间跳跃/回忆可用 DISSOLVE/FADE；声音先行可用 J_CUT/L_CUT（仅当原文能支撑）。
- VFX：
  - 原文明确出现超自然/烟火/水效/破碎/慢动作等才写；否则 vfx_type=NONE。
- 时长 duration_sec 可选：只有在原文节奏/动作明确时才给出，否则留空。

## ID 规则（必须）
- scene_id: scene_001 起
- shot_id: shot_{sceneIndex3}_{order3}，例如 scene_001 的第3镜是 shot_001_003
- from/to_shot_id 必须引用存在的 shot_id

只输出 JSON。
"""

FILM_SHOTLIST_PROMPT = PromptTemplate(
    input_variables=["source_id", "source_title", "language", "chunks_json"],
    template="""## 输入
source_id: {source_id}
source_title: {source_title}
language: {language}
chunks (JSON 数组，元素含 chunk_id 与 text):
{chunks_json}

## 输出
请输出 FilmShotlistResult 的 JSON。
""",
)


class FilmEntityExtractorAgent(AgentBase[FilmEntityExtractionResult]):
    """关键信息提取 Agent：使用 film_entity_extractor skill，输出人物/地点/道具。"""

    @property
    def system_prompt(self) -> str:
        return _ENTITY_EXTRACTION_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return FILM_ENTITY_EXTRACTION_PROMPT

    @property
    def output_model(self) -> type[FilmEntityExtractionResult]:
        return FilmEntityExtractionResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        return _normalize_entity_result(data)


class FilmShotlistStoryboarderAgent(AgentBase[FilmShotlistResult]):
    """分镜提取 Agent：使用 film_shotlist skill，输出场景/镜头/转场（ProjectCinematicBreakdown）。"""

    @property
    def system_prompt(self) -> str:
        return _SHOTLIST_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return FILM_SHOTLIST_PROMPT

    @property
    def output_model(self) -> type[FilmShotlistResult]:
        return FilmShotlistResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        return _normalize_shotlist_result(data)
