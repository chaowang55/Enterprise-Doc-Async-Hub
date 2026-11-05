import time

import httpx

from app.config import get_settings
from app.llm import TransientLLMError


class ModelProtocolError(ValueError):
    pass


class ModelClient:
    def __init__(self):
        self.settings = get_settings()
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.calls = 0
        self.models = set()
        self.started = time.monotonic()
        self.deadline = self.started + self.settings.agent_max_seconds

    def chat(self, messages, tools, *, force_finish=False):
        settings = self.settings
        key = settings.llm_api_key.get_secret_value()
        if not key:
            raise ValueError("LLM_API_KEY 未配置")
        url = httpx.URL(settings.llm_base_url)
        if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
            raise ValueError("模型地址必须为不带凭据和查询参数的 HTTPS URL")
        if settings.llm_provider == "deepseek" and url.host != "api.deepseek.com":
            raise ValueError("DeepSeek 模式只允许官方 API 域名")
        choice = ({"type": "function", "function": {"name": "finish_review"}}
                  if force_finish else "auto")
        body = {"model": settings.llm_model, "messages": messages, "tools": tools,
                "tool_choice": choice, "max_tokens": settings.llm_max_output_tokens,
                "temperature": 0}
        if settings.llm_provider == "deepseek":
            body["thinking"] = {"type": "disabled"}
        remaining_seconds = self.deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise TimeoutError("AGENT_TIME_BUDGET")
        with httpx.Client(timeout=min(settings.llm_timeout_seconds, remaining_seconds),
                          follow_redirects=False) as client:
            try:
                response = client.post(str(url).rstrip("/") + "/chat/completions",
                                       headers={"Authorization": f"Bearer {key}"}, json=body)
            except httpx.TransportError as exc:
                raise TransientLLMError("模型网络异常或超时") from exc
        self.calls += 1
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientLLMError(f"模型暂不可用 ({response.status_code})")
        if response.status_code != 200:
            raise ModelProtocolError(f"模型请求失败 ({response.status_code})")
        try:
            payload = response.json()
            for key in self.usage:
                self.usage[key] += int(payload.get("usage", {}).get(key, 0))
            self.models.add(payload.get("model", settings.llm_model))
            choice = payload["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ModelProtocolError("模型输出被截断")
            return choice["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProtocolError("模型响应协议异常") from exc
