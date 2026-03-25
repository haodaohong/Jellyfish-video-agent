"""脚本处理 Agent：分镜分割、信息提取、实体合并、变体分析、一致性检查、输出编译。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase, _extract_json_from_text
from app.schemas.skills.script_processing import (
    OutputCompileResult,
    ScriptConsistencyCheckResult,
    ScriptDivisionResult,
    ScriptOptimizationResult,
    ShotElementExtractionResult,
    StudioScriptExtractionDraft,
    EntityMergeResult,
    VariantAnalysisResult,
    ShotDivision,
)

# PromptTemplates（固化在本模块，供各 Agent 子类通过 @property 返回）
_SCRIPT_DIVIDER_SYSTEM_PROMPT = """\
你是\"剧本分镜师\"。将完整剧本分割为多个镜头。每个镜头应是完整的连贯场景。
为每个镜头提供：
- index（镜头序号，章节内唯一；从 1 开始）
- start_line、end_line
- shot_name（镜头名称/镜头标题，分镜名；一句话描述该镜头画面/动作；不要把它当作场景名）
- script_excerpt（镜头对应的剧本摘录/文本）
- scene_name（场景名称，必须与 shots 中 scene_name 的含义一致；不要把 shot_name 当成 scene_name）
- time_of_day
- character_names_in_text（角色名/称呼，弱信息；稳定ID会在后续合并阶段统一分配）
严格区分字段含义：
- shot_name = 分镜名/镜头标题
- scene_name = 场景名
只输出 JSON，符合 ScriptDivisionResult 结构。
"""

SCRIPT_DIVIDER_PROMPT = PromptTemplate(
    input_variables=["script_text"],
    template="## 输入脚本\n{script_text}\n\n## 输出\n",
)

_ELEMENT_EXTRACTOR_SYSTEM_PROMPT = """\
你是\"镜头元素提取员\"。从单个镜头提取关键信息：
- character_keys、scene_keys、costume_keys、prop_keys（弱ID/归一化名；稳定ID由后续合并阶段统一分配）
- characters_detailed（每个角色含 character_key/name_in_text/appearance/clothing/accessories/state + raw_* 溯源，可选 evidence）
- props_detailed（每个道具含 prop_key/name_in_text/description/state/interaction + raw_text，可选 evidence）
- scene_detailed（scene_key/name/location_detail/atmosphere/time_weather/raw_description_text，可选 evidence）
- dialogue_lines（结构化对白，字段与 schemas.DialogueLine 对齐）
- actions、shot_type_hints、confidence_breakdown
其中 dialogue_lines 每项必须包含 text/line_mode；建议包含 index/speaker_character_id/target_character_id（若可判定）。
严格按照原文，不要编造。只输出 JSON，符合 ShotElementExtractionResult 结构。
"""

ELEMENT_EXTRACTOR_PROMPT = PromptTemplate(
    input_variables=["index", "shot_text", "context_summary", "shot_division_json"],
    template="镜头号: {index}\n分镜元信息(来自上一步): {shot_division_json}\n上文: {context_summary}\n\n## 镜头文本\n{shot_text}\n\n## 输出\n",
)

_ENTITY_MERGER_SYSTEM_PROMPT = """\
你是\"实体合并师\"。合并多镜头提取结果，统一实体定义，为每个实体分配ID，识别变体和冲突。
请输出 EntityMergeResult，merged_library 中至少包含 characters/locations/scenes/props 四类。
每个实体条目（EntityEntry）需包含：
- 通用：id/name/type/description/aliases/normalized_name/confidence/first_appearance/evidence/first_shot/appearances/variants
- 角色（type=character）：尽量补充 costume_note、traits
- 地点（type=location）：尽量补充 location_type
- 道具（type=prop）：尽量补充 category、owner_character_id
variants 使用 {variant_key, description, affected_shots, evidence} 的最小结构。
当提供 previous_merge_json 与 conflict_resolutions_json 时，表示这是一次“重试合并”：你必须参考上一次的合并结果与冲突解决建议，优先消解 conflicts；必要时可调整实体合并/拆分策略，但要保持 ID 尽量稳定（除非建议明确要求变更）。
只输出 JSON，符合 EntityMergeResult 结构。
"""

ENTITY_MERGER_PROMPT = PromptTemplate(
    input_variables=[
        "all_extractions_json",
        "historical_library_json",
        "script_division_json",
        "previous_merge_json",
        "conflict_resolutions_json",
    ],
    template=(
        "## 脚本分镜(来自上一步)\n{script_division_json}\n\n"
        "## 所有镜头提取结果\n{all_extractions_json}\n\n"
        "## 历史实体库\n{historical_library_json}\n\n"
        "## 上一次合并结果（可选，用于重试）\n{previous_merge_json}\n\n"
        "## 冲突解决建议（可选，用于重试）\n{conflict_resolutions_json}\n\n"
        "## 输出\n"
    ),
)

_VARIANT_ANALYZER_SYSTEM_PROMPT = """\
你是\"变体分析师\"。分析实体变体（特别是角色服装变化），构建时间线，生成变体建议。
输出 VariantAnalysisResult：costume_timelines.timeline_entries 使用 {shot_index, scene_id, costume_note, changes, evidence}；variant_suggestions 可带 evidence。
只输出 JSON，符合 VariantAnalysisResult 结构。
"""

VARIANT_ANALYZER_PROMPT = PromptTemplate(
    input_variables=["merged_library_json", "all_extractions_json", "script_division_json"],
    template="## 脚本分镜(来自上一步)\n{script_division_json}\n\n## 合并后的实体库\n{merged_library_json}\n\n## 所有镜头提取结果\n{all_extractions_json}\n\n## 输出\n",
)

_CONSISTENCY_CHECKER_SYSTEM_PROMPT = """\
你是\"一致性检查员\"。只做一件事：检测原文中是否把“同一个角色”在不同段落/镜头中赋予了不同的身份或行为主体，导致角色混淆（例如：同名不同人、代词指代混乱、行为归属错位）。

