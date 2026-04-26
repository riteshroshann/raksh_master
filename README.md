# Raksh Clinical Ingestion Backend

![Coming Soon](assets/Coming%20soon....png)

**Enterprise-grade clinical document ingestion, extraction, and intelligence pipeline.**

HIPAA and DPDP Act 2023 compliant. Built for Indian healthcare.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    INGESTION GATEWAY                      │
│  Upload • Chunked Upload • Email • Fax • DICOM/PACS     │
└──────────────┬───────────────────────────────┬────────────┘
               ▼                               ▼
┌──────────────────────┐        ┌──────────────────────────┐
│   PHI De-identification      │  Document Classification  │
│   (Presidio + Regex)         │  (VLM + Keyword)          │
└──────────┬───────────┘        └──────────┬───────────────┘
           ▼                               ▼
┌──────────────────────────────────────────────────────────┐
│                  EXTRACTION ENGINE                        │
│  Claude Sonnet (VLM) → Tesseract 5 (OCR Fallback)       │
│  Signal-Derived Confidence Scoring (0.50–0.98)           │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│                 CLINICAL INTELLIGENCE                     │
│  • Disease Protocol Engine (6 categories)                │
│  • Drug Formulary (40 drugs, 10 interactions)            │
│  • LOINC Mapping (90+ parameters)                        │
│  • Reference Range Enrichment (Indian population)        │
│  • Clinical NLP (sentence-boundary negation)             │
│  • Human Review Queue (low-confidence triage)            │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    PERSISTENCE                            │
│  Supabase (PostgreSQL + RLS) • FHIR R4 • ABDM            │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/riteshroshann/raksh_master.git
cd raksh_master

# Setup
cp .env.example .env
# Fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY

# Install
cd services/ingestion
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Run
uvicorn main:app --reload --port 8001

# Or with Docker
cd ../..
docker compose -f docker-compose.dev.yml up --build
```

## API Endpoints

### Ingestion
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest/upload` | Upload document for extraction |
| `POST` | `/ingest/confirm` | Confirm extracted parameters |
| `POST` | `/ingest/chunked/init` | Start chunked upload |
| `POST` | `/ingest/chunked/part` | Upload chunk |
| `POST` | `/ingest/chunked/complete` | Complete chunked upload |

### Clinical Intelligence
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analyze/disease` | Disease protocol analysis |
| `POST` | `/analyze/prescription` | Prescription safety analysis |
| `POST` | `/analyze/interactions` | Drug-drug interaction check |

### Data Access
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/documents` | List documents for member |
| `GET` | `/documents/{id}/parameters` | Get document parameters |
| `GET` | `/parameters/trend` | Parameter trend over time |
| `GET` | `/reference-ranges/lookup` | Indian reference range lookup |

### Review Queue
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/reviews/pending` | List pending reviews |
| `POST` | `/reviews/{id}/approve` | Approve extraction |
| `POST` | `/reviews/{id}/correct` | Correct extraction |
| `POST` | `/reviews/{id}/reject` | Reject extraction |
| `GET` | `/reviews/stats` | Review queue statistics |

### Compliance
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/consent` | Grant consent |
| `POST` | `/consent/withdraw` | Withdraw consent |
| `POST` | `/erasure` | Right to erasure (DPDP Act) |
| `GET` | `/audit` | Audit log |

### Interoperability
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/fhir/bundle/{id}` | FHIR R4 bundle export |
| `POST` | `/abdm/register` | ABHA ID registration |
| `POST` | `/abdm/consent-request` | ABDM consent request |

## Disease Protocol Engine

Supports clinical interpretation for 6 disease categories:

| Category | Key Parameters | Capabilities |
|----------|---------------|--------------|
| **Diabetes** | HbA1c, FPG, PPG, eGFR | Staging, nephropathy co-monitoring |
| **Thyroid** | TSH, FT4, FT3 | Hyper/hypo classification |
| **CKD** | eGFR, Creatinine, K+ | 5-stage classification |
| **Cardiac** | Troponin, BNP, LDL | AMI detection, HF screening |
| **Anemia** | Hb, Ferritin, MCV | Type classification |
| **Liver** | ALT, AST, Bilirubin | Injury grading, AST:ALT ratio |

## Testing

```bash
cd services/ingestion
python -m pytest tests/ -v --tb=short
```

## Releases

- **v1.0.0** — Disease protocols, drug formulary, LOINC mapping, review queue, dev tooling
- **v0.2.0** — Chunked upload PHI fix, signal-derived confidence, drug formulary
- **v0.1.0** — PHI de-identification, supabase migration, clinical NLP

## License

Proprietary. All rights reserved.
