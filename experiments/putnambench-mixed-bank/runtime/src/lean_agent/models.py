"""One request per step. Fixture responses never call a model; no automatic retries."""
from decimal import Decimal, InvalidOperation
import json
import os
import shlex
from urllib import error, request

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def load_key(path):
    """Read an explicitly supplied dotenv file literally; never run shell text."""
    values = []
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in {"OPENROUTER", "OPENROUTER_API_KEY"}:
            parts = shlex.split(value, comments=True)
            if len(parts) != 1 or not parts[0]:
                raise ValueError("Invalid OpenRouter dotenv entry")
            values.append(parts[0])
    if not values or len(set(values)) != 1:
        raise ValueError("Missing or conflicting OpenRouter dotenv entries")
    return values[0]


def payload(messages, model):
    result = {"model": model.get("id", "fixture-v1"), "messages": messages,
              "max_tokens": model.get("max_tokens", 1024),
              "stream": False, "response_format": {"type": "json_object"}}
    if "temperature" in model or model["backend"] == "fixture":
        result["temperature"] = model.get("temperature", 0)
    if model["backend"] == "openrouter":
        result["provider"] = {"only": [model["provider"]], "allow_fallbacks": False,
                              "require_parameters": True}
        result["plugins"] = []
        if "reasoning_effort" in model:
            result["reasoning"] = {"effort": model["reasoning_effort"]}
        if "max_price" in model:
            result["provider"]["max_price"] = model["max_price"]
        if "seed" in model:
            result["seed"] = model["seed"]
    return result


def query(body, model, step, fixtures=None):
    if model["backend"] == "fixture":
        return {"id": f"fixture-{step}", "model": "fixture-v1", "provider": "fixture",
                "choices": [{"message": {"role": "assistant", "content": fixtures[step - 1]}}],
                "usage": {"cost": 0, "prompt_tokens": 0, "completion_tokens": 0}}
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("Export OPENROUTER_API_KEY; .env files are not loaded automatically")
    call = request.Request(ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode(),
                           headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        # Disable redirects so the Authorization header cannot follow another origin.
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with request.build_opener(NoRedirect).open(call, timeout=model["timeout_seconds"]) as response:
            return json.loads(response.read())
    except (error.URLError, TimeoutError, OSError, ValueError) as exc:
        # No retry: a missing response may still represent a billed request.
        # Never serialize exception text or request headers containing credentials.
        return {"transport_error": type(exc).__name__, "http_status": getattr(exc, "code", None)}


def receipt(raw):
    """Unknown billing is explicit, never silently converted to zero."""
    raw = raw if isinstance(raw, dict) else {}
    usage = raw.get("usage", {})
    cost = usage.get("cost") if isinstance(usage, dict) else None
    try:
        if isinstance(cost, bool) or cost is None:
            raise ValueError()
        amount = Decimal(str(cost))
        if not amount.is_finite() or amount < 0:
            raise ValueError()
        billed = str(amount)
    except (InvalidOperation, ValueError):
        billed = None
    content = None
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass
    return {"content": content if isinstance(content, str) else None,
            "cost_usd": billed, "usage": usage,
            "id": raw.get("id"), "model": raw.get("model"), "provider": raw.get("provider")}