输出 ScriptConsistencyCheckResult：
- issues: 每条问题必须包含 character_candidates、description、suggestion；尽量给出 affected_lines（start_line/end_line）。
- has_issues: issues 非空则为 true

只输出 JSON。
"""

CONSISTENCY_CHECKER_PROMPT = PromptTemplate(
    input_variables=["script_text"],
    template="## 原文剧本\n{script_text}\n\n## 输出\n",
)

_SCRIPT_OPTIMIZER_SYSTEM_PROMPT = """\
你是\"剧本优化师\"。仅当一致性检查发现角色混淆问题时，对原文进行最小改写以消除混淆。

输入：
- script_text：原文
- consistency_json：一致性检查输出（ScriptConsistencyCheckResult）

输出 ScriptOptimizationResult：
- optimized_script_text：优化后的完整剧本文本（尽量少改，只改与 issues 相关的段落）
- change_summary：逐条对应 issues 的改动摘要

只输出 JSON。
"""

SCRIPT_OPTIMIZER_PROMPT = PromptTemplate(
    input_variables=["script_text", "consistency_json"],
    template="## 一致性检查结果\n{consistency_json}\n\n## 原文剧本\n{script_text}\n\n## 输出\n",
)

_SCRIPT_EXTRACTOR_SYSTEM_PROMPT = """\
你是\"Studio 信息提取员\"。你的任务是：基于剧本文本与分镜结果，输出可直接导入 Studio 的草稿结构 StudioScriptExtractionDraft（注意：ID 由导入 API 生成，因此这里全部使用 name 做引用键）。

