"""
engine.py - Clinical Intelligence Engine for ClinAssist Uganda

Pipeline:
    INPUT LAYER
        → patient symptoms, age group, duration, setting, history

    STEP 1: CONTEXTUAL RETRIEVAL (RAG)
        → age-aware ChromaDB vector search
        → chunk scoring and age-group filtering

    STEP 2: REASONING PASS
        → Gemma 4 e2b deliberates freely on the clinical case
        → reasoning is passed back as assistant turn in Step 3
        → this forces Step 3 to be consistent with Step 2 reasoning

    STEP 3: STRUCTURED SYNTHESIS
        → Gemma 4 receives its own reasoning as context
        → produces enforced JSON schema
        → sources always injected from Python metadata

    STEP 4: VALIDATION & SELF-CORRECTION
        → schema validation
        → auto-retry with error context
        → confidence normalisation
"""


# Standard library imports
import json                        # JSON parsing and validation
import logging                     # Logging engine activity/errors
import os                          # Environment variable handling
import time                        # Latency/performance timing
from pathlib import Path           # File path handling

# Ollama local LLM client
import ollama


# Local project imports
from database import query as db_query, collection_is_empty
from prompts  import SYSTEM_PROMPT, DRUG_REFERENCE_PROMPT

# =============================================================================
# LOGGER SETUP
# =============================================================================

# Create logger for engine diagnostics and monitoring
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Main Ollama model used for reasoning/synthesis
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL",          "gemma4:e2b")

# Path to Chroma vector database
CHROMA_PATH        = os.getenv("CHROMA_PATH",           str(Path(__file__).parent.parent / "chroma_db"))

# Maximum tokens for reasoning phase
MAX_TOKENS_REASON  = int(os.getenv("MAX_TOKENS_REASON", "1024"))

# Maximum tokens for structured synthesis phase
MAX_TOKENS_SYNTH   = int(os.getenv("MAX_TOKENS_SYNTH",  "4000"))

# Number of chunks retrieved from ChromaDB
TOP_K_CHUNKS       = int(os.getenv("TOP_K_CHUNKS",      "5"))

# Maximum validation/self-correction retries
MAX_RETRIES        = int(os.getenv("MAX_RETRIES",       "2"))


# -------------------------------------------------------------------------
# Legacy/OpenAI compatibility settings
# These are retained for compatibility with external health checks
# -------------------------------------------------------------------------
LLM_BACKEND  = os.getenv("LLM_BACKEND", "ollama")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")


# =============================================================================
# STEP 1 — CONTEXTUAL RETRIEVAL (RAG)
# =============================================================================

def _build_age_profile(age_group: str) -> dict:
    """
    Build an age-aware retrieval profile.

    The purpose is to bias retrieval toward guideline chunks
    relevant to the patient's demographic group.

    Example:
        - Under-5 children → retrieve paediatric dosing
        - Pregnant women → retrieve antenatal guidance
        - Elderly → retrieve older-adult management

    Returns:
        dict containing:
            qualifier     → retrieval expansion text
            keep_words    → words to boost
            filter_words  → words to penalise
    """

    age_lower = age_group.lower()

    # Elderly patient profile
    if "elderly" in age_lower:
        return {
            "qualifier":    "elderly older adult treatment management",
            "keep_words":   ["adult", "elderly", "older"],
            "filter_words": ["paediatric", "infant", "neonatal", "newborn", "child dose"],
        }
    # Pregnant patient profile
    elif "pregnant" in age_lower:
        return {
            "qualifier":    "pregnant woman antenatal maternal treatment safety",
            "keep_words":   ["pregnant", "maternal", "antenatal", "obstetric", "trimester"],
            "filter_words": ["infant", "neonatal", "newborn"],
        }
    # Under-5 paediatric profile
    elif "under 5" in age_lower:
        return {
            "qualifier":    "child under five infant paediatric IMCI treatment",
            "keep_words":   ["child", "infant", "paediatric", "mg/kg", "under 5", "imci"],
            "filter_words": ["adult dose", "elderly"],
        }
    # School-age child profile
    elif "5" in age_lower or "child" in age_lower:
        return {
            "qualifier":    "school age child paediatric treatment management",
            "keep_words":   ["child", "paediatric", "mg/kg"],
            "filter_words": ["infant", "neonatal", "adult dose"],
        }
    # Default adult profile
    else:
        return {
            "qualifier":    "adult outpatient treatment management",
            "keep_words":   [],
            "filter_words": ["paediatric", "infant", "neonatal", "newborn"],
        }


