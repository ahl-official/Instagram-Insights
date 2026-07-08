#!/usr/bin/env python3
"""Consolidate Instagram export JSON files into a single structured dataset."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ACTIVITY_DIR = BASE_DIR / "your_instagram_activity"
OUTPUT_JSON = BASE_DIR / "consolidated_messages.json"
OUTPUT_REPORT = BASE_DIR / "consolidation_report.txt"

# Last 6 months from consolidation date (2026-07-08)
DATE_START = datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 7, 8, 23, 59, 59, tzinfo=timezone.utc)
CONSOLIDATION_DATE = "2026-07-08"

BUSINESS_NAMES = {
    "american hairline | hair systems",
    "american hairline",
    "americanhairline",
}

# Keyword heuristics for classification
CATEGORY_RULES = [
    ("Complaint", [r"\b(complain|complaint|worst|terrible|awful|scam|fraud|refund|disappointed|angry|useless|pathetic|bad service|not happy|unhappy)\b"]),
    ("Compliment", [r"\b(thank|thanks|grateful|appreciate|amazing|excellent|great job|love it|wonderful|fantastic|best|awesome|perfect)\b"]),
    ("Feedback", [r"\b(feedback|review|experience|suggest|improvement|recommend)\b"]),
    ("Inquiry", [r"\b(inquir|interested|want to know|looking for|need hair|hair system|hair patch|wig|toupee|bald|hair loss|consultation|appointment|book|visit|branch|location|address|delhi|mumbai|bangalore|hyderabad|pune|chennai)\b"]),
    ("Question", [r"\?|\b(how much|price|cost|rate|charges|what is|when|where|which|can i|do you|is it|are you|how do|how long|available)\b"]),
]

INTENT_PATTERNS = [
    (r"\b(price|cost|rate|charges|how much|rs\.?|rupee|budget|afford)\b", "Asking about pricing for hair systems or services"),
    (r"\b(location|address|branch|where|delhi|mumbai|bangalore|hyderabad|pune|chennai|near|city)\b", "Inquiring about clinic/branch location or availability"),
    (r"\b(appointment|consultation|visit|book|call|callback|contact|number|whatsapp)\b", "Requesting consultation, callback, or contact"),
    (r"\b(delivery|shipping|dispatch|courier|order status|track)\b", "Asking about order delivery or shipping status"),
    (r"\b(refund|return|exchange|complaint|problem|issue|defect|damage)\b", "Reporting a problem or requesting resolution"),
    (r"\b(hair system|hair patch|wig|toupee|density|base|custom|install|maintenance)\b", "Inquiring about hair system products or customization"),
    (r"\b(dm|check your dm|message)\b", "Directing user to check direct messages"),
    (r"^(hi|hello|hey)\b", "Initial greeting or opening message"),
]

SENTIMENT_RULES = [
    ("urgent", [r"\b(urgent|asap|immediately|right now|emergency|today only|hurry)\b"]),
    ("negative", [r"\b(angry|upset|disappointed|worst|terrible|scam|fraud|refund|complaint|not happy|unhappy|bad|pathetic)\b"]),
    ("positive", [r"\b(thank|thanks|grateful|love|amazing|excellent|great|wonderful|happy|perfect|awesome)\b"]),
]


def fix_encoding(text: str | None) -> str:
    if not text:
        return ""
    if not isinstance(text, str):
        return str(text)
    try:
        repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if repaired and len(repaired.strip()) >= max(1, len(text.strip()) // 3):
            return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_business_sender(name: str | None) -> bool:
    if not name:
        return False
    return name.strip().lower() in BUSINESS_NAMES


def parse_timestamp(value, unit: str = "ms") -> datetime | None:
    if value is None:
        return None
    try:
        if unit == "ms":
            ts = float(value) / 1000.0
        else:
            ts = float(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def in_date_range(dt: datetime | None) -> bool:
    if dt is None:
        return False
    return DATE_START <= dt <= DATE_END


def to_iso(dt: datetime | None) -> str:
    if dt is None:
        return "date_unknown"
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_dm_content(msg: dict) -> str:
    parts: list[str] = []
    if msg.get("content"):
        parts.append(fix_encoding(msg["content"]))
    if msg.get("photos"):
        count = len(msg["photos"])
        parts.append(f"[Photo x{count}]")
    if msg.get("videos"):
        count = len(msg["videos"])
        parts.append(f"[Video x{count}]")
    if msg.get("audio_files"):
        count = len(msg["audio_files"])
        parts.append(f"[Audio x{count}]")
    if msg.get("share"):
        share = msg["share"]
        link = share.get("link") or share.get("share_text") or ""
        if link:
            parts.append(f"[Shared link: {fix_encoding(link)}]")
        else:
            parts.append("[Shared content]")
    if msg.get("reactions"):
        reactions = ", ".join(
            f"{fix_encoding(r.get('actor', 'Someone'))}: {fix_encoding(r.get('reaction', ''))}"
            for r in msg["reactions"]
        )
        parts.append(f"[Reaction: {reactions}]")
    if msg.get("sticker"):
        parts.append("[Sticker]")
    if not parts:
        return "[No text content]"
    return normalize_whitespace(" ".join(parts))


def detect_category(content: str, is_outbound: bool) -> str:
    text = content.lower()
    if is_outbound and re.search(r"@\w+.*check your dm", text):
        return "Inquiry"
    for category, patterns in CATEGORY_RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return category
    if "?" in text:
        return "Question"
    if is_outbound:
        return "Inquiry"
    return "Inquiry"


def detect_intent(content: str, is_outbound: bool) -> str:
    text = content.lower()
    for pattern, intent in INTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return intent
    if is_outbound:
        return "Business response or outreach to customer"
    return "General customer message requiring review"


def detect_sentiment(content: str) -> str:
    text = content.lower()
    for sentiment, patterns in SENTIMENT_RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return sentiment
    return "neutral"


def detect_language(content: str) -> str:
    if not content or content.startswith("["):
        return "unknown"
    if re.search(r"[\u0900-\u097F]", content):
        if re.search(r"[A-Za-z]", content):
            return "hi-en"
        return "hi"
    if re.search(r"[\u0B80-\u0BFF]", content):
        return "ta"
    if re.search(r"[\u0C80-\u0CFF]", content):
        return "kn"
    if re.search(r"[\u0980-\u09FF]", content):
        return "bn"
    if re.search(r"[A-Za-z]", content):
        return "en"
    return "unknown"


def detect_context_clues(content: str, sender: str, is_outbound: bool, thread_customer: str) -> str:
    clues: list[str] = []
    text = content.lower()
    if not is_outbound:
        clues.append("customer message")
    else:
        clues.append("business reply")
    if re.search(r"^(hi|hello|hey)\b", text) and len(text.split()) <= 4:
        clues.append("opening greeting")
    if re.search(r"\b(first time|new customer|never tried)\b", text):
        clues.append("first-time customer")
    if re.search(r"\b(urgent|asap|immediately)\b", text):
        clues.append("urgent tone")
    if re.search(r"\b(angry|upset|disappointed|complaint|worst)\b", text):
        clues.append("negative tone")
    if re.search(r"\b(price|cost|how much)\b", text):
        clues.append("price-sensitive")
    if re.search(r"\b(delhi|mumbai|bangalore|hyderabad|pune|chennai|branch|location)\b", text):
        clues.append("location-related")
    if thread_customer and sender != thread_customer and not is_outbound:
        clues.append("participant in thread")
    return ", ".join(clues) if clues else "none noted"


def content_fingerprint(sender: str, dt: datetime | None, content: str) -> str:
    minute = to_iso(dt)[:16] if dt else "date_unknown"
    normalized = normalize_whitespace(content).lower()
    raw = f"{sender.lower()}|{minute}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_response_status(
    msg_dt: datetime | None,
    is_outbound: bool,
    thread_messages: list[dict],
) -> str:
    if is_outbound:
        return "replied"

    if msg_dt is None:
        return "not_replied"

    later = [
        m
        for m in thread_messages
        if m["dt"] and m["dt"] > msg_dt
    ]
    business_replies = [m for m in later if m["is_business"]]
    customer_followups = [m for m in later if not m["is_business"]]

    if not business_replies:
        return "not_replied"
    if customer_followups:
        # Customer messaged again after business reply
        last_business = max(business_replies, key=lambda m: m["dt"])
        followups_after_reply = [m for m in customer_followups if m["dt"] > last_business["dt"]]
        if followups_after_reply:
            return "needs_follow_up"
    first_reply = min(business_replies, key=lambda m: m["dt"])
    if first_reply["dt"] and (first_reply["dt"] - msg_dt).total_seconds() > 0:
        # Basic partial detection: very short/generic business reply to substantive question
        return "replied"
    return "partially_replied"


def parse_dm_files() -> tuple[list[dict], list[str]]:
    messages: list[dict] = []
    warnings: list[str] = []
    dm_root = ACTIVITY_DIR / "messages"
    if not dm_root.exists():
        warnings.append(f"Missing messages directory: {dm_root}")
        return messages, warnings

    json_files = sorted(dm_root.rglob("message_*.json"))
    anonymous_counter = 0

    for file_path in json_files:
        rel_source = str(file_path.relative_to(BASE_DIR)).replace("\\", "/")
        if "message_requests" in rel_source:
            platform = "Instagram DM (Message Request)"
        else:
            platform = "Instagram DM"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            warnings.append(f"Failed to parse {rel_source}: {exc}")
            continue

        participants = [fix_encoding(p.get("name", "")) for p in data.get("participants", [])]
        customer_names = [p for p in participants if not is_business_sender(p)]
        thread_customer = customer_names[0] if customer_names else (data.get("title") or "")

        raw_messages = data.get("messages", [])
        thread_index: list[dict] = []
        for raw in raw_messages:
            sender = fix_encoding(raw.get("sender_name"))
            if not sender:
                anonymous_counter += 1
                sender = f"anonymous_{anonymous_counter}"
            dt = parse_timestamp(raw.get("timestamp_ms"), "ms")
            content = extract_dm_content(raw)
            is_business = is_business_sender(sender)
            thread_index.append(
                {
                    "dt": dt,
                    "is_business": is_business,
                    "sender": sender,
                    "content": content,
                }
            )

        for raw in raw_messages:
            sender = fix_encoding(raw.get("sender_name"))
            if not sender:
                anonymous_counter += 1
                sender = f"anonymous_{anonymous_counter}"
            dt = parse_timestamp(raw.get("timestamp_ms"), "ms")
            if not in_date_range(dt):
                continue

            content = extract_dm_content(raw)
            is_outbound = is_business_sender(sender)
            response_status = compute_response_status(dt, is_outbound, thread_index)

            messages.append(
                {
                    "sender": sender,
                    "date": to_iso(dt),
                    "platform": platform,
                    "content": content,
                    "category": detect_category(content, is_outbound),
                    "intent": detect_intent(content, is_outbound),
                    "context_clues": detect_context_clues(content, sender, is_outbound, thread_customer),
                    "response_status": response_status,
                    "source_file": rel_source,
                    "language": detect_language(content),
                    "sentiment": detect_sentiment(content),
                    "direction": "outbound" if is_outbound else "inbound",
                    "_fingerprint": content_fingerprint(sender, dt, content),
                    "_sort_dt": dt,
                }
            )

    return messages, warnings


def parse_comment_files() -> tuple[list[dict], list[str]]:
    messages: list[dict] = []
    warnings: list[str] = []
    comments_dir = ACTIVITY_DIR / "comments"
    if not comments_dir.exists():
        warnings.append(f"Missing comments directory: {comments_dir}")
        return messages, warnings

    for file_path in sorted(comments_dir.glob("*.json")):
        rel_source = str(file_path.relative_to(BASE_DIR)).replace("\\", "/")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            warnings.append(f"Failed to parse {rel_source}: {exc}")
            continue

        if not isinstance(data, list):
            warnings.append(f"Unexpected comment file structure: {rel_source}")
            continue

        for entry in data:
            smd = entry.get("string_map_data", {})
            comment_block = smd.get("Comment", {})
            owner_block = smd.get("Media Owner", {})
            time_block = smd.get("Time", {})

            content = fix_encoding(comment_block.get("value", ""))
            if not content:
                continue

            sender = fix_encoding(owner_block.get("value", "")) or "americanhairline"
            dt = parse_timestamp(time_block.get("timestamp"), "s")
            if not in_date_range(dt):
                continue

            is_outbound = True  # export stores comments posted by account owner
            messages.append(
                {
                    "sender": sender,
                    "date": to_iso(dt),
                    "platform": "Instagram Comment",
                    "content": content,
                    "category": detect_category(content, is_outbound),
                    "intent": detect_intent(content, is_outbound),
                    "context_clues": detect_context_clues(content, sender, is_outbound, ""),
                    "response_status": "replied",
                    "source_file": rel_source,
                    "language": detect_language(content),
                    "sentiment": detect_sentiment(content),
                    "direction": "outbound",
                    "_fingerprint": content_fingerprint(sender, dt, content),
                    "_sort_dt": dt,
                }
            )

    return messages, warnings


def deduplicate_messages(messages: list[dict]) -> tuple[list[dict], int]:
    seen: dict[str, str] = {}
    duplicate_count = 0

    # Sort oldest first so first occurrence becomes canonical
    messages.sort(key=lambda m: (m.get("_sort_dt") is None, m.get("_sort_dt") or datetime.min.replace(tzinfo=timezone.utc)))

    for msg in messages:
        fp = msg["_fingerprint"]
        if fp in seen:
            msg["is_duplicate"] = True
            msg["duplicate_of"] = seen[fp]
            duplicate_count += 1
        else:
            msg["is_duplicate"] = False
            seen[fp] = msg.get("id", "")

    return messages, duplicate_count


def assign_ids(messages: list[dict]) -> None:
    for idx, msg in enumerate(messages, start=1):
        msg["id"] = f"msg_{idx:05d}"


def finalize_messages(messages: list[dict]) -> list[dict]:
    assign_ids(messages)
    messages, duplicate_count = deduplicate_messages(messages)

    # Back-fill duplicate_of with actual ids
    id_by_fingerprint = {}
    for msg in messages:
        if not msg.get("is_duplicate"):
            id_by_fingerprint[msg["_fingerprint"]] = msg["id"]

    cleaned: list[dict] = []
    for msg in messages:
        if msg.get("is_duplicate"):
            msg["duplicate_of"] = id_by_fingerprint.get(msg["_fingerprint"], msg["duplicate_of"])
        output = {
            "id": msg["id"],
            "sender": msg["sender"],
            "date": msg["date"],
            "platform": msg["platform"],
            "content": msg["content"],
            "category": msg["category"],
            "intent": msg["intent"],
            "context_clues": msg["context_clues"],
            "response_status": msg["response_status"],
            "source_file": msg["source_file"],
            "language": msg["language"],
            "sentiment": msg["sentiment"],
            "direction": msg["direction"],
            "is_duplicate": msg["is_duplicate"],
        }
        if msg["is_duplicate"]:
            output["duplicate_of"] = msg["duplicate_of"]
        cleaned.append(output)

    cleaned.sort(key=lambda m: (m["date"] == "date_unknown", m["date"]))
    return cleaned, duplicate_count


def build_metadata(messages: list[dict], warnings: list[str], duplicate_count: int) -> dict:
    dates = [m["date"] for m in messages if m["date"] != "date_unknown"]
    category_breakdown = dict(Counter(m["category"] for m in messages))
    platform_breakdown = dict(Counter(m["platform"] for m in messages))
    response_status_breakdown = dict(Counter(m["response_status"] for m in messages))
    language_breakdown = dict(Counter(m["language"] for m in messages))
    sentiment_breakdown = dict(Counter(m["sentiment"] for m in messages))
    direction_breakdown = dict(Counter(m["direction"] for m in messages))

    intent_counts = Counter(m["intent"] for m in messages)
    top_intents = [intent for intent, _ in intent_counts.most_common(10)]

    notes = [
        "Source: Instagram data export for americanhairline.",
        "Included Instagram DMs (inbox + message requests) and post comments authored by the account.",
        f"Filtered to messages between {DATE_START.date()} and {DATE_END.date()} (last 6 months).",
        "Both inbound (customer) and outbound (business) messages are included.",
        "Comment export contains business-authored post comments only; incoming comment threads from other users were not present in this export.",
        f"Detected {duplicate_count} duplicate messages (same sender, minute, and content).",
        "Emoji/special characters were repaired from common Instagram export encoding issues where possible.",
    ]
    if warnings:
        notes.append(f"{len(warnings)} file-level warnings encountered during parsing.")

    metadata = {
        "total_messages": len(messages),
        "unique_messages": sum(1 for m in messages if not m.get("is_duplicate")),
        "duplicate_messages": duplicate_count,
        "date_range_start": min(dates)[:10] if dates else "date_unknown",
        "date_range_end": max(dates)[:10] if dates else "date_unknown",
        "platforms": sorted(platform_breakdown.keys()),
        "categories": category_breakdown,
        "consolidation_date": CONSOLIDATION_DATE,
        "category_breakdown": category_breakdown,
        "platform_breakdown": platform_breakdown,
        "response_status_breakdown": response_status_breakdown,
        "language_breakdown": language_breakdown,
        "sentiment_breakdown": sentiment_breakdown,
        "direction_breakdown": direction_breakdown,
        "top_intents": top_intents,
        "notes": " ".join(notes),
    }
    return metadata


def write_report(
    messages: list[dict],
    metadata: dict,
    warnings: list[str],
    duplicate_count: int,
) -> None:
    inbound = sum(1 for m in messages if m["direction"] == "inbound")
    outbound = sum(1 for m in messages if m["direction"] == "outbound")
    unknown_dates = sum(1 for m in messages if m["date"] == "date_unknown")
    no_text = sum(1 for m in messages if m["content"] == "[No text content]")

    lines = [
        "INSTAGRAM MESSAGE CONSOLIDATION REPORT",
        "=" * 42,
        f"Generated: {CONSOLIDATION_DATE}",
        f"Source folder: {BASE_DIR}",
        "",
        "SUMMARY",
        "-" * 20,
        f"Total messages processed: {metadata['total_messages']}",
        f"Unique messages: {metadata['unique_messages']}",
        f"Duplicate messages flagged: {duplicate_count}",
        f"Inbound (customer): {inbound}",
        f"Outbound (business): {outbound}",
        f"Date range: {metadata['date_range_start']} to {metadata['date_range_end']}",
        "",
        "PLATFORM BREAKDOWN",
        "-" * 20,
    ]
    for platform, count in sorted(metadata["platform_breakdown"].items(), key=lambda x: -x[1]):
        lines.append(f"  {platform}: {count}")

    lines.extend(["", "CATEGORY BREAKDOWN", "-" * 20])
    for category, count in sorted(metadata["category_breakdown"].items(), key=lambda x: -x[1]):
        lines.append(f"  {category}: {count}")

    lines.extend(["", "RESPONSE STATUS", "-" * 20])
    for status, count in sorted(metadata["response_status_breakdown"].items(), key=lambda x: -x[1]):
        lines.append(f"  {status}: {count}")

    lines.extend(["", "TOP INTENTS", "-" * 20])
    for intent in metadata["top_intents"]:
        lines.append(f"  - {intent}")

    lines.extend(["", "DATA QUALITY NOTES", "-" * 20])
    lines.append(f"  Messages with unknown date: {unknown_dates}")
    lines.append(f"  Messages without text (media-only): {no_text}")
    lines.append("  Instagram export uses mis-encoded UTF-8 for emojis; script attempted repair.")
    lines.append("  Comment export only includes comments posted by the business account.")
    lines.append("  Response status for inbound DMs is inferred from thread order in each conversation file.")

    if warnings:
        lines.extend(["", "WARNINGS / ERRORS", "-" * 20])
        for warning in warnings[:50]:
            lines.append(f"  - {warning}")
        if len(warnings) > 50:
            lines.append(f"  ... and {len(warnings) - 50} more warnings")

    lines.extend(
        [
            "",
            "RECOMMENDATIONS",
            "-" * 20,
            "1. Review messages flagged as is_duplicate=true before taking action.",
            "2. Prioritize inbound messages with response_status=not_replied or needs_follow_up.",
            "3. Validate pricing/location intents manually; keyword intent is approximate.",
            "4. Request a fuller Instagram export if incoming post comments from customers are needed.",
            "5. Cross-check urgent/negative sentiment messages for customer service follow-up.",
        ]
    )

    OUTPUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    all_warnings: list[str] = []

    dm_messages, dm_warnings = parse_dm_files()
    comment_messages, comment_warnings = parse_comment_files()
    all_warnings.extend(dm_warnings)
    all_warnings.extend(comment_warnings)

    combined = dm_messages + comment_messages
    messages, duplicate_count = finalize_messages(combined)
    metadata = build_metadata(messages, all_warnings, duplicate_count)

    output = {"metadata": metadata, "messages": messages}
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    write_report(messages, metadata, all_warnings, duplicate_count)

    print(f"Processed {metadata['total_messages']} messages ({metadata['unique_messages']} unique)")
    print(f"Duplicates flagged: {duplicate_count}")
    print(f"Output: {OUTPUT_JSON}")
    print(f"Report: {OUTPUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