输出 StudioScriptExtractionDraft：
- project_id（必填）
- chapter_id（必填）
- script_text（必填）
- characters: [{name, description, costume_name?, prop_names[], tags[]}]
- scenes/props/costumes: [{name, description, tags[], prompt_template_id?, view_count}]
- shots: [{index, title, script_excerpt, scene_name?, character_names[], prop_names[], costume_names[], dialogue_lines[], actions[]}]
  - dialogue_lines: [{index, text, line_mode, speaker_name?, target_name?}]

强约束：
- 同名实体在输出中只出现一次（全局去重）；shots 中引用必须使用同一名称
- shots.index 必须覆盖并对应输入分镜中的 index（不要跳号）
- 不要输出任何 id 字段（包括 char_001 等），由导入 API 生成

一致性强约束（必须严格遵守，否则导入会失败）：
- 先输出全局 characters/scenes/props/costumes 列表，再输出 shots；并把它们视为“字典”。
- shots[*].character_names / prop_names / costume_names / scene_name 只能从对应全局列表的 name 中选择（完全一致的字符串），禁止生成任何未在全局列表中出现的新名字。
- 禁止“同义名/括号变体/临时称呼”漂移：例如禁止在 shots 中写「女子（群）」但在 characters 中没有该条目；禁止「仙女A」与「仙女 A」混用。
- 遇到群体角色/泛指角色（如“女子（群）”“群众”“村民们”）：必须在 characters 列表中创建一条同名角色（name 完全一致），并在 shots 中引用该 name。
- 对于难以确定是否同一角色的称呼：宁可在 characters 里拆成两条不同 name，也不要在 shots 中凭空换名。
- 输出 shots 之前，必须做“全集校验”并补齐缺失：所有 shots[*] 中出现的 character_names/prop_names/costume_names/scene_name 的名字集合，必须都能在对应全局列表（characters/props/costumes/scenes）的 name 中找到；如果有缺失，必须在全局列表中补齐对应条目（描述可最小化，但 name 必须完全一致），禁止用别名替换来绕过。
- 角色名/场景名必须原样保留字符细节：包括全角/半角括号、空格、标点，不要自动做任何规范化或替换（例如不能把「女子（群）」改成「女子(群)」或「女子 （群）」）。
- 严格区分：shots[*].title 是“镜头标题”（一句话描述该镜头画面/动作），不要拿它当作 scenes 的 scene 名；shots[*].scene_name 才是场景名称，必须来自 scenes 全局列表的 name。

输入：
- project_id
- chapter_id
- script_text
- script_division_json（ScriptDivisionResult）
- consistency_json（可选）