def _score_chunk(chunk: dict, keep_words: list, filter_words: list) -> int:
    """
    Score a retrieved chunk using keyword heuristics.

    Positive matches increase score.
    Negative matches decrease score.

    This helps prioritise age-appropriate guideline chunks.
    """

    text = chunk["text"].lower()
    return (
        sum(1 for w in keep_words   if w in text) -
        sum(1 for w in filter_words if w in text)
    )


def retrieve_chunks(symptoms: str, age_group: str, duration: str) -> list:
    """
    STEP 1: Retrieve relevant clinical guideline chunks.

    Workflow:
        1. Build age-aware retrieval profile
        2. Construct enriched semantic query
        3. Query ChromaDB vector store
        4. Re-rank chunks using keyword scoring
        5. Filter irrelevant age-group content

    Returns:
        List of ranked chunk dictionaries
    """

    # Build demographic-specific retrieval strategy
    profile    = _build_age_profile(age_group)
     # Construct enriched retrieval query
    query_text = (
        f"Uganda clinical guidelines {profile['qualifier']} "
        f"diagnosis treatment {symptoms} duration {duration}"
    )

    # Query ChromaDB
    chunks = db_query(query_text, top_k=TOP_K_CHUNKS)
    logger.info(
        f"[STEP 1] Retrieved {len(chunks)} chunks | "
        f"top distance: {chunks[0]['distance'] if chunks else 'n/a'}"
    )

    # Apply heuristic chunk re-ranking
    kw = profile["keep_words"]
    fw = profile["filter_words"]
    if kw or fw:
        # Rank chunks by age relevance
        scored   = sorted(chunks, key=lambda c: _score_chunk(c, kw, fw), reverse=True)

        # Keep only non-negative chunks
        filtered = [c for c in scored if _score_chunk(c, kw, fw) >= 0]

        # Avoid over-filtering:
        # if too few chunks survive, keep top-ranked originals
        chunks   = filtered if len(filtered) >= 3 else scored[:TOP_K_CHUNKS]
    return chunks


def _build_context(chunks: list) -> str:
    """
    Convert retrieved chunks into a formatted context block.

    The context is passed directly into the LLM prompt.
    """

    if not chunks:
        return "No relevant guideline content retrieved."
    
    parts = []

    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        # Add labelled source metadata
        parts.append(
            f"[Source {i}] {meta.get('document','Unknown')} | "
            f"{meta.get('chapter','General')} | p.{meta.get('page','?')}\n"
            f"{chunk['text']}"
        )
    return "\n\n---\n\n".join(parts)


def _extract_sources(chunks: list) -> list:
    """
    Build citation/source list directly from chunk metadata.

    IMPORTANT:
        Sources NEVER come from the LLM.
        This eliminates hallucinated citations entirely.
    """

    seen, sources = set(), []
    for chunk in chunks:
        meta = chunk["metadata"]

        # Create unique source identifier
        key  = f"{meta.get('document','')}_{meta.get('page','')}"

        # Avoid duplicate references
        if key not in seen:
            seen.add(key)
            sources.append({
                "document":  meta.get("document", "Uganda Clinical Guidelines 2023"),
                "chapter":   meta.get("chapter",  "General"),
                "page":      meta.get("page",      "?"),
                "relevance": "Retrieved as relevant guideline evidence",
            })
    # Limit number of returned sources
    return sources[:4]


