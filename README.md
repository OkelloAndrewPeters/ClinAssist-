# ClinAssist Uganda — AI-Powered Clinical Decision Support for the Last Mile

> **Gemma 4 Good Hackathon Submission**
> Track: Health & Sciences · Global Resilience · Ollama Special Technology Track

---

## The Problem

Uganda has **1 doctor for every 25,000 people**.

At a Health Centre III in rural Karamoja or Kasese, a single clinical officer may see 80+ patients a day. They have no specialist to call. No reliable internet. No time. And one wrong decision — a missed malaria diagnosis, a wrong drug dose for a child — can cost a life.

The Uganda Ministry of Health publishes comprehensive clinical guidelines — 1,158 pages of evidence-based protocols covering every condition from malaria to meningitis, maternal emergencies to paediatric fever. But in practice, a busy clinical officer cannot flip through 1,158 pages mid-consultation.

**The knowledge exists. The access doesn't.**

---

## The Solution

**ClinAssist Uganda** is a clinical decision support system that puts Uganda's own national guidelines into the hands of every health worker — in real time, at the point of care, with no internet required.

A clinical officer types a patient's symptoms. In under 60 seconds, ClinAssist returns:

- **Triage level** — Urgent / Moderate / Low
- **Ranked differential diagnoses** with confidence scores
- **Recommended investigations** (e.g. Malaria RDT, CBC)
- **Treatment guidance** with age-appropriate dosing
- **Red flags** to watch for
- **Source citations** — exact chapter and page from the Uganda Clinical Guidelines

Every answer is grounded in Uganda's own national protocols. Not generic internet data. Not hallucinated drug doses. The actual UCG 2023.

---

## Why This Qualifies for Gemma 4 Good

| Criterion | How ClinAssist Delivers |
|---|---|
| **Real-world impact** | Addresses Uganda's 1:25,000 doctor-patient ratio directly |
| **Edge / offline deployment** | Runs entirely on a laptop with no internet after setup |
| **Gemma via Ollama** | Gemma 2B/9B powers all inference locally |
| **Grounded, safe AI** | Every output cites the source guideline — no hallucinated treatments |
| **Scalable** | Same architecture works for any country's clinical guidelines |

---

## Architecture

```
Patient symptoms + context
        │
        ▼
┌─────────────────────────────────────┐
│  Django Web Application             │
│  - Auth (doctor accounts)           │
│  - Patient registry (auto ID)       │
│  - Visit & diagnosis history        │
│  - PDF report generation            │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  RAG Engine (engine.py)             │
│                                     │
│  1. Age-aware semantic query        │
│  2. ChromaDB retrieval              │
│     (Uganda Clinical Guidelines     │
│      chunked into 1,967 segments)   │
│  3. Smart chunk filtering           │
│     (adult / paediatric / pregnant) │
│  4. Structured prompt with          │
│     patient history injection       │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Gemma 2B via Ollama (local)        │
│  Returns structured JSON:           │
│  triage, diagnoses, tests,          │
│  treatments, sources, red_flags     │
└─────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  SQLite Database                    │
│  Stores every visit + diagnosis     │
│  Patient history feeds next visit   │
└─────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| LLM | Gemma 2B / 9B via **Ollama** |
| Vector DB | ChromaDB (persistent, local) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| PDF extraction | PyMuPDF |
| Web framework | Django 6 |
| Database | SQLite (zero-config, offline-ready) |
| PDF reports | ReportLab |
| Knowledge base | Uganda Clinical Guidelines 2023 (MOH) |

---

## Key Technical Innovations

### 1. Age-Aware Retrieval
Standard RAG retrieves chunks by semantic similarity alone. ClinAssist uses **age-group-aware retrieval** — the query is dynamically constructed based on whether the patient is an adult, child under 5, school-age child, elderly, or pregnant woman. Chunk scoring then promotes age-relevant content and demotes irrelevant sections, ensuring a paediatric dose is never given to an adult.

```python
# Adult query steers toward adult treatment sections
query_text = f"Uganda clinical guidelines adult treatment management {symptoms}"

