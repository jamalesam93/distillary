"""Distillary Orchestration CLI — Reverse engineered to run without Claude Code.

Supports Gemini, Claude, and OpenAI APIs. Orchestrates multi-agent pipelines
via dynamic agent markdown definitions.
"""

from __future__ import annotations

import os
import re
import sys
import yaml
import httpx
import asyncio
import argparse
import logging
from pathlib import Path
from bs4 import BeautifulSoup

from distillary.extraction.loader import extract_text, split_text, ScannedPDFError
from distillary.vault_ops import fix_vault, reinforce_links, build_entity_hubs
from distillary.doctor import doctor

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("distillary")

class LLMClient:
    def __init__(self):
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        
        # Load .env if present
        self.load_env()
        
        self.client = httpx.AsyncClient(timeout=180.0)

    def load_env(self):
        env_paths = [Path(".env"), Path("../.env"), Path("brain/.env")]
        for p in env_paths:
            if p.exists():
                logger.info(f"Loading environment from {p}")
                for line in p.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
        
        self.gemini_key = self.gemini_key or os.environ.get("GEMINI_API_KEY")
        self.anthropic_key = self.anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        self.openai_key = self.openai_key or os.environ.get("OPENAI_API_KEY")

    async def call(self, system_prompt: str, user_prompt: str, model_type: str = "haiku") -> str:
        """Call LLM with support for Gemini, Anthropic, and OpenAI."""
        # Prioritize Gemini for speed & cost (highly integrated with Antigravity)
        if self.gemini_key:
            model = "gemini-2.5-flash" if model_type == "haiku" else "gemini-2.5-pro"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": user_prompt}]}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"maxOutputTokens": 8192}
            }
            res = await self.client.post(url, json=payload)
            if res.status_code != 200:
                # Try fallback model
                fallback = "gemini-1.5-flash" if model_type == "haiku" else "gemini-1.5-pro"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{fallback}:generateContent?key={self.gemini_key}"
                res = await self.client.post(url, json=payload)
                if res.status_code != 200:
                    raise Exception(f"Gemini API Error {res.status_code}: {res.text}")
            data = res.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except KeyError:
                raise Exception(f"Unexpected Gemini API Response structure: {data}")
                
        elif self.anthropic_key:
            model = "claude-3-5-haiku-20241022" if model_type == "haiku" else "claude-3-5-sonnet-20241022"
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": self.anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": model,
                "max_tokens": 4000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}]
            }
            res = await self.client.post(url, json=payload, headers=headers)
            if res.status_code != 200:
                raise Exception(f"Anthropic API Error {res.status_code}: {res.text}")
            data = res.json()
            return data["content"][0]["text"]
            
        elif self.openai_key:
            model = "gpt-4o-mini" if model_type == "haiku" else "gpt-4o"
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "content-type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            res = await self.client.post(url, json=payload, headers=headers)
            if res.status_code != 200:
                raise Exception(f"OpenAI API Error {res.status_code}: {res.text}")
            data = res.json()
            return data["choices"][0]["message"]["content"]
            
        else:
            raise Exception("No API Key detected! Please export GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY.")

def parse_agent(name: str) -> tuple[dict, str]:
    """Parse agent metadata and system prompt from .claude/agents/{name}.md."""
    agent_path = Path(".claude/agents") / f"{name}.md"
    if not agent_path.exists():
        raise FileNotFoundError(f"Agent prompt definition not found at: {agent_path}")
    
    text = agent_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end_idx = text.find("---", 3)
        if end_idx != -1:
            meta_text = text[3:end_idx]
            meta = yaml.safe_load(meta_text) or {}
            system_prompt = text[end_idx + 3:].strip()
            return meta, system_prompt
            
    return {}, text.strip()

# ---------------------------------------------------------------------------
# Pipeline Tasks
# ---------------------------------------------------------------------------