# =============================================================================
# STEP 2 — REASONING PASS
# =============================================================================

# Prompt used for unrestricted clinical reasoning
REASONING_PROMPT = """You are a clinical decision support assistant for Uganda's health system.

PATIENT:
- Age group: {age_group}
- Symptoms: {symptoms}
- Duration: {duration}
- Setting: {setting}

RETRIEVED GUIDELINE EVIDENCE:
{context}

Reason through this clinical case carefully:
1. What are the most likely diagnoses and why, based on the guideline evidence?
2. What features support or argue against each diagnosis?
3. What is the urgency level and why?
4. What investigations are needed to confirm the diagnosis?
5. What is the appropriate treatment for {age_group} per the Uganda Clinical Guidelines?

Reference the source numbers above. Think like a senior clinical officer in Uganda."""


def reasoning_pass(
    symptoms: str,
    age_group: str,
    duration: str,
    setting: str,
    context: str,
) -> str:
    """
    STEP 2: Free-form reasoning phase.

    This is intentionally unrestricted.

    The model:
        - deliberates clinically
        - weighs diagnoses
        - reasons about urgency
        - plans investigations
        - proposes treatment

    The reasoning output is later injected back into Step 3.
    This creates consistency between reasoning and final JSON.
    """

    logger.info("[STEP 2] Starting reasoning pass")

    # Populate reasoning prompt template
    prompt = REASONING_PROMPT.format(
        age_group=age_group,
        symptoms=symptoms,
        duration=duration,
        setting=setting,
        context=context,
    )

    # Call Ollama for unrestricted reasoning
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {
                "role":    "system",
                "content": (
                    "You are an expert clinical reasoning assistant for Uganda's health system. "
                    "Think carefully and be specific. Reference guideline sources by number."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        options={
            "temperature": 0.3,
            "num_predict": MAX_TOKENS_REASON,
        },
    )

    reasoning = response["message"]["content"]
    logger.info(f"[STEP 2] Reasoning complete ({len(reasoning)} chars)")
    return reasoning


# =============================================================================
# STEP 3 — STRUCTURED SYNTHESIS
# =============================================================================

SYNTHESIS_PROMPT = """Now convert your reasoning into a structured clinical assessment.

PATIENT: {age_group} | {symptoms} | {duration} | {setting}

STRICT RULES:
- Confidence scores: decimals 0.0 to 1.0 ONLY (e.g. 0.85 not 85)
- Dosing: must match {age_group} exactly — never mix adult and paediatric doses
- Return ONLY the JSON object. No text before or after. No markdown fences.

{{
  "triage": {{"level": "URGENT or MODERATE or LOW", "label": "max 8 words", "reason": "one sentence"}},
  "diagnoses": [
    {{"name": "diagnosis name", "confidence": 0.85, "icd10": "code or null", "reasoning": "one sentence"}}
  ],
  "tests": [
    {{"name": "specific test name", "priority": "URGENT or ROUTINE", "rationale": "why this test"}}
  ],
  "treatments": [
    {{"step": "First line or Second line or Supportive or Referral", "action": "specific drug dose route for {age_group}", "notes": "note"}}
  ],
  "red_flags": ["specific warning sign 1", "specific warning sign 2", "specific warning sign 3"],
  "reasoning": "2-3 sentence clinical summary",
  "disclaimer": "For clinical decision support only. Apply professional judgment."
}}"""


def synthesis_pass(
    symptoms: str,
    age_group: str,
    duration: str,
    setting: str,
    context: str,
    reasoning: str,
) -> str:
    """
    STEP 3: Structured synthesis using reasoning as assistant context.

    The reasoning from Step 2 is injected as the assistant's prior turn.
    This means Gemma commits to a JSON conclusion consistent with its own
    deliberation — not a fresh generation that might contradict the reasoning.

    Sources are NOT requested here — they are always injected from Python
    chunk metadata to prevent hallucinated citations.
    """
    logger.info("[STEP 3] Starting structured synthesis pass")

    reasoning_prompt = REASONING_PROMPT.format(
        age_group=age_group,
        symptoms=symptoms,
        duration=duration,
        setting=setting,
        context=context,
    )

    synthesis_prompt = SYNTHESIS_PROMPT.format(
        age_group=age_group,
        symptoms=symptoms,
        duration=duration,
        setting=setting,
    )

    # Key pattern from reference implementation:
    # Pass reasoning back as assistant turn — Gemma builds on its own thinking
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": reasoning_prompt},
            {"role": "assistant", "content": reasoning},   # Step 2 output as context
            {"role": "user",      "content": synthesis_prompt},
        ],
        options={
            "temperature": 0.1,
            "num_predict": MAX_TOKENS_SYNTH,
        },
    )

    raw = response["message"]["content"]
    logger.info(f"[STEP 3] Synthesis complete ({len(raw)} chars)")
    return raw


