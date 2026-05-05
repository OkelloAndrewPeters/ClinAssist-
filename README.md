# ClinAssist Uganda — AI-Powered Clinical Decision Support for the Last Mile

> **Gemma 4 Good Hackathon Submission**
> Track: Health & Sciences · Global Resilience · Ollama Special Technology Track
> Model: **Gemma 4 e2b** running locally via Ollama — no internet required

---

## The Problem

Uganda has **1 doctor for every 25,000 people**.

At a Health Centre III in rural Karamoja or Kasese, a single clinical officer may see 80+ patients a day. They have no specialist to call. No reliable internet. No time. And one wrong decision — a missed malaria diagnosis, a wrong drug dose for a child — can cost a life.

The Uganda Ministry of Health publishes comprehensive clinical guidelines — 1,158 pages of evidence-based protocols covering every condition from malaria to meningitis, maternal emergencies to paediatric fever. But in practice, a busy clinical officer cannot flip through 1,158 pages mid-consultation.

**The knowledge exists. The access doesn't.**

---

## The Solution

**ClinAssist Uganda** is a clinical decision support system that puts Uganda's own national guidelines into the hands of every health worker — in real time, at the point of care, with no internet required.

A clinical officer types a patient's symptoms. ClinAssist runs a 4-step Clinical Intelligence Pipeline and returns:

- **Triage level** — Urgent / Moderate / Low
- **Ranked differential diagnoses** with confidence scores and ICD-10 codes
- **Recommended investigations** with urgency flags (e.g. Malaria RDT — Urgent)
- **Treatment guidance** with age-appropriate dosing for all 5 patient groups
- **Red flags** to watch for
- **Source citations** — exact chapter and page from the Uganda Clinical Guidelines

Every answer is grounded in Uganda's own national protocols. Not generic internet data. Not hallucinated drug doses. The actual UCG 2023.

---

## Why This Qualifies for Gemma 4 Good

| Criterion | How ClinAssist Delivers |
|---|---|
| **Real-world impact** | Addresses Uganda's 1:25,000 doctor-patient ratio directly |
| **Edge / offline deployment** | Runs entirely on a standard laptop — no internet after setup |
| **Gemma 4 e2b via Ollama** | Edge-optimised model, runs on CPU, zero cloud cost |
| **Grounded, safe AI** | Every output cites the exact guideline chapter and page |
| **Scalable** | Same architecture works for any country's clinical guidelines |
| **Patient continuity** | Stores full visit history — returning patients get better analysis |

---

## Architecture

```
Patient symptoms + context
        │
        ▼
┌─────────────────────────────────────────┐
│  Django Web Application                 │
│  - Role-based auth (doctor / admin)     │
│  - Patient registry (auto-generated ID) │
│  - Visit & diagnosis history            │
│  - PDF report generation (ReportLab)    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Clinical Intelligence Engine           │
│                                         │
│  STEP 1: Contextual Retrieval (RAG)     │
│  - Age-aware query expansion            │
│  - ChromaDB vector search               │
│  - Chunk scoring & filtering            │
│                                         │
│  STEP 2: Deliberate Reasoning Pass      │
│  - Gemma 4 e2b thinks freely            │
│  - Evaluates symptoms vs evidence       │
│  - Identifies signals & uncertainties   │
│                                         │
│  STEP 3: Structured Synthesis Pass      │
│  - Enforced JSON schema                 │
│  - Triage, diagnoses, tests, treatments │
│  - Source citations attached            │
│                                         │
│  STEP 4: Validation & Self-Correction   │
│  - Schema validation layer              │
│  - Auto-retry on failure (up to 2x)     │
│  - Confidence normalisation             │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Gemma 4 e2b via Ollama (local, CPU)    │
│  Two inference calls per query:         │
│  1. Free-text clinical reasoning        │
│  2. Structured JSON synthesis           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  SQLite Database                        │
│  - Every visit stored permanently       │
│  - Patient history injected into        │
│    next analysis automatically          │
│  - Full audit trail: AI vs confirmed    │
└─────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| LLM | **Gemma 4 e2b** via Ollama (local, CPU-optimised) |
| Vector DB | ChromaDB (persistent, fully local) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| PDF extraction | PyMuPDF |
| Web framework | Django 6 |
| Database | SQLite (zero-config, offline-ready) |
| PDF reports | ReportLab |
| Knowledge base | Uganda Clinical Guidelines 2023 (MOH) |

---

## The 4-Step Clinical Intelligence Pipeline

This is the core technical innovation. Most RAG systems make a single LLM call — retrieve chunks, build prompt, get response. ClinAssist uses a deliberate two-pass architecture that significantly improves output quality and reliability.

### Step 1: Contextual Retrieval

Standard RAG retrieves by semantic similarity alone. ClinAssist builds an **age-aware query** — the retrieval prompt is dynamically constructed based on the patient's age group (adult, elderly, pregnant, child 5–17, under 5). Retrieved chunks are then scored: chunks matching the patient's age context score higher, irrelevant chunks (e.g. paediatric doses for an adult) are demoted.

The chunking pipeline also uses **carry-forward chapter detection** — each chunk inherits the chapter heading of the section it belongs to, making retrieval chapter-aware without hardcoding any document structure.

```python
# Adult query steers toward adult treatment sections
query_text = f"Uganda clinical guidelines adult outpatient treatment {symptoms}"

