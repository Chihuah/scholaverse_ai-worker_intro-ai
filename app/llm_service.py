"""Ollama API 封裝 — LLM prompt 生成與模型卸載"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a professional text-to-image prompt engineer for fantasy RPG character card art.
Given a structured character description, write a vivid English image generation prompt.

Output ONLY the prompt text - no explanations, no line breaks.

Rules:
- The character is the central subject, shown from waist up or full body, in a vertical portrait card format
- For CONFIRMED ATTRIBUTES: describe them faithfully and in detail (race features, class appearance, clothing, weapon, pose, expression, background scene)
- For CREATIVE GUIDANCE sections: invent unique, vivid details that fit the hint. Make each generation feel different - vary the specific scene, items, pose, and expression every time, even if the input is identical
- The Card Display instructions (LV number, rarity label, nickname scroll) MUST appear verbatim in your output - copy them exactly as given, do not paraphrase
- Do NOT include LoRA triggers, style prefixes, or technical SD tags
- Output a single flowing paragraph"""


async def generate_prompt(structured_description: str) -> str:
    """呼叫 Ollama API 將結構化描述轉為英文文生圖 prompt。

    Args:
        structured_description: prompt_builder 產出的結構化角色描述。

    Returns:
        Ollama 產生的英文 prompt（已去除前後空白）。

    Raises:
        Exception: Ollama API 呼叫失敗時。
    """
    url = f"{settings.ollama_base_url}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": f"{SYSTEM_PROMPT}\n\n{structured_description}",
        "stream": False,
    }

    logger.info("Calling Ollama API for prompt generation (model=%s)", settings.ollama_model)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.TimeoutException:
        logger.error("Ollama API request timed out after 60s")
        raise Exception("LLM prompt generation timed out (60s)")
    except httpx.HTTPStatusError as e:
        logger.error("Ollama API returned HTTP %d: %s", e.response.status_code, e.response.text)
        raise Exception(f"Ollama API error: HTTP {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error("Ollama API request failed: %s", e)
        raise Exception(f"LLM service unavailable: {e}")

    data = response.json()
    prompt = data.get("response", "").strip()

    if not prompt:
        logger.error("Ollama returned empty prompt")
        raise Exception("Ollama returned empty prompt")

    logger.info("Prompt generated successfully (%d chars)", len(prompt))
    return prompt


async def unload_model() -> None:
    """卸載 Ollama 模型以釋放 GPU VRAM，確保 sd-cli 可獨佔 GPU。

    失敗時僅記錄 warning，不影響主流程。
    """
    url = f"{settings.ollama_base_url}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "keep_alive": 0,
    }

    logger.info("Unloading Ollama model '%s' to free GPU VRAM", settings.ollama_model)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        logger.info("Ollama model unloaded successfully")
    except Exception as e:
        logger.warning("Failed to unload Ollama model (non-critical): %s", e)
