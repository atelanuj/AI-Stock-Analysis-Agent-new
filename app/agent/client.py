import json
from openai import OpenAI
from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT, TECHNICAL_DECISION_PROMPT

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
        extra_body={
            "chat_template_kwargs": {"enable_thinking": settings.ai_enable_thinking},
            "reasoning_budget": settings.ai_reasoning_budget,
        },
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
        "Evaluate the technical evidence for the selected horizon. Return JSON only. Do not invent prices.\n\n" + json.dumps(prompt_payload, default=str),
    )