# =============================================================================
# STEP 4 — VALIDATION & SELF-CORRECTION
# =============================================================================

REQUIRED_KEYS = {
    "triage", "diagnoses", "tests", "treatments",
    "red_flags", "reasoning",
}

CORRECTION_PROMPT = """Your previous response had an error: {error}

Return ONLY valid JSON with these exact keys:
- triage: object with level (URGENT/MODERATE/LOW), label, reason
- diagnoses: list with name, confidence (0.0-1.0), icd10, reasoning
- tests: list with name, priority, rationale
- treatments: list with step, action, notes
- red_flags: list of strings
- reasoning: string (2-3 sentences)
- disclaimer: string

No explanations. No markdown. Valid JSON only."""


def _clean_json(raw: str) -> str:
    """Strip markdown fences that models occasionally wrap around JSON."""
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                return part
    return raw


def _extract_json(raw: str) -> dict:
    cleaned = _clean_json(raw)
    start   = cleaned.find("{")
    end     = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found:\n{cleaned[:200]}")
    return json.loads(cleaned[start:end])


def _normalise(result: dict) -> dict:
    """Normalise confidence scores from 0-100 integers to 0.0-1.0 decimals."""
    for dx in result.get("diagnoses", []):
        c = dx.get("confidence", 0)
        if isinstance(c, (int, float)) and c > 1:
            dx["confidence"] = round(c / 100, 2)
    return result


def validate_and_correct(raw: str) -> dict:
    """
    STEP 4: Schema validation with automatic self-correction.

    On failure, the exact error is passed back to Gemma with a correction
    prompt — leveraging the model to fix its own malformed output.
    Max 2 retries before surfacing the error.
    """
    logger.info("[STEP 4] Validating schema")
    current = raw

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            # Try normal parse, then salvage if truncated
            try:
                result = _extract_json(current)
            except (ValueError, json.JSONDecodeError):
                salvaged = current[:current.rfind(",")] + "]}}"
                result   = _extract_json(salvaged)
                logger.warning("[STEP 4] Used salvaged partial JSON")

            result  = _normalise(result)
            missing = [k for k in REQUIRED_KEYS if k not in result]
            if missing:
                raise ValueError(f"Missing required fields: {missing}")

            logger.info(f"[STEP 4] Validation passed on attempt {attempt}")
            return result

        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"[STEP 4] Attempt {attempt} failed: {e}")

            if attempt <= MAX_RETRIES:
                logger.info(f"[STEP 4] Requesting self-correction ({attempt}/{MAX_RETRIES})")
                fix_response = ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[
                        {
                            "role":    "user",
                            "content": CORRECTION_PROMPT.format(error=str(e)),
                        },
                        {
                            "role":    "assistant",
                            "content": current,  # pass broken output for context
                        },
                        {
                            "role":    "user",
                            "content": "Fix the JSON now. Return only valid JSON.",
                        },
                    ],
                    options={"temperature": 0.0, "num_predict": MAX_TOKENS_SYNTH},
                )
                current = fix_response["message"]["content"]

    raise ValueError(f"Validation failed after {MAX_RETRIES} retries")


