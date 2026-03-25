from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ShotFramePromptInput(BaseModel):
    """镜头帧提示词生成输入，与 Shot + ShotDetail 字段对齐。"""

    model_config = ConfigDict(extra="forbid")

    script_excerpt: str = Field(..., description="剧本摘录，对应 Shot.script_excerpt")
    title: str = Field("", description="镜头标题，对应 Shot.title")
    camera_shot: Optional[str] = Field(None, description="景别，如 ECU/CU/MS")
    angle: Optional[str] = Field(None, description="机位角度")
    movement: Optional[str] = Field(None, description="运镜方式")
    atmosphere: Optional[str] = Field(None, description="氛围描述")
    mood_tags: Optional[List[str]] = Field(None, description="情绪标签")
    vfx_type: Optional[str] = Field(None, description="视效类型")
    vfx_note: Optional[str] = Field(None, description="视效说明")
    duration: Optional[int] = Field(None, description="时长（秒）")
    scene_id: Optional[str] = Field(None, description="关联场景 ID")
    dialog_summary: Optional[str] = Field(None, description="对白摘要")


class ShotFramePromptResult(BaseModel):
    """镜头帧提示词生成结果：单个 prompt 字符串。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., description="画面描述提示词，可写入 ShotDetail 对应字段")


__all__ = ["ShotFramePromptInput", "ShotFramePromptResult"]