async def run_extract(client: LLMClient, sem: asyncio.Semaphore, title: str, author: str, year: int, slug: str, chunk_file: Path, chunk_idx: int) -> str:
    async with sem:
        logger.info(f"Extracting claims from chunk {chunk_idx:02d}...")
        meta, system_prompt = parse_agent("extract")
        model = meta.get("model", "haiku")
        
        chunk_content = chunk_file.read_text(encoding="utf-8")
        user_prompt = (
            f"Read the following chunk: {chunk_file.name}\n"
            f"Source title: {title}\n"
            f"Author: {author}\n"
            f"Published: {year}\n"
            f"Source slug: {slug}\n"
            f"Write notes to: tmp/results/extract_{chunk_idx:02d}.md\n\n"
            f"--- CHUNK CONTENT ---\n{chunk_content}"
        )
        
        result = await client.call(system_prompt, user_prompt, model_type=model)
        
        # Save intermediate result
        out_path = Path("tmp/results") / f"extract_{chunk_idx:02d}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")
        logger.info(f"Chunk {chunk_idx:02d} claims extraction completed.")
        return result

async def run_dedupe(client: LLMClient, sem: asyncio.Semaphore, batch_content: str, batch_idx: int) -> str:
    async with sem:
        logger.info(f"Deduping batch {batch_idx:02d}...")
        meta, system_prompt = parse_agent("dedupe")
        model = meta.get("model", "haiku")
        
        user_prompt = (
            f"Read the following batch of claim notes:\n\n"
            f"{batch_content}\n\n"
            f"Write deduped claims to: tmp/results/dedupe_{batch_idx:02d}.md"
        )
        
        result = await client.call(system_prompt, user_prompt, model_type=model)
        out_path = Path("tmp/results") / f"dedupe_{batch_idx:02d}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")
        logger.info(f"Deduplication batch {batch_idx:02d} completed.")
        return result