只输出 JSON。
"""

SCRIPT_EXTRACTOR_PROMPT = PromptTemplate(
    input_variables=["project_id", "chapter_id", "script_text", "script_division_json", "consistency_json"],
    template=(
        "## project_id\n{project_id}\n\n"
        "## chapter_id\n{chapter_id}\n\n"
        "## 一致性检查（可选）\n{consistency_json}\n\n"
        "## 分镜结果\n{script_division_json}\n\n"
        "## 剧本文本\n{script_text}\n\n"
        "## 输出\n"
    ),
)

_OUTPUT_COMPILER_SYSTEM_PROMPT = """\
你是\"输出编译员\"。汇总所有Agent输出，生成完整项目JSON、可导出表格、项目总结。
输出 OutputCompileResult，其中 project_json 必须严格符合 ProjectCinematicBreakdown schema（至少包含 source_id/chunks/characters/locations/props/scenes/shots/transitions/notes/uncertainties）。
只输出 JSON。
"""

OUTPUT_COMPILER_PROMPT = PromptTemplate(
    input_variables=["division_json", "all_extractions_json", "merge_json", "variant_json", "consistency_json"],
    template="## 分镜结果\n{division_json}\n\n## 所有逐镜提取\n{all_extractions_json}\n\n## 实体合并\n{merge_json}\n\n## 变体分析\n{variant_json}\n\n## 一致性检查\n{consistency_json}\n\n## 输出\n",
)


# ============================================================================
# 1. ScriptDividerAgent - 剧本自动分镜
# ============================================================================

class ScriptDividerAgent(AgentBase[ScriptDivisionResult]):
    """剧本自动分镜：输入完整剧本文本，输出分镜列表。"""

    @property
    def system_prompt(self) -> str:
        return _SCRIPT_DIVIDER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return SCRIPT_DIVIDER_PROMPT

    @property
    def output_model(self) -> type[ScriptDivisionResult]:
        return ScriptDivisionResult

    def format_output(self, raw: str) -> ScriptDivisionResult:
        """
        更强的兜底解析：
        LLM 可能输出：
        - 正常结构：{shots:[...], total_shots:N}
        - 包裹结构：{"ScriptDivisionResult": {...}}
        - 直接列表：[{...}, {...}]（视为 shots）
        """
        json_str = _extract_json_from_text(raw)
        data: Any = json.loads(json_str)

        if isinstance(data, list):
            data = {"shots": data}
        elif isinstance(data, dict) and "ScriptDivisionResult" in data:
            inner = data.get("ScriptDivisionResult")
            if isinstance(inner, list):
                data = {"shots": inner}
            elif isinstance(inner, dict):
                data = inner
            else:
                data = {"shots": []}

        if isinstance(data, dict):
            data = self._normalize(data)

        return self.output_model.model_validate(data)  # type: ignore[arg-type]

    def divide_script(self, *, script_text: str) -> ScriptDivisionResult:
        return self.extract(script_text=script_text)

    async def adivide_script(self, *, script_text: str) -> ScriptDivisionResult:
        return await self.aextract(script_text=script_text)

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """规范化脚本分割结果。"""
        data = dict(data)

        # 兼容：LLM 可能输出 {"ScriptDivisionResult": {...}} 或 {"ScriptDivisionResult": [...]}
        if "ScriptDivisionResult" in data:
            inner = data.get("ScriptDivisionResult")
            if isinstance(inner, list):
                data = {"shots": inner}
            elif isinstance(inner, dict):
                data = dict(inner)
            else:
                data = {"shots": []}

        if "shots" in data and isinstance(data["shots"], list):
            shots = []
            for idx, shot in enumerate(data["shots"]):
                shot_dict: dict[str, Any] = (
                    dict(shot) if isinstance(shot, dict) else {"script_excerpt": str(shot), "shot_name": ""}
                )
                if "index" not in shot_dict:
                    shot_dict["index"] = idx + 1
                # 兼容：LLM 可能用 title/shot_title 代替 shot_name
                if "shot_name" not in shot_dict:
                    if "title" in shot_dict:
                        shot_dict["shot_name"] = str(shot_dict.pop("title"))
                    elif "shot_title" in shot_dict:
                        shot_dict["shot_name"] = str(shot_dict.pop("shot_title"))
                shot_dict.setdefault("shot_name", "")
                # 兼容旧字段：character_ids -> character_names_in_text（此阶段为弱信息）
                if "character_ids" in shot_dict and "character_names_in_text" not in shot_dict:
                    val = shot_dict.get("character_ids")
                    if isinstance(val, list):
                        shot_dict["character_names_in_text"] = [str(x) for x in val]
                    shot_dict.pop("character_ids", None)
                shots.append(shot_dict)
            data["shots"] = shots
        if "total_shots" not in data and "shots" in data:
            data["total_shots"] = len(data["shots"])
        return data


# ============================================================================
# 2. ShotElementExtractorAgent - 逐镜信息提取（兼容旧流程）
# ============================================================================

class ShotElementExtractorAgent(AgentBase[ShotElementExtractionResult]):
    """[兼容] 逐镜信息提取：输入单镜文本+上文摘要，输出该镜的结构化提取结果。"""

    @property
    def system_prompt(self) -> str:
        return _ELEMENT_EXTRACTOR_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return ELEMENT_EXTRACTOR_PROMPT

    @property
    def output_model(self) -> type[ShotElementExtractionResult]:
        return ShotElementExtractionResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """规范化元素提取结果（升级版结构）。"""
        data = dict(data)
        # 兼容：缺失 shot_division
        if "shot_division" not in data:
            data["shot_division"] = None
        if "elements" not in data or not isinstance(data["elements"], dict):
            data["elements"] = {}

        elements = data["elements"]

        # 兼容旧字段名：*_ids -> *_keys
        legacy_key_map = {
            "character_ids": "character_keys",
            "scene_ids": "scene_keys",
            "costume_ids": "costume_keys",
            "prop_ids": "prop_keys",
        }
        for old, new in legacy_key_map.items():
            if old in elements and new not in elements:
                val = elements.get(old)
                if isinstance(val, list):
                    elements[new] = [str(x) for x in val]
                elements.pop(old, None)

        # 兼容旧字段名：dialog_lines -> dialogue_lines
        if "dialog_lines" in elements and "dialogue_lines" not in elements:
            elements["dialogue_lines"] = elements.pop("dialog_lines")

        for key in (
            "character_keys",
            "scene_keys",
            "costume_keys",
            "prop_keys",
            "characters_detailed",
            "props_detailed",
            "dialogue_lines",
            "actions",
            "shot_type_hints",
        ):
            if key not in elements or not isinstance(elements[key], list):
                elements[key] = []

        if "scene_detailed" not in elements:
            elements["scene_detailed"] = None
        elif elements["scene_detailed"] is not None and not isinstance(elements["scene_detailed"], dict):
            elements["scene_detailed"] = None

        if "confidence_breakdown" not in elements or not isinstance(elements["confidence_breakdown"], dict):
            elements["confidence_breakdown"] = {}

        # 兼容旧结构：characters_detailed/props_detailed/scene_detailed 里字段名 *_id -> *_key
        for c in elements.get("characters_detailed", []) or []:
            if isinstance(c, dict) and "character_id" in c and "character_key" not in c:
                c["character_key"] = str(c.pop("character_id"))
            if isinstance(c, dict) and "evidence" not in c:
                c["evidence"] = []
        for p in elements.get("props_detailed", []) or []:
            if isinstance(p, dict) and "prop_id" in p and "prop_key" not in p:
                p["prop_key"] = str(p.pop("prop_id"))
            if isinstance(p, dict) and "evidence" not in p:
                p["evidence"] = []
        sd = elements.get("scene_detailed")
        if isinstance(sd, dict) and "scene_id" in sd and "scene_key" not in sd:
            sd["scene_key"] = str(sd.pop("scene_id"))
        if isinstance(sd, dict) and "evidence" not in sd:
            sd["evidence"] = []

        # 兼容旧对白行结构：补齐 schemas.DialogueLine 的可选字段
        dl = elements.get("dialogue_lines")
        if isinstance(dl, list):
            for line in dl:
                if not isinstance(line, dict):
                    continue
                if "index" not in line and "order" in line:
                    line["index"] = line.pop("order")
                if "evidence" not in line:
                    line["evidence"] = []
                # 确保 line_mode 合法字符串（由 schema Literal 校验）
                if "line_mode" not in line:
                    line["line_mode"] = "DIALOGUE"

        data["elements"] = elements

        if "confidence" not in data:
            data["confidence"] = None

        return data


# ============================================================================
# 2b. ElementExtractorAgent - 项目级信息提取（新流程最终输出）
# ============================================================================

class ElementExtractorAgent(AgentBase[StudioScriptExtractionDraft]):
    """项目级信息提取（最终输出）：输入剧本文本 + 分镜结果，产出全局实体表 + 逐镜关联。"""

    @property
    def system_prompt(self) -> str:
        return _SCRIPT_EXTRACTOR_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return SCRIPT_EXTRACTOR_PROMPT

    @property
    def output_model(self) -> type[StudioScriptExtractionDraft]:
        return StudioScriptExtractionDraft

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        data = dict(data)
        data.setdefault("project_id", "")
        data.setdefault("chapter_id", "")
        data.setdefault("script_text", "")
        for k in ("characters", "scenes", "props", "costumes", "shots"):
            if k not in data or not isinstance(data[k], list):
                data[k] = []
        return data


# ============================================================================
# 3. EntityMergerAgent - 跨镜静态合并 + 基础画像生成
# ============================================================================

class EntityMergerAgent(AgentBase[EntityMergeResult]):
    """跨镜合并 + 基础画像生成：输入全部分镜提取结果+历史实体库，输出合并后的库。"""

    @property
    def system_prompt(self) -> str:
        return _ENTITY_MERGER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return ENTITY_MERGER_PROMPT

    @property
    def output_model(self) -> type[EntityMergeResult]:
        return EntityMergeResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """规范化实体合并结果。"""
        data = dict(data)
        if "merged_library" not in data:
            data["merged_library"] = {
                "characters": [],
                "locations": [],
                "scenes": [],
                "props": [],
                "total_entries": 0,
            }
        lib = data["merged_library"]
        # 兼容旧字段：缺 locations 时补空；旧结构可能没有 scenes
        if "locations" not in lib:
            lib["locations"] = []
        if "scenes" not in lib:
            lib["scenes"] = []
        if "total_entries" not in lib:
            lib["total_entries"] = sum(
                len(lib.get(k, []) or [])
                for k in ("characters", "locations", "scenes", "props")
            )
        # 兼容旧 variants 结构：dict[] -> EntityVariant[]（最小补齐）
        for bucket_name in ("characters", "locations", "scenes", "props"):
            bucket = lib.get(bucket_name)
            if not isinstance(bucket, list):
                continue
            for ent in bucket:
                if not isinstance(ent, dict):
                    continue
                if "variants" in ent and isinstance(ent["variants"], list):
                    new_vars = []
                    for v in ent["variants"]:
                        if isinstance(v, dict):
                            if "variant_key" not in v:
                                v["variant_key"] = v.get("id") or v.get("key") or "variant"
                            if "affected_shots" not in v:
                                v["affected_shots"] = []
                            if "evidence" not in v:
                                v["evidence"] = []
                            new_vars.append(v)
                        else:
                            new_vars.append(
                                {
                                    "variant_key": "variant",
                                    "description": str(v),
                                    "affected_shots": [],
                                    "evidence": [],
                                }
                            )
                    ent["variants"] = new_vars
        if "merge_stats" not in data:
            data["merge_stats"] = {}
        if "conflicts" not in data or not isinstance(data["conflicts"], list):
            data["conflicts"] = []
        return data


# ============================================================================
# 4. VariantAnalyzerAgent - 服装/外形变体检测与建议
# ============================================================================

class VariantAnalyzerAgent(AgentBase[VariantAnalysisResult]):
    """服装/外形变体检测与建议：输入实体库+全镜提取，输出变体分析结果。"""

    @property
    def system_prompt(self) -> str:
        return _VARIANT_ANALYZER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return VARIANT_ANALYZER_PROMPT

    @property
    def output_model(self) -> type[VariantAnalysisResult]:
        return VariantAnalysisResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """规范化变体分析结果。"""
        data = dict(data)
        if "costume_timelines" not in data or not isinstance(data["costume_timelines"], list):
            data["costume_timelines"] = []
        if "variant_suggestions" not in data or not isinstance(data["variant_suggestions"], list):
            data["variant_suggestions"] = []
        if "chapter_variants" not in data or not isinstance(data["chapter_variants"], dict):
            data["chapter_variants"] = {}
        # 补齐可选 evidence 字段，避免 strict schema 校验失败
        for tl in data.get("costume_timelines", []) or []:
            if not isinstance(tl, dict):
                continue
            entries = tl.get("timeline_entries")
            if isinstance(entries, list):
                for e in entries:
                    if isinstance(e, dict) and "evidence" not in e:
                        e["evidence"] = []
        for s in data.get("variant_suggestions", []) or []:
            if isinstance(s, dict) and "evidence" not in s:
                s["evidence"] = []
        return data


# ============================================================================
# 5. ConsistencyCheckerAgent - 文本一致性检查
# ============================================================================

class ConsistencyCheckerAgent(AgentBase[ScriptConsistencyCheckResult]):
    """一致性检查（角色混淆）：输入原文，检测同一角色身份/行为混淆并给出修改建议。"""

    @property
    def system_prompt(self) -> str:
        return _CONSISTENCY_CHECKER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return CONSISTENCY_CHECKER_PROMPT

    @property
    def output_model(self) -> type[ScriptConsistencyCheckResult]:
        return ScriptConsistencyCheckResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """规范化一致性检查结果（角色混淆）。"""
        data = dict(data)
        if "issues" not in data or not isinstance(data["issues"], list):
            data["issues"] = []
        for it in data["issues"]:
            if isinstance(it, dict):
                it.setdefault("issue_type", "character_confusion")
                it.setdefault("character_candidates", [])
                it.setdefault("affected_lines", None)
                it.setdefault("evidence", [])
        if "has_issues" not in data:
            data["has_issues"] = len(data["issues"]) > 0
        if "summary" not in data:
            data["summary"] = None
        return data


class ScriptOptimizerAgent(AgentBase[ScriptOptimizationResult]):
    """剧本优化 Agent：输入一致性检查输出 + 原文，输出优化后的剧本。"""

    @property
    def system_prompt(self) -> str:
        return _SCRIPT_OPTIMIZER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return SCRIPT_OPTIMIZER_PROMPT

    @property
    def output_model(self) -> type[ScriptOptimizationResult]:
        return ScriptOptimizationResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        data = dict(data)
        if "optimized_script_text" not in data:
            data["optimized_script_text"] = ""
        if "change_summary" not in data:
            data["change_summary"] = ""
        return data


# ============================================================================
# 6. OutputCompilerAgent - 最终输出打包
# ============================================================================

class OutputCompilerAgent(AgentBase[OutputCompileResult]):
    """最终输出打包：输入所有Agent状态，输出完整项目JSON + 表格数据。"""

    @property
    def system_prompt(self) -> str:
        return _OUTPUT_COMPILER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return OUTPUT_COMPILER_PROMPT

    @property
    def output_model(self) -> type[OutputCompileResult]:
        return OutputCompileResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """规范化输出编译结果。"""
        data = dict(data)
        # 严格输出：project_json 必须能被 ProjectCinematicBreakdown 校验
        if "project_json" not in data or not isinstance(data["project_json"], dict):
            data["project_json"] = {}
        pj = data["project_json"]
        if isinstance(pj, dict):
            # 补齐 ProjectCinematicBreakdown 必填字段
            pj.setdefault("source_id", "unknown_source")
            pj.setdefault("chunks", [])
            pj.setdefault("characters", [])
            pj.setdefault("locations", [])
            pj.setdefault("props", [])
            pj.setdefault("scenes", [])
            pj.setdefault("shots", [])
            pj.setdefault("transitions", [])
            pj.setdefault("notes", [])
            pj.setdefault("uncertainties", [])
        if "tables" not in data or not isinstance(data["tables"], list):
            data["tables"] = []
        if "export_stats" not in data or not isinstance(data["export_stats"], dict):
            data["export_stats"] = {
                "total_tables": len(data["tables"]),
                "total_rows": sum(t.get("row_count", 0) for t in data["tables"]),
            }
        return data