# Under-5 query steers toward IMCI / paediatric chapters
query_text = f"Uganda clinical guidelines child under five paediatric {symptoms}"
```

### 2. Patient History Injection
When a returning patient is seen, their full visit history — previous symptoms, AI suggestions, confirmed diagnoses, known conditions, allergies, current medications — is automatically injected into the prompt context alongside the retrieved guideline chunks. The LLM reasons over both the guidelines and the patient's history simultaneously.

### 3. Structured Clinical Outputs
The LLM is instructed via a strict system prompt to return only valid JSON matching a defined clinical schema. No narrative paragraphs. No markdown. A structured response that maps directly to the UI — triage level, ranked diagnoses with ICD-10 codes, investigations with urgency flags, treatments with dosing steps, and source citations.

### 4. Source Grounding
Every recommendation includes the document name, chapter, and page number from the Uganda Clinical Guidelines. Doctors can verify any output in seconds. This is the trust layer that makes clinicians actually use the tool.

### 5. Fully Offline Operation
After a one-time setup (pull Gemma model, index PDFs), the entire system runs with **zero internet connectivity**. ChromaDB stores vectors locally. Ollama runs Gemma locally. Django serves locally. This is designed for Health Centre IIIs with no reliable connectivity — which is most of Uganda's 3,000+ health facilities.

---

## Knowledge Base

The system is currently indexed on:

- **Uganda Clinical Guidelines 2023** — Ministry of Health Uganda (1,158 pages → 1,967 chunks)

Designed to also ingest:
- Uganda IMCI Guidelines 2022
- Uganda Essential Medicines List
- MOH Treatment Manuals
- WHO Pocket Book of Hospital Care for Children

Adding a new guideline is one command:
```bash
python knowledge_base.py --file new_guideline.pdf
```

---

## Clinical Features

### Patient Registry
- Auto-generated patient IDs (`CA-2026-00142`)
- Search by name, ID, phone, or village
- Medical history: known conditions, allergies, current medications
- Role-based access: each doctor sees only their patients; admin sees all

### Symptom Analysis
- Free-text symptom entry
- Age group, symptom duration, and facility setting selectors
- Results in under 60 seconds on CPU (Gemma 2B)
- Doctor annotation layer: confirm final diagnosis, add clinical notes

### Visit History
- Every visit stored permanently
- Returning patient's history automatically included in next AI analysis
- Full audit trail of AI suggestions vs. doctor-confirmed diagnoses

### PDF Reports
- Doctor selects a date range
- System generates a formatted PDF: patient list, triage levels, diagnoses, confirmed outcomes
- Summary stats: total visits, unique patients, urgent cases

---

## Real-World Deployment Model

```
Health Centre III
├── 1 laptop (4GB RAM minimum)
├── Ollama running Gemma 2B locally
├── Django server on local network
└── Other devices connect via WiFi
    (tablets, phones — no app install needed)

Zero internet required after initial setup.
Cost of AI inference: $0/month.
```

This is the deployment model for the 3,000+ Health Centre IIs and IIIs across Uganda that have no specialist, no connectivity, and no budget for cloud AI.

---

## Impact Potential

**Immediate:**
- Any health facility in Uganda can run this today on a basic laptop
- The knowledge base is built on freely available MOH publications
- Zero per-query cost — no API fees, no cloud dependency

**Scale:**
- Same architecture works for any country's clinical guidelines
- Kenya, Tanzania, Rwanda, Ethiopia — each has equivalent MOH protocols
- The codebase is open source and documented for replication

**Validation path:**
- Pilot with 3–5 Health Centre IIIs in Uganda
- Collect doctor feedback on diagnosis accuracy
- Partner with Makerere University School of Medicine for clinical validation
- Submit for MOH Uganda digital health registry

---

## Limitations & Honest Caveats

- **Not a replacement for clinical judgment.** Every screen includes the disclaimer. The tool supports decisions; it does not make them.
- **Gemma 2B quality.** The 2B model occasionally retrieves slightly off-target chunks. Gemma 9B or 27B significantly improves reasoning quality at the cost of RAM/speed.
- **English only (current).** Uganda's clinical guidelines are in English; Luganda and Swahili support is the next priority.
- **Single knowledge base.** Currently indexed on UCG 2023 only. IMCI, Essential Medicines List, and WHO protocols are queued for ingestion.

---

## Setup & Installation

### Requirements
- Python 3.11+
- [Ollama](https://ollama.ai) installed
- 4GB RAM minimum (8GB recommended for Gemma 9B)

### Install
```bash
git clone https://github.com/YOUR_USERNAME/clinassist-uganda
cd clinassist-uganda/core
pip install -r requirements.txt
```

### Pull Gemma
```bash
ollama pull gemma2:2b       # 1.6 GB — works on 4 GB RAM
# or
ollama pull gemma2:9b       # 5.4 GB — better reasoning quality
```

### Index Knowledge Base
```bash
mkdir knowledge_base_docs
# Copy Uganda Clinical Guidelines PDF into knowledge_base_docs/
cd ai
python knowledge_base.py
python knowledge_base.py --stats
```

### Run
```bash
cd ..
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
    ├── core/               Django settings & URLs
    ├── accounts/           Auth — login, register, roles
    ├── patients/           Patient registry & search
    ├── diagnoses/          Visit recording & AI analysis
    ├── reports/            PDF report generation
    ├── ai/
    │   ├── engine.py       RAG inference pipeline
    │   ├── database.py     ChromaDB operations
    │   ├── knowledge_base.py  PDF ingestion
    │   └── prompts.py      LLM prompt templates
    ├── templates/          HTML UI
    ├── knowledge_base_docs/  Place PDFs here
    └── chroma_db/          Auto-created vector store
```

---

## Why Gemma Specifically

Gemma's open weights and Ollama integration make it uniquely suited for this deployment context:

1. **It runs offline.** No API key. No internet. No per-query cost.
2. **It fits on edge hardware.** Gemma 2B runs on a 4GB laptop — the kind that exists at Uganda's health centres.
3. **It follows structured instructions.** Gemma reliably returns JSON when prompted correctly, enabling the structured clinical output format this system requires.
4. **It can be fine-tuned.** Future versions can be fine-tuned on Uganda-specific clinical cases for dramatically improved local accuracy — something impossible with closed models.

---

## The Vision

Every Health Centre III in Uganda. Every clinical officer. Every patient — whether they are in Kampala or Kotido — getting the same quality of clinical guidance, grounded in the same national protocols, in under 60 seconds.

ClinAssist is not a research prototype. It is running today, on a laptop, in Uganda.

---

*Built for the Gemma 4 Good Hackathon — Health & Sciences / Global Resilience tracks.*
*Knowledge base: Uganda Clinical Guidelines 2023, Ministry of Health Uganda.*
*For clinical decision support only. Always apply professional judgment.*
