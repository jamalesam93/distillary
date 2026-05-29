---
title: Using Distillary with Antigravity (Keyless)
---

# Using Distillary with Antigravity

Run the full Distillary pipeline **with no API keys** through an active [Antigravity](https://antigravity.ai) session.

Antigravity is an AI coding assistant (similar to Cursor) powered by Google Gemini. Instead of Claude Code spawning subagents, Antigravity spawns them natively through its conversation engine — meaning you get the full 12-stage pipeline without touching a single API key or paying per-token.

---

## Why this exists

The original Distillary requires Claude Code. If you use Antigravity (or don't have a Claude Code subscription), you're locked out. Additionally, Gemini's free API tier hits rate limits before finishing even a single chapter of a book — making the standalone CLI impractical without a paid key.

This path bypasses both constraints. The pipeline runs entirely through your Antigravity subscription.

---

## Prerequisites

- An active [Antigravity](https://antigravity.ai) subscription
- Python 3.11+ installed
- This repo cloned and open as an Antigravity workspace:

```bash
git clone https://github.com/jamalesam93/distillary.git
cd distillary
pip install pyyaml ebooklib beautifulsoup4 pypdfium2
```

> **Note**: `pypdfium2` replaces the original `langchain-community` PDF dependency in this fork. If you have EPUB files, also install `ebooklib beautifulsoup4`.

---

## Setup: add your book

Create a folder for your source files and drop your book in it:

```
distillary/
└── my books/
    └── my-book.pdf     ← put it here
```

The folder name `my books/` is already in `.gitignore` — your source files will never be committed.

---

## Step 1 — Open the project in Antigravity

In Antigravity, add the `distillary/` folder as a workspace. You can do this by:

- Opening Antigravity → **Add Workspace** → select the `distillary/` folder

Once it's open, you're ready.

---

## Step 2 — Start the ingestion

Type the following in the Antigravity chat (adjust title, author, and year to your book):

> Add `my books/my-book.pdf` to my brain. Title: "My Book Title", Author: "Author Name", Year: 2024

That's the entire prompt. Antigravity will:

1. Read the `.claude/agents/` prompt files to understand the pipeline
2. Extract and chunk your book's text using Python
3. Spawn subagents for each stage of the pipeline
4. Assemble the final vault automatically

**You don't need to do anything else.** Watch the progress in the chat.

---

## What you'll see as it runs

The pipeline runs in stages. Here's what each looks like in the Antigravity chat:

### Stage 1 — Text extraction & chunking (~30 sec)

Antigravity runs Python to extract text from your PDF/EPUB and splits it into ~20,000-character chunks. You'll see something like:

```
Extraction successful: 312,450 characters.
Split text into 16 chunks.
```

### Stage 2 — Parallel claims extraction (~3–5 min)

16 subagents launch simultaneously, one per chunk. Each reads its chunk and extracts atomic claims with evidence and source passages. You'll see them completing in the chat as they finish:

```
[Chunk 00] Extracted 11 claims
[Chunk 03] Extracted 9 claims
[Chunk 07] Extracted 14 claims
...
[All chunks complete] 145 raw claims total
```

> **Tip**: This is the longest stage. It's normal for subagents to complete out of order.

### Stage 3 — Deduplication (~1–2 min)

Claims are batched and two subagents deduplicate them, merging near-identical claims and keeping the strongest version of each:

```
Deduplication complete: 145 → 139 unique claims
```

### Stage 4 — Entity extraction (~1 min)

One subagent reads all claims and identifies the key people, places, concepts, and works mentioned. It generates canonical names and aliases:

```
Entities extracted: 28 canonical entities, 46 aliases
```

### Stage 5 — Entity-linking (~30 sec)

A Python script (not an LLM call) injects `[[wikilinks]]` into every claim body wherever a canonical entity or alias appears. This is deterministic — 100% accurate:

```
Entity-linking complete: 555 wikilinks injected
```

### Stage 6 — Grouping (~3–5 min)

Two subagents read all 139 claims and group them into cohesive argumentative clusters. Each group becomes a **Layer 1 parent note** with a synthesized title:

```
Grouping complete: 27 Layer 1 parent notes created
```

### Stage 7 — Pyramid (~3–5 min)

One subagent reads all 27 Layer 1 notes and builds the **argumentative pyramid**:
- Groups the 27 parents into 5 **Layer 2 structural clusters**
- Synthesizes all 5 clusters into 1 **Layer 3 root thesis** — the book's central argument in one sentence

```
Pyramid complete: 5 clusters + 1 root thesis
```

### Stage 8 — Lateral linking (~2–3 min)

Two subagents identify connections *across* claims — tensions, patterns, and evidence relationships — and add `## Related` sections to both sides of each link:

```
Lateral linking complete
```

### Stage 9 — Vault assembly (~30 sec)

Python assembles everything: writes notes to `brain/sources/`, reinforces all wikilinks, builds entity hub pages, and runs the doctor to flag and fix structural issues:

```
fix_vault complete: 206 notes written
Doctor complete: 10 fixes applied
```

### Stage 10 — Source index (~1 min)

One subagent reads your root thesis and clusters and writes a compelling narrative introduction for your source at `brain/sources/your-book/_index.md`:

```
Source index written to brain/sources/your-book/_index.md
```

### Stage 11 — Brain index (~1 min)

One subagent writes the brain's front page at `brain/_index.md`, framing what the brain covers and guiding readers to starting points:

```
Brain index written to brain/_index.md
```

### Stage 12 — Validation (~10 sec)

Antigravity runs `vault_ops.validate()` and reports the final integrity check:

```
Total notes: 211
Wikilinks resolved: 96.9%
Structural issues: 0
```

**Total time: approximately 20–30 minutes** depending on book length.

---

## Step 3 — Open your brain in Obsidian

1. Open **Obsidian** → **Open folder as vault**
2. Navigate to `distillary/brain/` and select it
3. Open `_index.md` — your entry point

**Recommended Obsidian setup:**

- Enable **Graph view** (`Ctrl+G`) — see all notes interconnected
- Enable **Bases** core plugin (Settings → Core plugins → Bases) for table views
- Enable the CSS snippet: Settings → Appearance → CSS snippets → toggle `distillary-tags`

**Where to start exploring:**

- `brain/_index.md` — brain overview
- `brain/sources/your-book/_index.md` — source narrative introduction
- Graph view — the root thesis will be the largest hub at the center
- Click any `[[wikilink]]` to navigate through the knowledge graph
- **Backlinks panel** (right sidebar) — see every note that references the current one

---

## Adding a second book

Once your first brain is complete, add a second source the same way:

> Add `my books/second-book.pdf` to my brain. Title: "Second Book", Author: "Author", Year: 2023

Antigravity will run the same pipeline, then additionally:
- Map concepts between both sources (concept-mapper agent)
- Create bridge entity pages in `brain/shared/concepts/`
- Write a comparison essay in `brain/shared/analytics/`
- Update `brain/_index.md` to cover both sources

---

## Asking research questions

Once your brain is built, you can query it directly in Antigravity:

> Research: what does this brain say about [topic]?

Or compare across sources:

> Research: how does [Book A] and [Book B] differ on [topic]?

Antigravity will use the deep research agent to walk your brain, follow backlink chains, check evidence quality, and write a structured answer with citations.

---

## Limitations

| Limitation | Notes |
|---|---|
| **No `publish` command** | Quartz web publishing still requires the CLI with an API key. The `brain/` vault works perfectly in Obsidian in the meantime. |
| **Book length** | Books over ~500 pages may take 40+ minutes. Consider splitting very long books into parts. |
| **Model selection** | The pipeline works best when Antigravity uses a capable model (Gemini 2.5 Pro or Claude Opus) for the grouping and pyramid stages. Flash-tier models work for extraction. |
| **One book at a time** | Don't start a second ingestion while one is in progress — the `tmp/` working directory is shared. |

---

## Tips

- **Start with one book.** Get comfortable with the output before adding a second.
- **Ghost wikilinks are fine.** After ingestion, some `[[wikilinks]]` may point to entities that don't have notes yet (secondary characters, places). These show as greyed-out in Obsidian's graph. Click one to create a new note — it's how the vault naturally grows.
- **The `_suggestions.md` file** in `brain/` lists exploration questions the doctor agent generated. These are good starting points for follow-up research.
- **Check `passages:` in atom notes** — each Layer 0 claim links back to the source chunk it came from, so you can verify any claim against the original text.

---

## Troubleshooting

**Antigravity stops partway through**

The pipeline is stateful — intermediate results are saved in `tmp/results/`. If a stage fails, you can resume by telling Antigravity which stage to re-run, e.g.:

> The grouping stage failed. Re-run grouping using the claims already in tmp/results/

**Some claims look wrong or too vague**

The extraction stage is parallel and fast — occasional low-quality claims are normal. The deduplication and grouping stages filter out the weakest ones. The Layer 1+ notes are consistently higher quality.

**Wikilink resolution is below 90%**

This usually means some entity aliases weren't captured. You can ask Antigravity:

> Review the entities in tmp/results/entities.md and add any missing aliases, then re-run entity-linking.

---

## What's next

- [How it works](how-it-works.md) — full pipeline and note format explained
- [Argumentation layer](argumentation-layer.md) — how evidence (`backing:`, `passages:`) is captured
- [Architecture](architecture.md) — agents, prompts, and utilities
- [Publishing](publishing.md) — share your brain as a website (requires CLI)