# Under-5 steers toward IMCI / paediatric chapters
query_text = f"Uganda clinical guidelines child under five paediatric IMCI {symptoms}"
```

### Step 2: Deliberate Reasoning Pass

Instead of going straight to JSON, Gemma 4 e2b first produces **free-text clinical reasoning** with no format constraints. It thinks through the case like a senior clinical officer — what are the likely diagnoses, what supports or argues against each, what is the urgency, what are the red flags.

This reasoning scratchpad is then passed to Step 3 as additional context. The model has already worked out the answer before it tries to format it — dramatically reducing hallucinations and improving diagnostic accuracy.

```
Reasoning prompt output (example):
"The symptom cluster of fever, chills, and joint pain in an adult 
presenting within 1–3 days is consistent with Plasmodium falciparum 
malaria as described in Source 2 (UCG Ch04, p.187). The absence of 
neck stiffness argues against meningitis. Urgency is HIGH given the 
potential for rapid deterioration..."
```

### Step 3: Structured Synthesis Pass

Gemma 4 e2b makes a second inference call, this time converting the reasoning into an **enforced JSON schema**. The schema is strict — triage level, ranked diagnoses with ICD-10 codes and decimal confidence scores (0.0–1.0), investigations with urgency flags, treatments with age-appropriate dosing, red flags, and source citations.

Having the reasoning available means the model synthesises from its own thinking, not from the raw chunks alone.

### Step 4: Validation & Self-Correction

The JSON output is validated against the required schema. If any field is missing or the JSON is malformed (e.g. truncated), the engine automatically sends the broken output back to Gemma with a correction prompt — up to 2 retries before surfacing an error. Confidence scores are normalised (0–100 integers converted to 0.0–1.0 decimals automatically).

This means the system never silently returns broken data to the clinical interface.

---

## Key Technical Innovations

### Age-Aware Retrieval
5 distinct retrieval profiles — Adult, Elderly, Pregnant, Child 5–17, Under 5. Each profile has its own query expansion, keep-words (chunks to promote), and filter-words (chunks to demote). A paediatric dose can never appear in an adult assessment because the retrieval layer filters it before the LLM ever sees it.

### Patient History Injection
When a returning patient is seen, their full history — previous visits, AI suggestions, confirmed diagnoses, known conditions, allergies, current medications — is automatically injected into the prompt context. The LLM reasons over both the guideline evidence and the patient's clinical history simultaneously.

### Self-Describing Knowledge Base
The PDF chunking pipeline detects chapter headings from the document's own text and carries them forward across pages. Adding any new PDF — WHO protocols, IMCI guidelines, Essential Medicines List — requires no code changes. One command: `python knowledge_base.py --file new_guideline.pdf`.

### Source Grounding
Every recommendation cites the document name, chapter, and page number from the Uganda Clinical Guidelines. Doctors can open the physical guideline and verify any recommendation in seconds. This is the trust layer that makes clinicians actually adopt the tool.

### Fully Offline Operation
After a one-time setup, the entire system runs with zero internet connectivity. ChromaDB stores vectors locally. Ollama runs Gemma 4 e2b locally. Django serves locally over the facility's WiFi. Designed for the 3,000+ Health Centre IIs and IIIs across Uganda with no reliable connectivity.

---

## Clinical Features

### Patient Registry
- Auto-generated patient IDs (`CA-2026-00001`)
- Search by name, ID, phone, or village
- Medical background: known conditions, allergies, current medications, next of kin
- Role-based access: doctors see only their own patients; admin sees all

### Symptom Analysis
- Free-text symptom entry in plain language
- Age group, duration, and facility setting selectors
- 4-step pipeline produces grounded, structured clinical assessment
- Doctor annotation layer: confirm final diagnosis, add clinical notes

### Visit History & Continuity
- Every visit stored permanently with full AI output
- Returning patient's complete history feeds automatically into next analysis
- Full audit trail of AI suggestions vs. doctor-confirmed diagnoses

### PDF Reports
- Doctor selects any date range
- System generates formatted PDF: patient list, triage levels, AI diagnoses, confirmed outcomes
- Summary stats: total visits, unique patients, urgent cases

---

## Real-World Deployment Model

```
Health Centre III (no internet)
├── 1 laptop — 8GB RAM, standard CPU
├── Gemma 4 e2b running via Ollama (local)
├── Django server on facility WiFi
└── Clinical officers connect from tablets/phones
    (browser only — no app install needed)

