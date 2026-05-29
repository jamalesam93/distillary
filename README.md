# Distillary

**Turn any knowledge source into a navigable, shareable brain.**

[Demo Brain](https://brain.distillary.xyz) | [Docs](https://distillary.xyz) | [Discord](https://discord.gg/rGwB4hPMCp)

---

## Quick start

### Try an existing brain (30 seconds)

Browse a published brain right now:

1. Go to the [Demo Brain](https://brain.distillary.xyz)
2. Click any source's root thesis to read the argument
3. Follow `[[wikilinks]]` to drill deeper
4. Check entity pages — their backlinks answer "what does this brain know about X?"

Or query it from your agent — fetch `/agent.json` and follow the navigation instructions.

### Create your own brain (15 minutes)

```bash
curl -fsSL https://raw.githubusercontent.com/distillary/distillary/main/install.sh | bash
cd ~/distillary && claude
```

Then say:

> Add ~/Downloads/my-book.epub to my brain

That's it. Three commands. Claude runs 14 agents in parallel and builds your brain in ~15 minutes. Open `brain/` in [Obsidian](https://obsidian.md) to explore.

### Add a second source

> Add books/another-book.epub to my brain

Claude auto-bridges the new source to everything already in your brain — finds same concepts under different names, writes a comparison essay, creates unified entity pages.

### Publish

> Publish my brain

Your brain becomes a static website with graph view, search, backlinks, and an agent API at `/agent.json`.

---

## What Distillary does

You give it a source (book, video, article). It gives you:

- **A pyramid of claims** — root thesis → chapter clusters → argument groups → atomic evidence, each traceable to a chapter via `source_ref`
- **Entity hubs** — every person, concept, and company gets a page where backlinks from every source show what your brain knows about it
- **Bridge concepts** — when two sources call the same idea by different names, a bridge entity unifies them with both perspectives
- **Your annotations** — your reactions, questions, and insights are part of the graph

All in one `brain/` vault that works in Obsidian and publishes as a website.

---

## How it works

```
Source (book, video, article)
  → 16 parallel haiku agents extract atomic claims (~2 min)
  → Deduplicate + extract entities (~2 min)
  → Opus agents build argumentative pyramid (~5 min)
  → Find tensions, patterns, evidence (~2 min)
  → Doctor fixes issues + suggests explorations (~1 min)
  → Bridge to existing sources in brain
```

14 agents total. Haiku for fast parallel work. Opus for reasoning. Everything defined in `.claude/agents/` and orchestrated by `.claude/skills/`.

---

## For AI agents

Published brains have an `agent.json` manifest. Any agent can query them:

```
curl https://brain.distillary.xyz/static/skill.txt   # get the skill
curl https://brain.distillary.xyz/static/agent.json  # get the manifest
```

Paste the skill into any agent's system prompt — Claude Code, Codex, Gemini CLI, Cursor, or anything with HTTP access. The agent fetches `agent.json`, picks a strategy, and walks pages by relevance. 2 fetches, under 2000 tokens per question.

### Demo: 10 questions answered from the live brain

| # | Question | Strategy | Fetches |
|---|---|---|---|
| 1 | What books are in this brain? | Read manifest | 1 |
| 2 | What are the main ideas? | Fetch clusters | 2 |
| 3 | What does Barnum say about debt? | Concept lookup | 2 |
| 4 | Does luck play a role in success? | Concept lookup | 2 |
| 5 | How important is integrity? | Concept lookup | 2 |
| 6 | Career advice? | Concept lookup | 2 |
| 7 | Role of health in wealth? | Concept lookup | 2 |
| 8 | How to advertise? | Concept lookup | 2 |
| 9 | Who is P.T. Barnum? | Entity lookup | 2 |
| 10 | Root thesis? | Fetch root note | 2 |

**Average: 1.9 fetches per question.** All answers sourced from [brain.distillary.xyz](https://brain.distillary.xyz) — no local files. [Full answers →](https://distillary.xyz/4---For-Agents/demo)

Five question strategies: **concept** ("what is X?"), **source** ("summarize"), **comparison** ("do they agree?"), **evidence** ("prove it"), **exploration** ("what's related?"). [Setup guide →](https://distillary.xyz/4---For-Agents/agent-retrieval)

---

## Community

Tag repos `distillary-brain` on GitHub. Join the [Discord](https://discord.gg/rGwB4hPMCp). Share brains, request distillations, compare sources.

---

## Project structure

```
.claude/           17 agents + 10 skills (the brain)
distillary/        Python utilities agents call
brain/             Your knowledge vault (the output)
docs/              Documentation
```

[Full docs →](https://distillary.xyz) | [Architecture →](https://distillary.xyz/3---Deployment/architecture) | [Agent demo →](https://distillary.xyz/4---For-Agents/demo)

---

---

## This fork — multi-LLM support & keyless execution

This is a fork of [distillary/distillary](https://github.com/distillary/distillary) that adds two things the original doesn't have:

### 1. Standalone Python CLI (`distillary_orchestrator.py`)

Run the full Distillary pipeline **without Claude Code** — from any terminal (Cursor, VS Code, plain shell):

```bash
# With Gemini
GEMINI_API_KEY=your_key python distillary_orchestrator.py add my-book.pdf --title "My Book" --author "Author"

# With Claude API
ANTHROPIC_API_KEY=your_key python distillary_orchestrator.py add my-book.pdf

# With OpenAI
OPENAI_API_KEY=your_key python distillary_orchestrator.py add my-book.pdf
```

The orchestrator reads the same `.claude/agents/*.md` prompt files as the original — so it stays compatible with upstream. Agents map to models by the `model:` frontmatter field (`haiku` → fast model, `opus` → reasoning model) across all providers.

### 2. Antigravity native skill (keyless)

Run the pipeline with **zero API keys** through an active [Antigravity](https://antigravity.ai) session. The orchestration spawns native subagents — no billing, no rate limits beyond your subscription.

→ **[Full hands-on tutorial: Using Distillary with Antigravity](docs/guides/antigravity.md)**

This was built to solve a real constraint: Gemini's free API tier hits limits before finishing a single book. The Antigravity path bypasses that entirely.

### What's unchanged

Everything in `.claude/agents/`, `distillary/`, and the brain vault format is **100% compatible** with the original. Brains generated by this fork open in Obsidian and publish via Quartz identically to the original.

### Tested on

- *An Inheritance of Shadow: Book One* by Gamal Alsakkaf — 975 KB PDF → 211 notes, 1,585 wikilinks, 96.9% resolution, 0 structural issues

---

## License

MIT

---

*Built with Claude agents. Published with [Quartz](https://quartz.jzhao.xyz/). The brains are the value, not the tool.*
