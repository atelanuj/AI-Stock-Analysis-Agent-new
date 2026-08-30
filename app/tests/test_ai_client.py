from app.agent.client import _completion_extra_body
from app.config import settings


def test_ultra_model_omits_unsupported_reasoning_budget(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_model", "nvidia/nemotron-3-ultra-550b-a55b")
    body = _completion_extra_body()
    assert body["chat_template_kwargs"]["enable_thinking"] == settings.ai_enable_thinking
    assert "reasoning_budget" not in body


def test_other_models_keep_configured_reasoning_budget(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_model", "nvidia/nemotron-3-nano-30b-a3b")
    assert _completion_extra_body()["reasoning_budget"] == settings.ai_reasoning_budget
