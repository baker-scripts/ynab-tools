"""Memo building, truncation, and AI summarization for YNAB transaction memos."""

from __future__ import annotations

import re

from loguru import logger

from ynab_tools.config.settings import get_settings

YNAB_MEMO_LIMIT = 500


def extract_order_url(memo: str) -> str | None:
    """Extract the Amazon order URL from a memo (markdown or plain format)."""
    normalized = _normalize_memo(memo)

    # Markdown link format: [Order #XXX](https://...)
    md_match = re.search(
        r"\[Order\s*#[\w-]+\]\((https://www\.amazon\.com/gp/your-account/order-details\?orderID=[\w-]+)\)",
        normalized,
    )
    if md_match:
        return md_match.group(1)

    # Plain URL format
    plain_match = re.search(
        r"https://www\.amazon\.com/gp/your-account/order-details\?orderID=[\w-]+",
        normalized,
    )
    if plain_match:
        return plain_match.group(0)

    return None


def truncate_memo(memo: str) -> str:
    """Truncate a memo to fit within YNAB's character limit.

    Preserves the URL and partial-order warning while truncating item lines.
    """
    if len(memo) <= YNAB_MEMO_LIMIT:
        return memo

    url_line = extract_order_url(memo)

    # Strip markdown formatting for space calculation
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", memo)
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)

    lines = [line.strip() for line in clean.replace("\r\n", "\n").split("\n") if line.strip()]

    multi_order = next((ln for ln in lines if ln.startswith("-This transaction")), None)
    items_header = next((ln for ln in lines if ln == "Items"), None)
    item_lines = [ln for ln in lines if ln and ln[0].isdigit() and ". " in ln]

    # Calculate space for items
    required = [x for x in [multi_order, items_header, url_line] if x]
    required_space = sum(len(x) + 1 for x in required)
    available = YNAB_MEMO_LIMIT - required_space

    # Truncate items to fit
    truncated: list[str] = []
    current_len = 0
    for item in item_lines:
        item_len = len(item) + 1
        if current_len + item_len <= available:
            truncated.append(item)
            current_len += item_len
        else:
            if available - current_len >= 4:
                truncated.append("...")
            break

    # Build final memo
    final: list[str] = []
    if multi_order:
        final.append(multi_order)
    if items_header and truncated:
        final.append(items_header)
    final.extend(truncated)
    if url_line:
        final.append(url_line)

    return "\n".join(final)


def generate_ai_summary(
    items: list[str],
    order_url: str,
    *,
    order_total: str | None = None,
    transaction_amount: str | None = None,
    max_length: int = YNAB_MEMO_LIMIT,
) -> str | None:
    """Use OpenAI to generate a concise memo summary.

    Returns None on API errors (caller should fall back to truncation).
    Raises ConfigError if OpenAI API key is missing.
    """
    s = get_settings()
    if not s.openai_api_key or not s.openai_api_key.get_secret_value():
        from ynab_tools.exceptions import ConfigError

        raise ConfigError("OpenAI API key required for AI summarization")

    from openai import APIError, AuthenticationError, OpenAI, RateLimitError

    from ynab_tools.amazon.prompts import MARKDOWN_PROMPT, PLAIN_PROMPT, SYSTEM_PROMPT

    client = OpenAI(
        api_key=s.openai_api_key.get_secret_value(),
        default_headers={"User-Agent": "ynab-tools"},
    )

    items_text = "\n".join(f"- {item}" for item in items)
    user_prompt = MARKDOWN_PROMPT if s.ynab_use_markdown else PLAIN_PROMPT
    full_prompt = f"{user_prompt}\n\nOrder Details:\n{items_text}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ],
        )
    except AuthenticationError as e:
        from ynab_tools.exceptions import ConfigError

        raise ConfigError("Invalid OpenAI API key") from e
    except (RateLimitError, APIError, ConnectionError, TimeoutError) as e:
        logger.error(f"OpenAI API error: {type(e).__name__}")
        return None

    if not response.choices or not response.choices[0].message.content:
        logger.error("OpenAI returned an empty response")
        return None

    content = response.choices[0].message.content

    if len(content) > max_length:
        content = content[:max_length]

    # Add partial order note if applicable
    if order_total and transaction_amount and order_total != transaction_amount:
        content = f"{content} -This transaction doesn't represent the entire order. The order total is ${order_total}-"

    return content


def _summarize_with_ai(memo: str, order_url: str) -> str:
    """Summarize a memo using AI, falling back to truncation on failure."""
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", memo)
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)

    items: list[str] = []
    order_total: str | None = None
    transaction_amount: str | None = None

    for line in clean.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:])
        elif stripped and stripped[0].isdigit() and ". " in stripped:
            items.append(stripped)
        elif "order total is $" in stripped:
            order_total = stripped.split("$")[-1].strip("-")
        elif "transaction doesn't represent" in stripped:
            transaction_amount = stripped.split("$")[-1].strip("-")

    if not items:
        return memo

    summary = generate_ai_summary(
        items=items,
        order_url=order_url,
        order_total=order_total,
        transaction_amount=transaction_amount,
    )

    if summary is None or len(summary) > YNAB_MEMO_LIMIT:
        return truncate_memo(memo)

    return summary


def process_memo(memo: str) -> str:
    """Process a memo: AI summarization if enabled, otherwise truncation if needed."""
    s = get_settings()
    order_url = extract_order_url(memo)

    if not order_url:
        logger.warning("No Amazon order URL found in memo")
        return memo

    if s.use_ai_summarization:
        logger.info("Using AI summarization")
        result = _summarize_with_ai(memo, order_url)
        logger.info(f"Processed memo from {len(memo)} to {len(result)} chars")
        return result

    if len(memo) > YNAB_MEMO_LIMIT:
        result = truncate_memo(memo)
        logger.info(f"Truncated memo from {len(memo)} to {len(result)} chars")
        return result

    return memo


def _normalize_memo(memo: str) -> str:
    """Normalize a memo by joining split lines that contain a URL."""
    lines = memo.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result: list[str] = []
    current = ""
    in_url = False

    for line in lines:
        stripped = line.strip()
        if "amazon.com" in line:
            current += stripped
            in_url = True
        elif in_url and (stripped.endswith("-") or stripped.endswith(")")):
            current += stripped
            if stripped.endswith(")"):
                in_url = False
                result.append(current)
                current = ""
        elif in_url:
            current += stripped
        else:
            if current:
                result.append(current)
                current = ""
            result.append(line)

    if current:
        result.append(current)

    return "\n".join(result)