# =============================================================================
# MAIN ENGINE
# =============================================================================

def analyse_symptoms(
    symptoms:  str,
    age_group: str = "Adult (18+)",
    duration:  str = "1-3 days",
    setting:   str = "Outpatient",
) -> dict:
    """
    Full Clinical Intelligence Pipeline:
    Retrieval → Reasoning → Synthesis (with reasoning as context) → Validation
    """
    t0       = time.perf_counter()
    symptoms = symptoms.strip()

    if not symptoms:
        return {"error": "No symptoms provided."}
    if collection_is_empty():
        return _empty_kb_response()

    try:
        # Step 1: Contextual Retrieval
        chunks  = retrieve_chunks(symptoms, age_group, duration)
        context = _build_context(chunks)

        # Step 2: Reasoning Pass
        reasoning = reasoning_pass(symptoms, age_group, duration, setting, context)

        # Step 3: Structured Synthesis (reasoning injected as assistant turn)
        raw = synthesis_pass(symptoms, age_group, duration, setting, context, reasoning)

        # Step 4: Validate and self-correct
        result = validate_and_correct(raw)

    except Exception as e:
        logger.error(f"Engine error: {e}", exc_info=True)
        return {"error": f"Engine error: {str(e)}"}

    # Always inject real sources from chunk metadata — never LLM-generated
    result["sources"] = _extract_sources(chunks)

    result["_meta"] = {
        "chunks_retrieved":   len(chunks),
        "top_chunk_distance": chunks[0]["distance"] if chunks else None,
        "model":              OLLAMA_MODEL,
        "latency_s":          round(time.perf_counter() - t0, 2),
        "pipeline":           "retrieve → reason → synthesise (assistant turn) → validate",
    }

    logger.info(
        f"Pipeline complete | {result['_meta']['latency_s']}s | "
        f"triage={result.get('triage',{}).get('level')} | "
        f"top_dx={result.get('diagnoses',[{}])[0].get('name','none') if result.get('diagnoses') else 'none'}"
    )
    return result


# =============================================================================
# DRUG REFERENCE
# =============================================================================

def query_drug(drug_or_condition: str) -> dict:
    """Drug reference lookup — single-pass."""
    if not drug_or_condition.strip():
        return {"error": "No drug or condition specified."}
    if collection_is_empty():
        return _empty_kb_response()

    chunks  = db_query(f"drug dosage treatment {drug_or_condition}", top_k=4)
    context = _build_context(chunks)

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": DRUG_REFERENCE_PROMPT.format(
                    query=drug_or_condition, context=context
                )},
            ],
            options={"temperature": 0.1, "num_predict": 2000},
        )
        return _extract_json(response["message"]["content"])
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# UTILITIES
# =============================================================================

def _empty_kb_response() -> dict:
    return {
        "triage":     {"level":"MODERATE","label":"Knowledge base not loaded",
                       "reason":"No clinical guidelines indexed."},
        "diagnoses":  [], "tests": [], "treatments": [],
        "red_flags":  [], "sources": [],
        "reasoning":  "Run: python knowledge_base.py to index your PDFs.",
        "disclaimer": "For clinical decision support only.",
        "error":      "Knowledge base is empty. Index your PDFs first.",
    }


def check_llm_health() -> dict:
    try:
        models = [m["model"] for m in ollama.list().get("models", [])]
        return {
            "status":           "ok",
            "backend":          "ollama",
            "model":            OLLAMA_MODEL,
            "available_models": models,
            "model_pulled":     any(OLLAMA_MODEL in m for m in models),
            "pipeline":         "retrieve → reason → synthesise (assistant turn) → validate",
        }
    except Exception as e:
        return {"status": "error", "backend": "ollama", "error": str(e)}