#!/usr/bin/env python3
"""Consolidate Instagram DM + comment export into structured JSON."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\LENOVO\Downloads\instagram-alchemanehairextensions-2026-07-08-k1WIg31R")
ACTIVITY = ROOT / "your_instagram_activity"
OUT_JSON = ROOT / "consolidated_messages.json"
OUT_REPORT = ROOT / "consolidation_report.txt"

BUSINESS_NAMES = {
    "Alchemane Hair Extensions | Luxury Hair",
    "vinittdessai(ALCHEMANE SALON Account)",
    "alchemanehairextensions",
}
BUSINESS_NAME_NORM = {n.lower() for n in BUSINESS_NAMES}

# Dating window note (export estimated ~ last 6 months relative to 2026-07-08)
CONSOLIDATION_DATE = "2026-07-08"

warnings: list[str] = []
errors: list[str] = []
notes: list[str] = []


def fix_encoding(text: str | None) -> str:
    """Fix Instagram double-encoded UTF-8 (mojibake)."""
    if not text:
        return ""
    s = text
    # Try latin-1 round-trip (common in IG exports)
    for _ in range(2):
        try:
            fixed = s.encode("latin-1").decode("utf-8")
            if fixed != s:
                s = fixed
            else:
                break
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    # Normalize whitespace
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def ts_to_iso(ts) -> str:
    if ts is None:
        return "date_unknown"
    try:
        ts = float(ts)
        if ts > 1e12:  # ms
            dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        warnings.append(f"Bad timestamp {ts!r}: {e}")
        return "date_unknown"


def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    has_devanagari = bool(re.search(r"[\u0900-\u097F]", text))
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    # Common Hinglish romanized tokens
    hinglish_tokens = {
        "hai", "nahi", "kya", "please", "price", "kitna", "haan", "mujhe",
        "aap", "krna", "karna", "bhejo", "number", "call", "whatsapp",
    }
    words = set(re.findall(r"[a-zA-Z']+", text.lower()))
    hinglish_hits = len(words & hinglish_tokens)
    if has_devanagari and has_latin:
        return "hi-en-mixed"
    if has_devanagari:
        return "hi"
    if has_arabic and has_latin:
        return "ar-en-mixed"
    if has_arabic:
        return "ar"
    if hinglish_hits >= 2 and has_latin:
        return "hinglish"
    if has_latin:
        return "en"
    return "other"


def categorize(text: str) -> str:
    t = text.lower()
    if not t or t in {"hi", "hello", "hey", "hii", "hiii", "hola", "namaste"}:
        return "Greeting"
    complaint = [
        "complaint", "refund", "dirty", "poor", "worst", "scam", "fake",
        "angry", "disappointed", "not happy", "unhappy", "issue", "problem",
        "wrong", "delay", "still waiting", "no response", "didn't work",
        "doesnt work", "doesn't work", "cheated", "wasted",
    ]
    compliment = [
        "love", "amazing", "beautiful", "gorgeous", "thanks", "thank you",
        "awesome", "perfect", "best", "wonderful", "fantastic", "looks great",
        "so happy", "recommend",
    ]
    pricing = [
        "price", "pricing", "cost", "rate", "how much", "kitna", "charges",
        "budget", "quote", "fee", "rs", "₹", "inr",
    ]
    booking = [
        "appointment", "book", "slot", "available", "visit", "come", "timing",
        "schedule", "when can", "free on",
    ]
    inquiry = [
        "do you", "can you", "have you", "is it", "are you", "location",
        "address", "branch", "delivery", "shipping", "product", "extension",
        "clip in", "tape", "keratin", "volume", "length", "colour", "color",
        "texture", "virgin", "human hair",
    ]
    feedback = ["feedback", "suggestion", "review", "experience was"]
    question_marks = "?" in text

    if any(k in t for k in complaint):
        return "Complaint"
    if any(k in t for k in pricing):
        return "Pricing"
    if any(k in t for k in booking):
        return "Booking"
    if any(k in t for k in compliment) and not question_marks:
        return "Compliment"
    if any(k in t for k in feedback):
        return "Feedback"
    if any(k in t for k in inquiry) or question_marks:
        return "Inquiry" if any(k in t for k in inquiry) else "Question"
    if question_marks:
        return "Question"
    if len(t) < 40 and any(g in t for g in ("hi", "hello", "hey", "good morning", "good evening")):
        return "Greeting"
    return "Other"


def extract_intent(text: str, category: str) -> str:
    t = text.strip()
    if not t:
        return "No textual content (media/sticker/system message)"
    clipped = re.sub(r"\s+", " ", t)[:180]
    templates = {
        "Pricing": f"Asking about pricing/cost: {clipped}",
        "Booking": f"Wants to book/schedule: {clipped}",
        "Complaint": f"Reporting a problem/complaint: {clipped}",
        "Compliment": f"Sharing positive feedback: {clipped}",
        "Feedback": f"Providing feedback: {clipped}",
        "Inquiry": f"Product/service inquiry: {clipped}",
        "Question": f"Asking a question: {clipped}",
        "Greeting": "Opening greeting / starting conversation",
        "Other": f"General message: {clipped}",
    }
    intent = templates.get(category, f"Customer message: {clipped}")
    return intent[:220]


def context_clues(text: str, sender: str, is_business: bool) -> str:
    clues = []
    t = text.lower()
    if is_business:
        clues.append("business_outbound")
    if sender.lower().startswith("anonymous") or sender == "Instagram user":
        clues.append("anonymous_or_hidden_user")
    if any(k in t for k in ("urgent", "asap", "immediately", "today", "right now")):
        clues.append("urgent")
    if any(k in t for k in ("first time", "never tried", "new to", "first-time")):
        clues.append("first-time customer")
    if any(k in t for k in ("angry", "frustrated", "worst", "scam", "refund")):
        clues.append("angry tone")
    if any(k in t for k in ("please call", "whatsapp", "number", "phone")):
        clues.append("wants_callback_or_whatsapp")
    if any(k in t for k in ("wedding", "bridal", "event", "function")):
        clues.append("event_or_bridal_context")
    if re.search(r"\b\d{10}\b", text) or "9967123333" in text:
        clues.append("contains_phone_number")
    if len(text) > 300:
        clues.append("long_message")
    if len(text) < 5 and text:
        clues.append("very_short")
    return ", ".join(clues) if clues else "none"


def sentiment(text: str, category: str) -> str:
    t = text.lower()
    if any(k in t for k in ("urgent", "asap", "immediately", "today only", "emergency")):
        return "urgent"
    if category == "Complaint" or any(
        k in t for k in ("refund", "worst", "scam", "angry", "disappointed", "hate", "terrible")
    ):
        return "negative"
    if category == "Compliment" or any(
        k in t for k in ("love", "amazing", "thanks", "thank you", "beautiful", "perfect", "great")
    ):
        return "positive"
    return "neutral"


def content_from_message(m: dict) -> str:
    parts = []
    if m.get("content"):
        parts.append(fix_encoding(m["content"]))
    if m.get("share"):
        share = m["share"]
        link = share.get("link") or share.get("share_text") or ""
        parts.append(f"[shared] {fix_encoding(str(link))}")
    if m.get("photos"):
        parts.append(f"[photo x{len(m['photos'])}]")
    if m.get("videos"):
        parts.append(f"[video x{len(m['videos'])}]")
    if m.get("audio_files"):
        parts.append(f"[audio x{len(m['audio_files'])}]")
    if m.get("sticker"):
        parts.append("[sticker]")
    if m.get("gifs"):
        parts.append(f"[gif x{len(m['gifs'])}]")
    if m.get("reactions"):
        try:
            reacts = ", ".join(
                f"{fix_encoding(r.get('reaction',''))} by {fix_encoding(r.get('actor',''))}"
                for r in m["reactions"]
            )
            parts.append(f"[reactions: {reacts}]")
        except Exception:
            parts.append("[reactions]")
    # System-ish texts already in content
    return "\n".join(p for p in parts if p).strip()


def is_business_sender(name: str) -> bool:
    return (name or "").strip().lower() in BUSINESS_NAME_NORM


def dup_key(sender: str, date: str, content: str) -> str:
    raw = f"{sender}|{date}|{content}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:16]


def classify_response_status(thread_msgs: list[dict], idx: int, is_business: bool) -> str:
    """Infer reply status for a customer message within its thread (chrono ascending)."""
    if is_business:
        return "replied"  # outbound from brand
    # Look ahead for a business reply after this customer msg
    after = thread_msgs[idx + 1 :]
    before_biz = any(m["_is_business"] for m in thread_msgs[:idx])
    biz_after = [m for m in after if m["_is_business"]]
    cust_after = [m for m in after if not m["_is_business"]]
    if biz_after:
        # If customer sent more after last business reply overall, may need follow-up —
        # but THIS message was replied to if any business message follows it.
        # Refine: if last message in thread is customer, flag earlier unreplied chain end.
        last = thread_msgs[-1]
        if not last["_is_business"] and idx == len(thread_msgs) - 1:
            return "needs_follow_up"
        return "replied"
    # No business reply after this message
    if idx == len(thread_msgs) - 1:
        return "not_replied" if before_biz or idx == 0 else "not_replied"
    # Later customer messages exist but no business reply after this one
    if cust_after and not biz_after:
        return "not_replied"
    return "partially_replied"


def main() -> int:
    messages_out: list[dict] = []
    seen_hashes: dict[str, str] = {}
    duplicate_flags = 0
    anonymous_counter = 0
    files_processed = 0
    files_failed = 0
    skipped_empty = 0
    platform_counts: Counter = Counter()
    category_counts: Counter = Counter()
    status_counts: Counter = Counter()
    sentiment_counts: Counter = Counter()
    language_counts: Counter = Counter()
    intent_counter: Counter = Counter()
    customer_only = 0
    business_only = 0

    # ---- DMs ----
    msg_files = sorted(ACTIVITY.glob("messages/**/message_*.json"))
    notes.append(f"Found {len(msg_files)} Instagram message JSON files under messages/")

    for path in msg_files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        try:
            with open(path, "rb") as f:
                data = json.load(f)
        except Exception as e:
            files_failed += 1
            errors.append(f"Failed to parse {rel}: {e}")
            continue
        files_processed += 1
        platform = "Instagram DM"
        if "message_requests" in path.parts:
            platform = "Instagram Message Request"

        thread_raw = data.get("messages") or []
        # IG exports newest-first; sort oldest-first for reply status
        enriched = []
        for m in thread_raw:
            sender_raw = fix_encoding(m.get("sender_name") or "")
            if not sender_raw or sender_raw.lower() in {"", "instagram user"}:
                anonymous_counter += 1
                sender = f"anonymous_{anonymous_counter}"
            else:
                sender = sender_raw
            content = content_from_message(m)
            date = ts_to_iso(m.get("timestamp_ms"))
            biz = is_business_sender(sender_raw)
            enriched.append(
                {
                    "_sender": sender,
                    "_sender_raw": sender_raw,
                    "_content": content,
                    "_date": date,
                    "_is_business": biz,
                    "_ts": m.get("timestamp_ms") or 0,
                    "_raw": m,
                }
            )
        enriched.sort(key=lambda x: x["_ts"])

        for idx, em in enumerate(enriched):
            content = em["_content"]
            if not content:
                skipped_empty += 1
                continue
            sender = em["_sender"]
            date = em["_date"]
            biz = em["_is_business"]
            category = categorize(content) if not biz else "Business_Reply"
            intent = extract_intent(content, category if not biz else "Other")
            if biz:
                intent = f"Business outbound: {re.sub(r'\s+', ' ', content)[:160]}"
            lang = detect_language(content)
            sent = sentiment(content, category)
            clues = context_clues(content, sender, biz)
            status = classify_response_status(enriched, idx, biz)

            h = dup_key(sender, date, content)
            is_dup = h in seen_hashes
            if is_dup:
                duplicate_flags += 1
            else:
                seen_hashes[h] = rel

            msgid = f"msg_{len(messages_out)+1:05d}"
            record = {
                "id": msgid,
                "sender": sender,
                "date": date,
                "platform": platform,
                "content": content,
                "category": category,
                "intent": intent,
                "context_clues": clues,
                "response_status": status,
                "source_file": rel,
                "language": lang,
                "sentiment": sent,
                "is_duplicate": is_dup,
                "duplicate_of_source": seen_hashes.get(h) if is_dup else None,
                "is_business_outbound": biz,
                "thread_title": fix_encoding(data.get("title") or ""),
            }
            messages_out.append(record)
            platform_counts[platform] += 1
            category_counts[category] += 1
            status_counts[status] += 1
            sentiment_counts[sent] += 1
            language_counts[lang] += 1
            if not biz:
                customer_only += 1
                # Normalize intent for top intents (first clause)
                short_intent = intent.split(":")[0].strip()
                intent_counter[short_intent] += 1
            else:
                business_only += 1

    # ---- Comments ----
    comment_files = sorted(ACTIVITY.glob("comments/**/*.json"))
    notes.append(f"Found {len(comment_files)} comment JSON file(s) under comments/")
    notes.append(
        "Instagram 'post_comments' export typically contains comments MADE BY this account "
        "(often 'Check your DMs!'), not incoming comments from customers."
    )

    for path in comment_files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        try:
            with open(path, "rb") as f:
                data = json.load(f)
        except Exception as e:
            files_failed += 1
            errors.append(f"Failed to parse {rel}: {e}")
            continue
        files_processed += 1
        if not isinstance(data, list):
            warnings.append(f"Unexpected comments structure in {rel}")
            continue
        for entry in data:
            sm = entry.get("string_map_data") or {}
            comment_val = fix_encoding((sm.get("Comment") or {}).get("href") or "")
            # Prefer value field
            comment_val = fix_encoding((sm.get("Comment") or {}).get("value") or comment_val)
            media_owner = fix_encoding((sm.get("Media Owner") or {}).get("value") or "")
            ts = (sm.get("Time") or {}).get("timestamp")
            date = ts_to_iso(ts)
            if not comment_val:
                skipped_empty += 1
                continue

            # Instagram "post_comments" = comments authored BY this account.
            # Media Owner = whose post received the comment (often own posts or collabs).
            sender = "Alchemane Hair Extensions | Luxury Hair"
            biz = True
            category = "Business_Reply"
            on_own_post = media_owner.lower() in BUSINESS_NAME_NORM or media_owner == ""

            intent = (
                f"Outbound comment on {'own' if on_own_post else '@' + (media_owner or 'unknown')} post: "
                f"{comment_val[:140]}"
            )
            lang = detect_language(comment_val)
            sent = sentiment(comment_val, category)
            clues = context_clues(comment_val, sender, biz)
            if media_owner:
                target = "own_post" if on_own_post else f"external_post_owner={media_owner}"
                clues = f"{clues}, {target}" if clues != "none" else target
            status = "replied"

            h = dup_key(sender, date, comment_val)
            is_dup = h in seen_hashes
            if is_dup:
                duplicate_flags += 1
            else:
                seen_hashes[h] = rel

            msgid = f"msg_{len(messages_out)+1:05d}"
            record = {
                "id": msgid,
                "sender": sender,
                "date": date,
                "platform": "Instagram Comment",
                "content": comment_val,
                "category": category,
                "intent": intent,
                "context_clues": clues if clues != "none" else clues,
                "response_status": status,
                "source_file": rel,
                "language": lang,
                "sentiment": sent,
                "is_duplicate": is_dup,
                "duplicate_of_source": seen_hashes.get(h) if is_dup else None,
                "is_business_outbound": biz,
                "thread_title": media_owner or "",
            }
            messages_out.append(record)
            platform_counts["Instagram Comment"] += 1
            category_counts[category] += 1
            status_counts[status] += 1
            sentiment_counts[sent] += 1
            language_counts[lang] += 1
            if not biz:
                customer_only += 1
                intent_counter[intent.split(":")[0].strip()] += 1
            else:
                business_only += 1

    # Sort by date where possible
    def sort_key(m):
        d = m["date"]
        return d if d != "date_unknown" else "9999"

    messages_out.sort(key=sort_key)

    # Re-number ids after sort
    for i, m in enumerate(messages_out, 1):
        m["id"] = f"msg_{i:05d}"

    dates = [m["date"] for m in messages_out if m["date"] != "date_unknown"]
    date_start = min(dates)[:10] if dates else "unknown"
    date_end = max(dates)[:10] if dates else "unknown"

    top_intents = [k for k, _ in intent_counter.most_common(15)]

    metadata = {
        "total_messages": len(messages_out),
        "customer_messages": customer_only,
        "business_outbound_messages": business_only,
        "date_range_start": date_start,
        "date_range_end": date_end,
        "platforms": sorted(platform_counts.keys()),
        "categories": dict(category_counts),
        "category_breakdown": dict(category_counts.most_common()),
        "platform_breakdown": dict(platform_counts.most_common()),
        "response_status_breakdown": dict(status_counts.most_common()),
        "sentiment_breakdown": dict(sentiment_counts.most_common()),
        "language_breakdown": dict(language_counts.most_common()),
        "top_intents": top_intents,
        "duplicates_flagged": duplicate_flags,
        "anonymous_senders_assigned": anonymous_counter,
        "files_processed": files_processed,
        "files_failed": files_failed,
        "empty_skipped": skipped_empty,
        "consolidation_date": CONSOLIDATION_DATE,
        "notes": " | ".join(notes + [
            f"Duplicates flagged (kept, marked is_duplicate=true): {duplicate_flags}",
            f"Encoding repaired via latin-1→utf-8 for Instagram mojibake",
            f"Category/intent/sentiment use rule-based heuristics (not LLM)",
        ]),
    }

    payload = {"metadata": metadata, "messages": messages_out}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Report
    report_lines = [
        "INSTAGRAM MESSAGE CONSOLIDATION REPORT",
        "=" * 50,
        f"Consolidation date: {CONSOLIDATION_DATE}",
        f"Source root: {ACTIVITY}",
        f"Output JSON: {OUT_JSON}",
        "",
        "TOTALS",
        "-" * 30,
        f"Total messages written: {len(messages_out)}",
        f"  Customer / inbound-ish: {customer_only}",
        f"  Business outbound:      {business_only}",
        f"Files processed: {files_processed}",
        f"Files failed: {files_failed}",
        f"Empty/media-only skipped: {skipped_empty}",
        f"Duplicates flagged: {duplicate_flags}",
        f"Anonymous senders assigned: {anonymous_counter}",
        f"Date range: {date_start} → {date_end}",
        "",
        "PLATFORM BREAKDOWN",
        "-" * 30,
    ]
    for k, v in platform_counts.most_common():
        report_lines.append(f"  {k}: {v}")
    report_lines += ["", "CATEGORY BREAKDOWN", "-" * 30]
    for k, v in category_counts.most_common():
        report_lines.append(f"  {k}: {v}")
    report_lines += ["", "RESPONSE STATUS", "-" * 30]
    for k, v in status_counts.most_common():
        report_lines.append(f"  {k}: {v}")
    report_lines += ["", "SENTIMENT", "-" * 30]
    for k, v in sentiment_counts.most_common():
        report_lines.append(f"  {k}: {v}")
    report_lines += ["", "LANGUAGE", "-" * 30]
    for k, v in language_counts.most_common():
        report_lines.append(f"  {k}: {v}")
    report_lines += ["", "TOP INTENTS (customer)", "-" * 30]
    for k, v in intent_counter.most_common(15):
        report_lines.append(f"  {v:5d}  {k}")

    report_lines += [
        "",
        "ERRORS",
        "-" * 30,
    ]
    if errors:
        report_lines.extend(f"  - {e}" for e in errors[:50])
        if len(errors) > 50:
            report_lines.append(f"  ... and {len(errors)-50} more")
    else:
        report_lines.append("  None")

    report_lines += ["", "WARNINGS", "-" * 30]
    if warnings:
        # Deduplicate warnings somewhat
        wc = Counter(warnings)
        for w, c in wc.most_common(40):
            report_lines.append(f"  [{c}x] {w}")
    else:
        report_lines.append("  None")

    report_lines += [
        "",
        "DATA QUALITY NOTES",
        "-" * 30,
        "1. Source is an Instagram data download (JSON). Platforms beyond Instagram are not present.",
        "2. Many DM threads start with business private-reply / templates after comment CTAs.",
        "3. post_comments_1.json mostly contains comments authored by the brand account",
        "   (e.g. 'Hello Please Check Your DM!'), not third-party comments on your posts.",
        "4. Sender names and text often had mojibake (e.g. â instead of ’); repaired where possible.",
        "5. Category, intent, language, and sentiment are heuristic — review Complaints/Pricing for CRM use.",
        "6. response_status for DMs is inferred from whether a business message appears after a customer message",
        "   in the same thread; media-only business replies still count.",
        "7. Duplicate detection is exact match on sender+timestamp+content; near-duplicates are not merged.",
        "8. Messages with no extractable text (empty content and no media markers) were skipped.",
        "",
        "RECOMMENDATIONS",
        "-" * 30,
        "1. Filter is_business_outbound=false when building a customer FAQ / reply playbook.",
        "2. Prioritize response_status in ('not_replied','needs_follow_up') + sentiment urgent/negative.",
        "3. Treat category=Business_Reply / Instagram Comment brand CTAs as outbound marketing logs, not inquiries.",
        "4. Manually review top Pricing + Inquiry clusters to build canned WhatsApp/DM replies.",
        "5. If you also have WhatsApp/Email exports, drop them in a folder and re-run with an extended parser.",
        "6. For true incoming post comments, export 'comments on your posts' (if available) separately —",
        "   this dump's comments folder appears to be your outbound comments.",
        "",
        "DONE",
    ]

    OUT_REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote {OUT_JSON} ({len(messages_out)} messages)")
    print(f"Wrote {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
