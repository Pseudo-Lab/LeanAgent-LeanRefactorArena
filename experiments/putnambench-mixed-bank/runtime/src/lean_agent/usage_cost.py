"""Compatibility API and CLI; the only calculator is lean_agent.accounting."""
from .accounting import (
    MILLION,
    VERSION,
    NO_PRICES,
    canonical,
    digest,
    read_json,
    money,
    text_id,
    count,
    normalize_usage,
    response_record,
    response_summary,
    validate_prices,
    estimate,
    make_receipt,
    summarize,
    codex_turn_records,
    parse_codex_jsonl,
    harness_records,
    build_report,
    native_report,
    main
)

if __name__ == "__main__":
    raise SystemExit(main())
