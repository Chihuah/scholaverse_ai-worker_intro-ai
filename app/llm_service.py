from __future__ import annotations

"""Ollama API wrapper for constrained prompt generation and model unload."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a prompt writer for a fantasy RPG character card image model.

Your task is to convert structured character facts and visual direction into one coherent English image prompt.

Rules:
- Do not change confirmed character facts.
- Do not change the object rule.
- Do not add extra characters, creatures, companions, mounts, props, weapons, or tools unless explicitly allowed.
- Do not show any visible blade, hilt, dagger, staff, or combat item when the object rule says the character is unarmed.
- Respect the visual direction exactly.
- Keep the image focused on one character only.
- Keep the face fully lit with clearly visible facial features.
- Keep a clear character outline with visible clothing details.
- Do not render the character as a silhouette or heavy backlit shadow.
- Keep the background secondary to the character.
- Preserve readable English card text as part of the image composition.
- Treat all three card text areas as required and important.
- The student nickname must appear in a compact parchment scroll nameplate at the bottom center.
- The level must appear as digits only inside a round badge at the top left.
- The rarity must appear as letters only at the top right.
- Do not add extra words such as "rarity" to the rarity mark.
- Keep the bottom nameplate compact and limited to a small lower band of the card.
- The bottom nameplate must contain only the nickname in one single line.
- Do not duplicate the nickname elsewhere or add extra large title text above the nameplate.
- Do not repeat the level number inside the bottom nameplate.
- If the unlock stage is no_class, do not describe the character as any class, profession, or combat role.
- If the character is empty-handed, explicitly describe the character as unarmed with both hands empty.
- If the character uses a starter object, keep it simple, basic, and low-tier.
- If pose or expression is explicitly provided, do not override it.
- Output one single coherent English image prompt only.
- Do not output explanations, lists, JSON, markdown, or quotation marks around the result.

Write the prompt in this order:
1. character identity
2. framing and camera
3. pose and expression
4. held object or unarmed state
5. clothing and appearance
6. background
7. card text placement and readability
8. mood and finish
"""


def build_ollama_prompt(structured_description: str) -> str:
    """Assemble the final prompt sent to Ollama.

    The worker still passes a rendered structured description string from
    prompt_builder. We keep that interface stable and only tighten the system
    instruction here.
    """
    return f"{SYSTEM_PROMPT}\n\n{structured_description}".strip()


async def generate_prompt(structured_description: str, model_name: str | None = None) -> str:
    """Call Ollama and convert structured direction into one English image prompt.

    Args:
        structured_description: Structured direction text rendered by prompt_builder.

    Returns:
        A single English image prompt string.

    Raises:
        Exception: If the Ollama request fails or returns empty output.
    """
    url = f"{settings.ollama_base_url}/api/generate"
    active_model = model_name or settings.ollama_model
    payload = {
        "model": active_model,
        "prompt": build_ollama_prompt(structured_description),
        "stream": False,
    }

    logger.info("Calling Ollama API for prompt generation (model=%s)", active_model)

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


async def unload_model(model_name: str | None = None) -> None:
    """Unload the Ollama model so sd-cli can reclaim GPU VRAM."""
    url = f"{settings.ollama_base_url}/api/generate"
    active_model = model_name or settings.ollama_model
    payload = {
        "model": active_model,
        "keep_alive": 0,
    }

    logger.info("Unloading Ollama model '%s' to free GPU VRAM", active_model)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        logger.info("Ollama model unloaded successfully")
    except Exception as e:
        logger.warning("Failed to unload Ollama model (non-critical): %s", e)
