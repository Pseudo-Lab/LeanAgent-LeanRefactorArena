"""Conservative output-only tail fitting; no discount to input reservations."""
from copy import deepcopy
from decimal import Decimal


def fit_output(body, remaining, request_cost, minimum_tokens=2048):
    remaining = Decimal(str(remaining))
    original = deepcopy(body)
    if Decimal(request_cost(original)["reserved_usd"]) <= remaining:
        return original
    low, high = minimum_tokens, original["max_completion_tokens"]
    if type(low) is not int or low < 1 or low > high:
        raise ValueError("Invalid minimum output budget")
    smallest = {**original, "max_completion_tokens": low}
    if Decimal(request_cost(smallest)["reserved_usd"]) > remaining:
        return original  # The ordinary budget guard will stop without dispatch.
    while low < high:
        middle = (low + high + 1) // 2
        candidate = {**original, "max_completion_tokens": middle}
        if Decimal(request_cost(candidate)["reserved_usd"]) <= remaining:
            low = middle
        else:
            high = middle - 1
    fitted = {**original, "max_completion_tokens": low}
    assert Decimal(request_cost(fitted)["reserved_usd"]) <= remaining
    return fitted
