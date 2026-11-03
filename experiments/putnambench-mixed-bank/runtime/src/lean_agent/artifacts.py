"""Shared JSON and byte-integrity helpers for runs and offline readers."""
import hashlib
import json


def sha(data):
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def canonical(value):
    # Preserve malformed Unicode receipts losslessly, so parsing can reject them
    # after the original response has been saved. Normal bytes are unchanged.
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON")))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical(value))


def inventory(root):
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p != root / "artifacts.json"}
