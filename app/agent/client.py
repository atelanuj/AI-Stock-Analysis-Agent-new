import json
from openai import OpenAI
from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT, TECHNICAL_DECISION_PROMPT, FINAL_STOCK_DECISION_PROMPT, INTRADAY_DECISION_PROMPT, IPO_ANALYSIS_PROMPT, CHAT_ASSISTANT_PROMPT

client = OpenAI(
    base_url=settings.nvidia_base_url,
    api_key=settings.nvidia_api_key,
)

def _parse_json_content(content: str) -> dict:
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].lstrip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {content[:500]}") from exc


def _completion_extra_body() -> dict:
    body = {
        "chat_template_kwargs": {"enable_thinking": settings.ai_enable_thinking},
    }
    # NVIDIA's hosted Nemotron 3 Ultra runner supports thinking through the
    # chat template flag, but rejects the separate reasoning_budget field.
    if settings.nvidia_model != "nvidia/nemotron-3-ultra-550b-a55b":
        body["reasoning_budget"] = settings.ai_reasoning_budget
    return body

def _complete(system_prompt: str, user_content: str) -> dict:
    completion = client.chat.completions.create(
        model=settings.nvidia_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=settings.ai_temperature,
        top_p=settings.ai_top_p,
        max_tokens=settings.ai_max_tokens,
        extra_body=_completion_extra_body(),
    )
    return _parse_json_content(completion.choices[0].message.content or "")

def synthesize(prompt_payload: dict) -> dict:
    return _complete(
        SYSTEM_PROMPT,
        "Create the final stock research synthesis from this JSON evidence. Return JSON only.\n\n" + json.dumps(prompt_payload, default=str),
    )

def synthesize_technical_decision(prompt_payload: dict) -> dict:
    return _complete(
        TECHNICAL_DECISION_PROMPT,
        "Evaluate the technical evidence for the selected horizon and select target/stop candidate IDs. Return JSON only.\n\n" + json.dumps(prompt_payload, default=str),
    )


def synthesize_final_stock_decision(prompt_payload: dict) -> dict:
    return _complete(
        FINAL_STOCK_DECISION_PROMPT,
        "Combine all supplied UI evidence into one final BUY, HOLD or SELL decision. Return JSON only.\n\n" + json.dumps(prompt_payload, default=str),
    )


def synthesize_intraday_decision(prompt_payload: dict) -> dict:
    return _complete(
        INTRADAY_DECISION_PROMPT,
        "Evaluate the current-session evidence and select target, stop and next-candle candidate IDs. Return JSON only.\n\n" + json.dumps(prompt_payload, default=str),
    )

def synthesize_ipo_analysis(prompt_payload: dict) -> dict:
    return _complete(
        IPO_ANALYSIS_PROMPT,
        "Evaluate this pre-listing IPO evidence conservatively. Return JSON only.\n\n" + json.dumps(prompt_payload, default=str),
    )

def synthesize_chat(prompt_payload: dict) -> dict:
    return _complete(
        CHAT_ASSISTANT_PROMPT,
        "Answer the user's question using only the supplied context when market facts are involved. Return JSON only.\n\n" + json.dumps(prompt_payload, default=str),
    )
