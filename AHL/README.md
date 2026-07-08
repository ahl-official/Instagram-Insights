# AHL — American Hairline Instagram Insights

Consolidated customer and business message intelligence from the **American Hairline | Hair Systems** Instagram data export (Jan–Jul 2026).

## What’s in this folder

| File | Purpose |
|------|---------|
| `consolidated_messages.json` | Single structured dataset of all parsed messages (DMs + comments) |
| `consolidation_report.txt` | Human-readable stats, warnings, and recommendations |
| `consolidate_messages.py` | Script used to build the JSON (re-runnable on new exports) |
| `README.md` | This overview |

## Data source

Instagram “Download your information” export from account **@americanhairline** (business display name: *American Hairline | Hair Systems*), covering roughly **8 Jan 2026 – 8 Jul 2026**.

- **~1,725** DM thread JSON files + post comments processed
- **9,047** messages in the last 6 months (inbound + outbound)
- **8,705** unique messages after duplicate flagging (**342** duplicates flagged)

## Key insights

### Volume & direction

| Metric | Count |
|--------|------:|
| Total messages | 9,047 |
| Unique messages | 8,705 |
| Customer / inbound | 3,091 |
| Business outbound | 5,956 |
| Unreplied customer messages | 148 |
| Needs follow-up | 216 |

### Platform mix

| Platform | Messages |
|----------|---------:|
| Instagram DM | 8,383 |
| Instagram Comment | 662 |
| Instagram DM (Message Request) | 2 |

Most activity is **Instagram DMs**. Comments in this export are primarily **outbound brand replies** (e.g. “Hello Please Check Your DM!”), not incoming post comments from customers.

### Categories

| Category | Messages |
|----------|---------:|
| Inquiry | 7,090 |
| Question | 843 |
| Compliment | 840 |
| Feedback | 269 |
| Complaint | 5 |

### Top intents

1. Requesting consultation, callback, or contact  
2. General customer message requiring review  
3. Business response or outreach to customer  
4. Inquiring about clinic/branch location or availability  
5. Initial greeting or opening message  
6. Asking about pricing for hair systems or services  
7. Directing user to check direct messages  
8. Inquiring about hair system products or customization  

**Takeaway:** Consultation/callback requests, location questions, and pricing dominate real customer intent. These are the highest-value clusters for FAQ templates and faster DM replies.

### Sentiment (all messages)

| Sentiment | Count |
|-----------|------:|
| Neutral | 7,788 |
| Positive | 1,253 |
| Negative | 4 |
| Urgent | 2 |

Prioritize the **148 unreplied** and **216 needs_follow_up** messages, especially those tagged **negative** or **urgent**.

### Language mix

| Language | Count |
|----------|------:|
| English | 7,940 |
| Unknown (often media-only) | 1,102 |
| Hindi / Hinglish / other | small |

## JSON schema (per message)

Each record in `consolidated_messages.json` includes:

- `id`, `sender`, `date` (ISO 8601), `platform`, `content`
- `category` — Question, Inquiry, Complaint, Compliment, Feedback, etc.
- `intent` — short summary of what the customer needs
- `context_clues` — e.g. urgent, price-sensitive, first-time customer
- `response_status` — `not_replied` | `replied` | `partially_replied` | `needs_follow_up`
- `language`, `sentiment`, `direction` (`inbound` / `outbound`), `source_file`
- `is_duplicate` (+ `duplicate_of` when flagged)

See `metadata` in the JSON for full breakdowns (`category_breakdown`, `platform_breakdown`, `top_intents`, etc.).

## Recommended next steps

1. **Filter customer-only:** `direction == "inbound"`
2. **Triage unreplied:** `response_status == "not_replied"` or `"needs_follow_up"`
3. **Build canned replies** for consultation, location, and pricing clusters
4. **Review complaints** and urgent/negative messages manually
5. **Re-run** `consolidate_messages.py` when a new Instagram export is available
6. Request a fuller export if **incoming** post comments from customers are needed

## Re-running consolidation

Place a fresh Instagram export so that `your_instagram_activity/` sits next to the script (or update `BASE_DIR` / `ACTIVITY_DIR` in the script), then:

```bash
python consolidate_messages.py
```

## Data quality notes

- Category, intent, sentiment, and language use **rule-based heuristics** (not LLM) — good for triage, not perfect classification.
- Instagram text encoding issues (mojibake / emoji) were repaired where possible.
- Duplicate detection flags same sender + minute + content (**342** flagged).
- `comments/post_comments_1.json` reflects comments **made by the brand**, not inbound comments on posts.
- **852** media-only messages are stored with placeholders like `[Photo]`, `[Sticker]`, etc.

## Privacy

This dataset contains real customer names, handles, and message content. Restrict repo access to authorized AHL team members only.

---

*Consolidated on 2026-07-08 · American Hairline | Hair Systems*