Zero internet required after initial setup.
Cost of AI inference: $0/month.
Cost to deploy: cost of one laptop.
```

This is the deployment model for the 3,000+ Health Centre IIs and IIIs across Uganda that have no specialist, no connectivity, and no budget for cloud AI services.

---

## Impact Potential

**Immediate:**
- Any health facility in Uganda can deploy this today on a standard laptop
- Knowledge base built on freely available MOH publications
- Zero per-query cost — no API fees, no subscriptions, no cloud dependency

**Scale:**
- Same architecture replicates for any country's national clinical guidelines
- Kenya, Tanzania, Rwanda, Ethiopia — each has equivalent MOH protocols
- Codebase is open source and documented for replication by other developers

**Validation path:**
- Pilot with 3–5 Health Centre IIIs in Uganda
- Collect clinical officer feedback on diagnosis accuracy and usability
- Partner with Makerere University School of Medicine for formal validation
- Submit for MOH Uganda digital health registry

---

## Limitations & Honest Caveats

- **Not a replacement for clinical judgment.** Every screen includes the disclaimer. The tool supports decisions — it does not make them.
- **Response time.** The 2-pass pipeline on a standard CPU takes 2–4 minutes per query. Acceptable for a consultation context; Gemma 4 on GPU brings this under 30 seconds.
- **English only (current).** Uganda's clinical guidelines are in English. Luganda and Swahili support is the next priority.
- **Single knowledge base.** Currently indexed on UCG 2023 only. IMCI, Essential Medicines List, and WHO protocols are queued for ingestion.
- **Retrieval edge cases.** Occasional off-target chunk retrieval for rare conditions. Improving with additional PDFs and fine-tuned embeddings.

---

## Setup & Installation

### Requirements
- Python 3.11+
- [Ollama](https://ollama.ai) installed
- 8GB RAM recommended (4GB minimum with Gemma 4 e2b)

### Install
```bash
git clone https://github.com/YOUR_USERNAME/clinassist-uganda
cd clinassist-uganda/core
pip install -r requirements.txt
```

### Pull Gemma 4
```bash
ollama pull gemma4:e2b      # edge-optimised, runs on CPU
```

### Index Knowledge Base
```bash
mkdir knowledge_base_docs
# Copy Uganda Clinical Guidelines 2023 PDF into knowledge_base_docs/
cd ai
python knowledge_base.py
python knowledge_base.py --stats
cd ..
```

### Run
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# Open http://localhost:8000
```

---

## File Structure

```
clinassist-uganda/
└── core/
    ├── manage.py
    ├── core/                   Django settings & URLs
    ├── accounts/               Auth — login, register, roles (doctor/admin)
    ├── patients/               Patient registry, search, history
    ├── diagnoses/              Visit recording & AI analysis
    ├── reports/                PDF report generation
    ├── ai/
    │   ├── engine.py           4-step Clinical Intelligence Pipeline
    │   ├── database.py         ChromaDB vector store operations
    │   ├── knowledge_base.py   PDF ingestion & chunking pipeline
    │   └── prompts.py          LLM system prompts
    ├── templates/              HTML UI (9 templates)
    ├── knowledge_base_docs/    Place PDFs here
    └── chroma_db/              Auto-created local vector store
```

---

## Why Gemma 4 e2b Specifically

Gemma 4 e2b is the right model for this deployment context for three reasons:

1. **Edge-optimised for CPU.** Designed to run on resource-constrained hardware — exactly the standard laptops that exist at Uganda's health centres. No GPU required.
2. **Follows structured instructions.** Gemma 4 reliably produces valid JSON when given a strict schema prompt, enabling the structured synthesis pass that makes clinical outputs consistent and machine-readable.
3. **Open weights via Ollama.** No API key. No internet. No per-query cost. The model runs identically whether the laptop is in Kampala or Kotido with no connectivity.
4. **Can be fine-tuned.** Future versions can be fine-tuned on Uganda-specific clinical cases using Unsloth — something impossible with closed models. This is the path to dramatically improved local accuracy.

---

## The Vision

Every Health Centre III in Uganda. Every clinical officer. Every patient — whether they are in Kampala or Kotido — getting the same quality of clinical guidance, grounded in the same national protocols, supported by a 4-step reasoning pipeline that thinks before it answers.

ClinAssist is not a research prototype. It is running today, on a standard laptop, in Uganda.

---

*Built for the Gemma 4 Good Hackathon — Health & Sciences / Global Resilience / Ollama Special Technology tracks.*
*Knowledge base: Uganda Clinical Guidelines 2023, Ministry of Health Uganda.*
*For clinical decision support only. Always apply professional judgment.*
