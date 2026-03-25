"""镜头分镜首帧/尾帧/关键帧提示词生成 Agent：根据镜头信息生成对应帧的画面提示词。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase, _extract_json_from_text
from app.schemas.skills.shot_frame_prompt import ShotFramePromptResult


def _prepare_shot_frame_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    """将 input_dict 转为 prompt 模板所需格式，mood_tags 转为字符串。"""
    out = dict(input_dict)
    if "mood_tags" in out and isinstance(out["mood_tags"], list):
        out["mood_tags"] = ", ".join(str(t) for t in out["mood_tags"])
    else:
        out.setdefault("mood_tags", "")
    for key in ("camera_shot", "angle", "movement", "atmosphere", "vfx_type", "vfx_note", "duration", "scene_id", "dialog_summary"):
        if key not in out or out[key] is None:
            out[key] = ""
    out.setdefault("title", "")
    return out


_SHOT_FRAME_INPUT_VARS = [
    "script_excerpt",
    "title",
    "camera_shot",
    "angle",
    "movement",
    "atmosphere",
    "mood_tags",
    "vfx_type",
    "vfx_note",
    "duration",
    "scene_id",
    "dialog_summary",
]

_FIRST_FRAME_TEMPLATE = """你是一名分镜师。根据下列镜头信息，生成该镜头的**首帧**画面描述提示词（用于图像生成模型）。
要求：一句或几句简洁、可视化的中文描述（不得使用英文），涵盖画面主体、景别、氛围、关键动作或状态。
专有名词一致性规则：
- 剧本摘录（script_excerpt）中出现的角色名/场景名/道具名等专有名词，必须在输出中**原样保留**，不得翻译、不得替换为同义词或其他说法。
- 除了需要补全画面描述以外，不要对专有名词进行改写。
只输出一个 JSON 对象：{{"prompt": "你的提示词内容"}}，不要其他文字。

## 镜头信息
剧本摘录：{script_excerpt}
镜头标题：{title}
景别：{camera_shot}
机位角度：{angle}
运镜：{movement}
氛围：{atmosphere}
情绪标签：{mood_tags}
视效：{vfx_type} - {vfx_note}
时长：{duration}秒
对白摘要：{dialog_summary}

## 输出（仅首帧提示词，JSON：{{"prompt": "..."}}）
"""

_LAST_FRAME_TEMPLATE = """你是一名分镜师。根据下列镜头信息，生成该镜头的**尾帧**画面描述提示词（用于图像生成模型）。
要求：一句或几句简洁、可视化的中文描述（不得使用英文），描述镜头结束时的画面状态。
专有名词一致性规则：
- 剧本摘录（script_excerpt）中出现的角色名/场景名/道具名等专有名词，必须在输出中**原样保留**，不得翻译、不得替换为同义词或其他说法。
- 除了需要补全画面描述以外，不要对专有名词进行改写。
只输出一个 JSON 对象：{{"prompt": "你的提示词内容"}}，不要其他文字。

## 镜头信息
剧本摘录：{script_excerpt}
镜头标题：{title}
景别：{camera_shot}
机位角度：{angle}
运镜：{movement}
氛围：{atmosphere}
情绪标签：{mood_tags}
视效：{vfx_type} - {vfx_note}
时长：{duration}秒
对白摘要：{dialog_summary}

## 输出（仅尾帧提示词，JSON：{{"prompt": "..."}}）
"""

_KEY_FRAME_TEMPLATE = """你是一名分镜师。根据下列镜头信息，生成该镜头的**关键帧**画面描述提示词（用于图像生成模型）。
要求：一句或几句简洁、可视化的中文描述（不得使用英文），捕捉该镜头中最具代表性的瞬间画面。
专有名词一致性规则：
- 剧本摘录（script_excerpt）中出现的角色名/场景名/道具名等专有名词，必须在输出中**原样保留**，不得翻译、不得替换为同义词或其他说法。
- 除了需要补全画面描述以外，不要对专有名词进行改写。
只输出一个 JSON 对象：{{"prompt": "你的提示词内容"}}，不要其他文字。

## 镜头信息
剧本摘录：{script_excerpt}
镜头标题：{title}
景别：{camera_shot}
机位角度：{angle}
运镜：{movement}
氛围：{atmosphere}
情绪标签：{mood_tags}
视效：{vfx_type} - {vfx_note}
时长：{duration}秒
对白摘要：{dialog_summary}

## 输出（仅关键帧提示词，JSON：{{"prompt": "..."}}）
"""

SHOT_FIRST_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_FIRST_FRAME_TEMPLATE)
SHOT_LAST_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_LAST_FRAME_TEMPLATE)
SHOT_KEY_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_KEY_FRAME_TEMPLATE)


class ShotFirstFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头首帧提示词生成 Agent，输出可写入 ShotDetail.first_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_FIRST_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)


class ShotLastFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头尾帧提示词生成 Agent，输出可写入 ShotDetail.last_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_LAST_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)


class ShotKeyFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头关键帧提示词生成 Agent，输出可写入 ShotDetail.key_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_KEY_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)