async def run_entities(client: LLMClient, all_claims_content: str) -> str:
    logger.info("Extracting entities...")
    meta, system_prompt = parse_agent("entities")
    model = meta.get("model", "haiku")
    
    user_prompt = (
        f"Read all claim notes below and extract people, concepts, companies, and works:\n\n"
        f"{all_claims_content}\n\n"
        f"Write all entities to: tmp/results/entities.md"
    )
    result = await client.call(system_prompt, user_prompt, model_type=model)
    out_path = Path("tmp/results/entities.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    logger.info("Entity extraction completed.")
    return result

async def run_entity_link(client: LLMClient, deduped_content: str, entities_content: str) -> str:
    logger.info("Entity-linking claims...")
    meta, system_prompt = parse_agent("entity-link")
    model = meta.get("model", "haiku")
    
    user_prompt = (
        f"Read the entities lists:\n"
        f"{entities_content}\n\n"
        f"Read the deduped claims and add wikilinks to matching entities in body text:\n"
        f"{deduped_content}\n\n"
        f"Write linked claims to: tmp/results/linked_claims.md"
    )
    result = await client.call(system_prompt, user_prompt, model_type=model)
    out_path = Path("tmp/results/linked_claims.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    logger.info("Entity-linking completed.")
    return result

async def run_group(client: LLMClient, sem: asyncio.Semaphore, batch_content: str, batch_idx: int) -> str:
    async with sem:
        logger.info(f"Grouping claims batch {batch_idx:02d}...")
        meta, system_prompt = parse_agent("group")
        model = meta.get("model", "opus") # Opus defaults to Sonnet/Pro
        
        user_prompt = (
            f"Read the following batch of entity-linked claims:\n\n"
            f"{batch_content}\n\n"
            f"Group them into clusters of 3-7 by argumentative cohesion. "
            f"Write structural parent notes and Parent/Children links. "
            f"Write the FULL updated list to: tmp/results/group_{batch_idx:02d}.md"
        )
        result = await client.call(system_prompt, user_prompt, model_type=model)
        out_path = Path("tmp/results") / f"group_{batch_idx:02d}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")
        logger.info(f"Grouping batch {batch_idx:02d} completed.")
        return result

async def run_pyramid(client: LLMClient, layer1_content: str) -> str:
    logger.info("Building argumentative pyramid to root...")
    meta, system_prompt = parse_agent("pyramid")
    model = meta.get("model", "opus")
    
    user_prompt = (
        f"Read all layer-1 structural notes below:\n\n"
        f"{layer1_content}\n\n"
        f"Build hierarchy to a single root thesis (layer 3). "
        f"Write output to: tmp/results/pyramid.md"
    )
    result = await client.call(system_prompt, user_prompt, model_type=model)
    out_path = Path("tmp/results/pyramid.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    logger.info("Pyramid building completed.")
    return result

async def run_link(client: LLMClient, sem: asyncio.Semaphore, batch_content: str, batch_idx: int) -> str:
    async with sem:
        logger.info(f"Finding lateral links for batch {batch_idx:02d}...")
        meta, system_prompt = parse_agent("link")
        model = meta.get("model", "haiku")
        
        user_prompt = (
            f"Read the following linked claims:\n\n"
            f"{batch_content}\n\n"
            f"Identify lateral links (tensions, patterns, evidence) between notes. "
            f"Add ## Related links to note bodies. "
            f"Write to: tmp/results/link_{batch_idx:02d}.md"
        )
        result = await client.call(system_prompt, user_prompt, model_type=model)
        out_path = Path("tmp/results") / f"link_{batch_idx:02d}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")
        logger.info(f"Lateral links batch {batch_idx:02d} completed.")
        return result

async def run_source_index(client: LLMClient, title: str, author: str, year: int, slug: str) -> str:
    logger.info("Generating source index...")
    meta, system_prompt = parse_agent("source-index")
    model = meta.get("model", "haiku")
    
    # Read generated root notes and cluster notes
    vault_dir = Path("brain/sources") / slug
    root_notes = ""
    for md in vault_dir.rglob("*.md"):
        if md.name != "_source.md" and md.name != "_index.md":
            text = md.read_text(encoding="utf-8")
            if "layer: 3" in text or "layer: 2" in text:
                root_notes += f"## {md.stem}\n{text}\n\n"
                
    user_prompt = (
        f"Write a compelling, narrative index page for this source: {title} by {author} ({year}).\n"
        f"Source Slug: {slug}\n"
        f"Here are the core high-layer notes from the vault:\n\n"
        f"{root_notes}\n"
        f"Write the index output to: brain/sources/{slug}/_index.md"
    )
    result = await client.call(system_prompt, user_prompt, model_type=model)
    out_path = vault_dir / "_index.md"
    out_path.write_text(result, encoding="utf-8")
    logger.info("Source index generated successfully.")
    return result

async def run_brain_index(client: LLMClient) -> str:
    logger.info("Updating brain index page...")
    meta, system_prompt = parse_agent("brain-index")
    model = meta.get("model", "haiku")
    
    # Load all source indexes to orient
    source_overviews = ""
    for idx_md in Path("brain/sources").rglob("_index.md"):
        source_overviews += f"### Source: {idx_md.parent.name}\n"
        source_overviews += idx_md.read_text(encoding="utf-8") + "\n\n"
        
    user_prompt = (
        f"Update brain/_index.md to include a compelling overview of the brain.\n"
        f"Here are the existing source indexes:\n\n"
        f"{source_overviews}\n"
        f"Write main index output to: brain/_index.md"
    )
    result = await client.call(system_prompt, user_prompt, model_type=model)
    out_path = Path("brain/_index.md")
    out_path.write_text(result, encoding="utf-8")
    logger.info("Brain index page updated successfully.")
    return result

# ---------------------------------------------------------------------------
# Orchestrator Main Ingestion
# ---------------------------------------------------------------------------

async def add_source(file_path: str, title: str = None, author: str = None, year: int = None, slug: str = None):
    # Setup directories
    Path("tmp/results").mkdir(parents=True, exist_ok=True)
    Path("tmp/chunks").mkdir(parents=True, exist_ok=True)
    
    path = Path(file_path)
    if not path.exists():
        logger.error(f"Source file not found: {file_path}")
        return
        
    # Auto-detect metadata if not provided
    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").title()
    if not author:
        author = "Unknown Author"
    if not year:
        year = 2026
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        
    logger.info(f"Starting ingestion pipeline for '{title}' by {author} ({year}) [slug: {slug}]")
    
    # 1. Ingest/Extract text & split into chunks
    logger.info("Extracting document text...")
    try:
        text = extract_text(path)
        logger.info(f"Extraction successful: {len(text)} characters.")
    except ScannedPDFError as e:
        logger.error(f"Scanned PDF Error: {e}")
        logger.info("Image-based PDF requires OCR! OCR parallel flow not supported in CLI fallback. Please convert to .txt first.")
        return
        
    chunks = split_text(text, max_chars=20000)
    logger.info(f"Split text into {len(chunks)} chunks.")
    
    # Save chunks permanently
    chunk_dir = Path("brain/sources") / slug / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for idx, chunk in enumerate(chunks):
        chunk_file = chunk_dir / f"chunk_{idx:02d}.txt"
        chunk_file.write_text(chunk, encoding="utf-8")
        # Also copy to tmp for local processing
        tmp_chunk_file = Path("tmp/chunks") / f"chunk_{idx:02d}.txt"
        tmp_chunk_file.write_text(chunk, encoding="utf-8")
        
    # Ingest _source.md
    source_meta_path = Path("brain/sources") / slug / "_source.md"
    source_meta = {
        "title": title,
        "author": author,
        "type": "book" if path.suffix.lower() in [".pdf", ".epub"] else "article",
        "published": year,
        "url": "",
        "source_slug": slug,
        "ingested": "2026-05-29",
        "extracted_by": "gemini-distillary-orchestrator",
        "chunks_available": True,
        "publishable": False # Default to false for copyrighted materials
    }
    source_meta_path.write_text(f"---\n{yaml.dump(source_meta)}\n---\nDraft metadata.", encoding="utf-8")
    
    # Initialize API Client
    client = LLMClient()
    sem = asyncio.Semaphore(5) # Cap parallel executions at 5 to prevent rate limits
    
    # 2. Parallel claim extraction
    logger.info(f"Running claim extraction in parallel (limit: 5 concurrent)...")
    tasks = []
    for idx in range(len(chunks)):
        chunk_file = Path("tmp/chunks") / f"chunk_{idx:02d}.txt"
        tasks.append(run_extract(client, sem, title, author, year, slug, chunk_file, idx))
    
    await asyncio.gather(*tasks)
    logger.info("All claims extracted.")
    
    # 3. Combine & Deduplicate claims
    logger.info("Combining claims...")
    combined_claims = ""
    for f in sorted(Path("tmp/results").glob("extract_*.md")):
        combined_claims += f.read_text(encoding="utf-8") + "\n\n"
    Path("tmp/all_claims.md").write_text(combined_claims, encoding="utf-8")
    
    # Batch combined claims for deduplication (batches of ~100 notes)
    from distillary.notes import parse_notes, serialize
    notes_list = parse_notes(combined_claims)
    logger.info(f"Parsed {len(notes_list)} raw claim notes from extraction results.")
    
    batch_size = 100
    dedupe_tasks = []
    for idx in range(0, len(notes_list), batch_size):
        batch = notes_list[idx:idx + batch_size]
        batch_text = serialize(batch)
        batch_idx = idx // batch_size
        dedupe_tasks.append(run_dedupe(client, sem, batch_text, batch_idx))
        
    await asyncio.gather(*dedupe_tasks)
    
    # Concatenate deduped claims
    deduped_claims = ""
    for f in sorted(Path("tmp/results").glob("dedupe_*.md")):
        deduped_claims += f.read_text(encoding="utf-8") + "\n\n"
    Path("tmp/deduped_claims.md").write_text(deduped_claims, encoding="utf-8")
    
    # 4. Entity Extraction & Entity-Linking
    entities_text = await run_entities(client, deduped_claims)
    linked_claims_text = await run_entity_link(client, deduped_claims, entities_text)
    
    # 5. Group & Pyramid argument building
    linked_notes = parse_notes(linked_claims_text)
    logger.info(f"Parsed {len(linked_notes)} linked claim notes.")
    
    group_size = 70
    group_tasks = []
    for idx in range(0, len(linked_notes), group_size):
        batch = linked_notes[idx:idx + group_size]
        batch_text = serialize(batch)
        batch_idx = idx // group_size
        group_tasks.append(run_group(client, sem, batch_text, batch_idx))
        
    group_results = await asyncio.gather(*group_tasks)
    
    # Extract layer-1 parents from grouped results for pyramid thesis building
    l1_notes = []
    for res_text in group_results:
        g_notes = parse_notes(res_text)
        for gn in g_notes:
            if gn.meta.get("layer") == 1:
                l1_notes.append(gn)
                
    l1_content = serialize(l1_notes)
    await run_pyramid(client, l1_content)
    
    # 6. Lateral link relationships
    link_tasks = []
    for idx in range(0, len(linked_notes), group_size):
        batch = linked_notes[idx:idx + group_size]
        batch_text = serialize(batch)
        batch_idx = idx // group_size
        link_tasks.append(run_link(client, sem, batch_text, batch_idx))
        
    await asyncio.gather(*link_tasks)
    
    # 7. Post-process and Assemble Obsidian Vault!
    logger.info("Post-processing and assembling vault...")
    stats = fix_vault("tmp", f"brain/sources/{slug}")
    reinforce_links("brain")
    build_entity_hubs("brain")
    doctor("brain")
    
    # Run auto-bridging if multiple sources exist
    sources_dir = Path("brain/sources")
    existing_sources = [d for d in sources_dir.iterdir() if d.is_dir()]
    if len(existing_sources) > 1:
        await run_auto_bridge(client, slug)
    
    # 8. Indexes updating
    await run_source_index(client, title, author, year, slug)
    await run_brain_index(client)
    
    logger.info(f"Pipeline complete! Output saved to: brain/sources/{slug}/")
    print("\n" + "="*50)
    print(f"DONE! '{title}' successfully added to your brain.")
    print(f"Total Notes Created: {stats.get('total_notes', 0)}")
    print(f"Claims: {stats.get('claims', 0)} atoms")
    print(f"Entities: {stats.get('entities', 0)} notes")
    print(f"Obsidian Vault: brain/sources/{slug}/")
    print("="*50 + "\n")

# ---------------------------------------------------------------------------
# CLI Command Entry & Additional Pipelines
# ---------------------------------------------------------------------------

async def run_auto_bridge(client: LLMClient, new_slug: str):
    logger.info("Running concept mapping to find bridge concepts...")
    
    # Load entities from all sources
    vault_path = Path("brain")
    from distillary.doctor import _load_vault
    notes = _load_vault(vault_path)
    
    entity_notes = [n for stem, n in notes.items() if n["meta"].get("kind") == "entity"]
    logger.info(f"Loaded {len(entity_notes)} entity notes for concept mapping.")
    
    # Compile entity details for LLM
    entity_str = ""
    for ent in entity_notes:
        stem = ent["path"].stem
        tags = ent["meta"].get("tags", [])
        body = ent["body"].strip().split("\n## ")[0].strip() # Get description only
        entity_str += f"## {stem}\nTags: {tags}\nDescription: {body}\n\n"
        
    meta, system_prompt = parse_agent("concept-mapper")
    model = meta.get("model", "opus")
    
    user_prompt = (
        f"Here are the concept and people entities in the combined brain vault:\n\n"
        f"{entity_str}\n"
        f"Perform concept mapping. Find identical concepts discussion under different names "
        f"across different sources, and complementary concepts. Output a markdown table as requested."
    )
    
    result = await client.call(system_prompt, user_prompt, model_type=model)
    logger.info("Concept mapping table generated. Parsing pairs and building bridges...")
    
    # Save the mapping result for records
    mapping_path = Path("tmp/results/concept_mapping.md")
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(result, encoding="utf-8")
    
    # Parse pairs from markdown table
    pairs = []
    lines = result.splitlines()
    for line in lines:
        if "|" in line and ("[[" in line or "[[ " in line):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 5:
                e_a = re.findall(r"\[\[(.*?)\]\]", parts[1])
                e_b = re.findall(r"\[\[(.*?)\]\]", parts[2])
                merged = parts[3].strip()
                desc = parts[4].strip()
                if e_a and e_b and merged and not merged.startswith("Unified") and not merged.startswith("Merged") and not merged.startswith("Bridge"):
                    pairs.append({
                        "ls": e_a[0].strip(),
                        "mt": e_b[0].strip(),
                        "merged": merged.strip(),
                        "description": desc.strip()
                    })
                    
    if pairs:
        logger.info(f"Building {len(pairs)} bridge concepts...")
        from distillary.cross_vault import _build_bridges
        _build_bridges(Path("brain"), pairs)
        reinforce_links("brain")
        build_entity_hubs("brain")
        logger.info("Bridge concept mapping and rewiring completed successfully.")
    else:
        logger.info("No semantic overlapping concept pairs found.")

def init_brain():
    Path("brain/sources").mkdir(parents=True, exist_ok=True)
    Path("brain/shared/concepts").mkdir(parents=True, exist_ok=True)
    Path("brain/shared/analytics").mkdir(parents=True, exist_ok=True)
    Path("brain/personal/annotations").mkdir(parents=True, exist_ok=True)
    Path("brain/personal/research").mkdir(parents=True, exist_ok=True)

def run_doctor():
    init_brain()
    logger.info("Running Doctor Agent to scan and heal the brain vault...")
    stats = doctor("brain")
    print("\n" + "="*50)
    print("DOCTOR HEAL COMPLETE!")
    print(f"Fixes applied: {stats.get('fixes', 0)}")
    print(f"Ghost notes created: {stats.get('ghosts_created', 0)}")
    print(f"Actionable suggestions generated: {stats.get('suggestions', 0)}")
    print("Output saved to: brain/_suggestions.md")
    print("="*50 + "\n")

async def run_research(question: str):
    logger.info(f"Initiating Deep Research for: '{question}'")
    client = LLMClient()
    
    # Load all notes from brain vault
    from distillary.doctor import _load_vault
    vault_path = Path("brain")
    if not vault_path.exists():
        logger.error("No brain vault found! Run 'add' first to ingest some sources.")
        return
        
    notes = _load_vault(vault_path)
    logger.info(f"Loaded {len(notes)} notes from vault for search.")
    
    # Simple keyword search across all notes
    keywords = re.findall(r"\b\w{4,}\b", question.lower())
    arabic_keywords = re.findall(r"[\u0600-\u06FF\w]{4,}", question)
    all_keywords = list(set(keywords + arabic_keywords))
    
    matched_notes = []
    for stem, data in notes.items():
        score = 0
        content = (stem + " " + data["body"] + " " + yaml.dump(data["meta"])).lower()
        for kw in all_keywords:
            if kw in content:
                score += 1
        if score > 0:
            matched_notes.append((score, stem, data))
            
    # Sort by relevance score descending
    matched_notes.sort(key=lambda x: x[0], reverse=True)
    top_matches = matched_notes[:25] # Top 25 matching notes for context
    
    context_str = ""
    for score, stem, data in top_matches:
        context_str += f"## {stem}\n"
        context_str += f"Frontmatter:\n{yaml.dump(data['meta'])}"
        context_str += f"Body:\n{data['body']}\n\n"
        
    meta, system_prompt = parse_agent("research")
    model = meta.get("model", "opus")
    
    user_prompt = (
        f"You have been asked the following research question: '{question}'\n\n"
        f"Here are the top relevant claims and entities from the brain vault to answer this question:\n\n"
        f"{context_str}\n"
        f"Formulate a complete, structured research report following the 'Your output' guidelines in the system prompt. "
        f"Trace every point to claims, cite backings, explain warrants, and calculate confidence."
    )
    
    logger.info("Generating deep research synthesis report...")
    result = await client.call(system_prompt, user_prompt, model_type=model)
    
    # Save the output to brain/personal/research/
    research_dir = Path("brain/personal/research")
    research_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate a safe filename
    safe_q = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:50]
    out_path = research_dir / f"{safe_q}.md"
    out_path.write_text(result, encoding="utf-8")
    
    print("\n" + "="*50)
    print("RESEARCH REPORT COMPLETE!")
    print(f"Output saved to: brain/personal/research/{out_path.name}")
    print("="*50 + "\n")
    print(result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distillary Orchestrator CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Command: add
    add_parser = subparsers.add_parser("add", help="Add a source to the brain")
    add_parser.add_argument("file", help="Path to book, EPUB, PDF or text file")
    add_parser.add_argument("--title", help="Title of the source")
    add_parser.add_argument("--author", help="Author of the source")
    add_parser.add_argument("--year", type=int, help="Publication year")
    add_parser.add_argument("--slug", help="Custom folder slug")
    
    # Command: research
    research_parser = subparsers.add_parser("research", help="Deep research on a question")
    research_parser.add_argument("question", help="The research question")
    
    # Command: doctor
    doctor_parser = subparsers.add_parser("doctor", help="Scan and heal the vault")
    
    args = parser.parse_args()
    
    if args.command == "add":
        asyncio.run(add_source(
            file_path=args.file,
            title=args.title,
            author=args.author,
            year=args.year,
            slug=args.slug
        ))
    elif args.command == "research":
        asyncio.run(run_research(args.question))
    elif args.command == "doctor":
        run_doctor()
    else:
        parser.print_help()

