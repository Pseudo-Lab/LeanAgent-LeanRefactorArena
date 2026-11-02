"""Conservative reservations for pinned OpenAI text requests, including reasoning.

The experiment adapter additionally verifies live endpoint/cache prices against
the transmitted price ceilings before every dispatch. No cache discount assumed.
"""
from decimal import Decimal
import json

from .artifacts import canonical, sha


def request_cost(body):
    """Maximum request cost, independent of a stopping policy."""
    if (body["model"] != "openai/gpt-6.1-sol" or body.get("plugins") != []
            or "tools" in body or len(body["messages"]) != 2
            or any(not isinstance(m.get("content"), str) for m in body["messages"])
            or body["provider"]["only"] != ["openai"] or body["provider"]["allow_fallbacks"]):
        raise ValueError("Cost cap requires pinned GPT-6.1 Sol/OpenAI plain-text requests")
    # Bound content tokens by UTF-8 wire bytes, plus ample chat framing.
    count = len(json.dumps(body, ensure_ascii=False).encode("utf-8")) + 4096
    if count >= 240000:
        raise ValueError("Cost-cap request must remain below the 272K pricing tier")
    prices = body["provider"]["max_price"]
    prompt, completion = Decimal(str(prices["prompt"])), Decimal(str(prices["completion"]))
    bound = (count * prompt + body["max_tokens"] * completion) / 1_000_000
    return {"request_sha256": sha(canonical(body)), "input_token_bound": count,
            "output_token_bound": body["max_tokens"], "reserved_usd": str(bound)}


def reservation(body, state, config):
    cap = config["limits"].get("cost_cap_usd")
    if cap is None:
        return None
    request = request_cost(body)
    spent, cap = Decimal(state["cost_usd"]), Decimal(str(cap))
    return {**request, "spent_usd": str(spent), "cap_usd": str(cap),
            "allowed": spent + Decimal(request["reserved_usd"]) <= cap}
