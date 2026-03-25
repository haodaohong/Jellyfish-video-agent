"""通用 Agent 基类：固化 PromptTemplate + 输出模型，调用 LLM 并解析输出。"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

STRUCTURED_OUTPUT_METHOD = "function_calling"

T = TypeVar("T", bound=BaseModel)


def _extract_json_from_text(raw: str) -> str:
    """从 LLM 原始输出中剥离 markdown 代码块并提取 JSON 字符串。"""
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _extract_first_json_object(text: str) -> str | None:
    """尽量从文本中提取第一个 JSON 对象/数组片段。"""

    s = text.strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        end = s.rfind(closer)
        if start != -1 and end != -1 and end > start:
            return s[start : end + 1].strip()
    return None


class AgentBase(ABC, Generic[T]):
    """通用 Agent 基类：子类固化 prompt_template 与 output_model。"""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        structured_output_method: str = STRUCTURED_OUTPUT_METHOD,
        agent_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._model = model
        self._structured_output_method = structured_output_method
        self._agent_kwargs = dict(agent_kwargs or {})
        self._structured_chain: Runnable | None = None

    @property
    @abstractmethod
    def prompt_template(self) -> PromptTemplate:
        ...

    @property
    @abstractmethod
    def output_model(self) -> type[T]:
        ...

    @property
    def system_prompt(self) -> str:
        """子类可覆盖：系统提示词（作为 system message / 高优先级指令）。"""
        return ""

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """子类可覆盖：将 LLM 返回的 dict 规范化为 output_model 所需结构。默认 identity。"""
        return data

    def render_prompt(self, **kwargs: Any) -> str:
        """渲染完整提示词（变量填充后的最终字符串）。"""

        prompt = self.prompt_template
        try:
            user_prompt = prompt.format(**kwargs)
        except KeyError as e:
            missing = str(e).strip("'")
            raise ValueError(
                f"render_prompt 缺少变量: {missing}. "
                f"需要: {list(prompt.input_variables)}"
            ) from e

        sys = (self.system_prompt or "").strip()
        if not sys:
            return user_prompt
        return f"{sys}\n\n{user_prompt}".strip()

    def _render_user_prompt(self, **kwargs: Any) -> str:
        """仅渲染用户提示词（不包含 system_prompt）。"""
        prompt = self.prompt_template
        try:
            return prompt.format(**kwargs)
        except KeyError as e:
            missing = str(e).strip("'")
            raise ValueError(
                f"render_prompt 缺少变量: {missing}. "
                f"需要: {list(prompt.input_variables)}"
            ) from e

    def create_agent(self, *, structured_output: type[BaseModel] | None = None) -> Runnable:
        """
        生成可执行 runnable：
        - 优先使用 `langchain.agents.create_agent`，把 `system_prompt` 作为系统提示词传入
        - structured_output 不为 None 时，通过 `response_format=ToolStrategy(structured_output)` 让模型输出结构化结果
        - 若当前环境未安装 langchain，则降级为：RunnableLambda(render_user_prompt) | model（structured 时用 with_structured_output）
        """

        def _render_input(inputs: dict[str, Any]) -> dict[str, Any]:
            return {"input": self._render_user_prompt(**inputs)}

        # --- preferred path: langchain create_agent + ToolStrategy ---
        try:
            from langchain.agents import create_agent as _lc_create_agent  # type: ignore

            kwargs = dict(self._agent_kwargs)
            if structured_output is not None:
                kwargs["response_format"] = structured_output
            agent = _lc_create_agent(
                model=self._model,
                system_prompt=(self.system_prompt or ""),
                **kwargs,
            )
            return RunnableLambda(_render_input) | cast(Runnable, agent)
        except Exception:
            # --- fallback path: no langchain available ---
            llm: Runnable = cast(Runnable, self._model)
            if structured_output is not None:
                with_structured = getattr(self._model, "with_structured_output", None)
                if callable(with_structured):
                    try:
                        llm = cast(
                            Runnable,
                            with_structured(
                                structured_output,
                                method=self._structured_output_method,
                            ),
                        )
                    except NotImplementedError:
                        # 某些 BaseChatModel 子类（如测试 mock）不实现 with_structured_output；退回原始输出解析。
                        pass
            return RunnableLambda(lambda inputs: self._render_user_prompt(**inputs)) | llm

    def _build_structured_chain(self) -> Runnable | None:
        """构建 structured output chain（优先 ToolStrategy；缺 langchain 时退回 with_structured_output）。"""
        return self.create_agent(structured_output=self.output_model)

    def _get_structured_chain(self) -> Runnable | None:
        if self._structured_chain is not None:
            return self._structured_chain
        self._structured_chain = self._build_structured_chain()
        return self._structured_chain

    def run(self, **kwargs: Any) -> str:
        """调用 agent，返回原始字符串（通常为 JSON）。"""
        chain: Runnable = self.create_agent()
        result = chain.invoke(kwargs)
        if hasattr(result, "content"):
            return getattr(result, "content", str(result))
        return str(result)

    async def arun(self, **kwargs: Any) -> str:
        """异步调用 agent。"""
        chain: Runnable = self.create_agent()
        result = await chain.ainvoke(kwargs)
        if hasattr(result, "content"):
            return getattr(result, "content", str(result))
        return str(result)

    def format_output(self, raw: str) -> T:
        """将 agent 原始输出解析为结构化结果（JSON → 规范化 → Pydantic）。"""
        output_model = self.output_model
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except Exception:
            candidate = _extract_first_json_object(json_str)
            if candidate is None:
                raise
            data = json.loads(candidate)
        if isinstance(data, dict):
            data = self._normalize(data)
        return output_model.model_validate(data)

    def extract(self, **kwargs: Any) -> T:
        """执行：优先 with_structured_output，否则 run + format_output。"""
        chain = self._get_structured_chain()
        if chain is not None:
            try:
                result = chain.invoke(kwargs)
                if isinstance(result, self.output_model):
                    return cast(T, result)
                if isinstance(result, dict):
                    data = self._normalize(result)
                    return self.output_model.model_validate(data)
            except Exception:
                pass
        return self.format_output(self.run(**kwargs))

    async def aextract(self, **kwargs: Any) -> T:
        """异步执行。"""
        chain = self._get_structured_chain()
        if chain is not None:
            try:
                result = await chain.ainvoke(kwargs)
                if isinstance(result, self.output_model):
                    return cast(T, result)
                if isinstance(result, dict):
                    data = self._normalize(result)
                    return self.output_model.model_validate(data)
            except Exception:
                pass
        return self.format_output(await self.arun(**kwargs))
