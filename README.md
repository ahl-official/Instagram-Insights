# Instagram Insights

Consolidated customer and business message intelligence from Instagram data exports across AHL brands. This repo is organized with separate brand folders.

## Repository structure

```
instagram-insights/
├── README.md                 # This overview
├── alchemane/                # Alchemane Hair Extensions Instagram data
│   ├── consolidated_messages.json
│   ├── consolidation_report.txt
│   └── consolidate_messages.py
└── AHL/                      # American Hairline | Hair Systems Instagram data
    ├── README.md
    ├── consolidated_messages.json
    ├── consolidation_report.txt
    └── consolidate_messages.py
```

## What’s in `AHL/`

American Hairline Instagram insights (**9,047** messages, Jan–Jul 2026). See [`AHL/README.md`](AHL/README.md) for full stats, schema, and triage guidance.

| File | Purpose |
|------|---------|
| `consolidated_messages.json` | Structured DM + comment dataset |
| `consolidation_report.txt` | Stats, warnings, recommendations |
| `consolidate_messages.py` | Re-runnable consolidation script |
| `README.md` | Brand-specific overview and insights |

**Quick stats:** 3,091 inbound · 5,956 outbound · 148 unreplied · 216 needs follow-up. Top customer intents: consultation/callback, location, pricing.

## What’s in `alchemane/`

| File | Purpose |
|------|---------|
| `consolidated_messages.json` | Single structured dataset of all parsed messages |
| `consolidation_report.txt` | Human-readable stats, warnings, and recommendations |
| `consolidate_messages.py` | Script used to build the JSON (re-runnable on new exports) |

### Data source

Instagram “Download your information” export from account **@alchemanehairextensions**, covering roughly **8 Jan 2026 – 8 Jul 2026**.

- **3,421** JSON files processed (DM threads + comments)
- **16,513** messages with extractable text
- **2,883** media-only / empty messages skipped

## Key insights (Alchemane)

### Volume & direction

| Metric | Count |
|--------|------:|
| Total messages | 16,513 |
| Customer / inbound | 4,238 |
| Business outbound | 12,275 |
| Unreplied customer messages | 380 |

Most activity is **Instagram DMs** (14,253). Comments in this export are primarily **outbound brand replies** (e.g. “Check your DMs!”), not incoming post comments from customers.

### What customers ask about most

| Intent | Messages |
|--------|---------:|
| General / uncategorized | 1,874 |
| Greetings / conversation openers | 649 |
| **Pricing / cost** | **542** |
| **Product / service inquiry** | **535** |
| Questions | 248 |
| Positive feedback | 203 |
| Booking / scheduling | 166 |
| Complaints | 19 |

**Takeaway:** Pricing and product inquiries dominate real customer intent. These are the highest-value clusters for FAQ templates and faster DM replies.

### Sentiment (all messages)

| Sentiment | Count |
|-----------|------:|
| Neutral | 14,895 |
| Positive | 1,551 |
| Negative | 60 |
| Urgent | 7 |

Prioritize the **380 unreplied** messages, especially those tagged **negative** or **urgent**.

### Language mix

| Language | Count |
|----------|------:|
| English | 12,440 |
| Hinglish | 3,418 |
| Other | 645 |

Reply templates should support **English + Hinglish** (romanized Hindi).

### Response performance

- **16,133** messages marked as replied (includes business outbound)
- **380** customer messages with no business reply in-thread

Use `response_status: "not_replied"` and `is_business_outbound: false` in the JSON to build a follow-up queue.

## JSON schema (per message)

Each record in `consolidated_messages.json` includes:

- `id`, `sender`, `date` (ISO 8601), `platform`, `content`
- `category` — Question, Pricing, Inquiry, Complaint, Compliment, etc.
- `intent` — short summary of what the customer needs
- `context_clues` — e.g. urgent, wants callback, first-time customer
- `response_status` — `not_replied` | `replied` | `partially_replied` | `needs_follow_up`
- `language`, `sentiment`, `is_business_outbound`, `source_file`

See `metadata` in the JSON for full breakdowns (`category_breakdown`, `platform_breakdown`, `top_intents`, etc.).

## Recommended next steps

1. **Filter customer-only:** `is_business_outbound == false`
2. **Triage unreplied:** `response_status == "not_replied"`
3. **Build canned replies** for Pricing + Inquiry clusters
4. **Review complaints** (19) and urgent messages (7) manually
5. **Re-run** `consolidate_messages.py` when new Instagram exports are available
6. Add WhatsApp / email exports under `ahl/` or `alchemane/` and extend the script

## Re-running consolidation

```bash
python alchemane/consolidate_messages.py
```

Update `ROOT` in the script if the Instagram export path changes.

## Data quality notes

- Category, intent, sentiment, and language use **rule-based heuristics** (not LLM) — good for triage, not perfect classification.
- Instagram text encoding issues (mojibake) were repaired where possible.
- Duplicate detection is exact match on sender + timestamp + content (6 flagged).
- `comments/post_comments_1.json` reflects comments **made by the brand**, not inbound comments on your posts.

## Privacy

This dataset contains real customer names, handles, and message content. Restrict repo access to authorized AHL team members only.

---

*Consolidated on 2026-07-08 · Alchemane Hair Extensions | Luxury Hair*
