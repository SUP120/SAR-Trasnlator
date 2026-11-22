import json
import re
from os import getenv
from urllib.error import URLError
from urllib.request import Request, urlopen

from .land import LandProfile, Narrative
from .land_guidance import GuidanceRequest, PURPOSE_LABELS, ROLE_LABELS

INSTRUCTIONS = (
    "Summarize only the supplied monthly land observations. Return one plain text paragraph, at most 65 words. "
    "Use qualitative descriptions. Leave out all digits so the report table remains the source of numbers. "
    "Use NDVI for greenness, NDMI for vegetation moisture, and label soil moisture regional. Avoid causal or "
    "future claims, confirmed flooding, ground motion, or crop damage. Treat null values as missing."
)


def ai_available() -> bool:
    return bool(getenv("GROQ_API_KEY", "").strip() or getenv("LAND_LLM_API_KEY", "").strip())


def generate_narrative(profile: LandProfile, guidance: GuidanceRequest | None = None) -> Narrative:
    groq_key = getenv("GROQ_API_KEY", "").strip()
    key = groq_key or getenv("LAND_LLM_API_KEY", "").strip()
    if not key:
        raise ValueError("No live AI report provider is configured. The measured template report is available.")
    facts = [row.model_dump(mode="json", exclude={"image", "image_offset", "scenes"}) for row in profile.observations]
    instructions = INSTRUCTIONS
    if guidance is not None:
        instructions += (
            f" The reader chose the role {ROLE_LABELS[guidance.role]} and the purpose {PURPOSE_LABELS[guidance.purpose]}."
            " Address that reader directly. Explain the most relevant observed pattern and suggest one specific check on the ground"
            " or in the next map view. Treat optical water as a mapped indication. Avoid prescribing irrigation levels,"
            " declaring land suitable for purchase or construction, or inferring legal ownership."
        )
    if groq_key:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"
        body = {"model": getenv("LAND_GROQ_MODEL", "openai/gpt-oss-20b"), "max_completion_tokens": 1024,
                "messages": [{"role": "system", "content": instructions},
                             {"role": "user", "content": json.dumps(facts)}]}
    else:
        endpoint = "https://api.openai.com/v1/responses"
        body = {"model": getenv("LAND_LLM_MODEL", "gpt-4.1-mini"), "instructions": instructions,
                "input": json.dumps(facts), "max_output_tokens": 250, "store": False}
    request = Request(endpoint, method="POST", data=json.dumps(body).encode(),
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
        if groq_key:
            text = (payload["choices"][0]["message"]["content"] or "").strip()
        else:
            text = " ".join(part["text"].strip() for item in payload["output"] if item["type"] == "message"
                            for part in item["content"] if part["type"] == "output_text").strip()
    except (URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        raise RuntimeError("The AI service could not compose a summary. Use the measured template report or try again.") from error
    if not text or len(text) > 750 or re.search(r"\d|<|>|https?://", text):
        raise RuntimeError("The AI summary did not pass the report check. The measured template report is still available.")
    return Narrative(source="ai", text=text)
