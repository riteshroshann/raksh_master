# raksh

clinical document ingestion backend. takes medical documents (lab reports, prescriptions, discharge summaries, imaging), extracts structured data using a vision language model, and stores it in a typed schema with full audit trail.

built for indian healthcare. hipaa and dpdp act 2023 compliant.

![Coming Soon](assets/Coming%20soon....png)

## quickstart

```bash
git clone https://github.com/riteshroshann/raksh_master.git
cd raksh_master
cp .env.example .env
# fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY
cd services/ingestion
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn main:app --reload --port 8001
```

or with docker:

```bash
docker compose -f docker-compose.dev.yml up --build
```

## what it does

1. **ingestion** — upload a pdf/image, it gets classified (lab report, prescription, etc.) and extracted into structured json using claude sonnet as a vlm. tesseract 5 as fallback.

2. **phi de-identification** — all extractions pass through presidio + regex before anything is stored. aadhaar, pan, abha, phone, email — redacted before persistence.

3. **confidence scoring** — each extracted field gets a signal-derived confidence score (0.50-0.98) based on field completeness, numeric parseability, unit presence, reference ranges. low-confidence fields get routed to a human review queue.

4. **clinical intelligence** — on confirmation, parameters are enriched with indian population reference ranges, interpreted through disease-specific protocols (diabetes staging, ckd staging, cardiac markers, etc.), and checked for drug interactions if it's a prescription.

5. **interop** — fhir r4 bundle export, abdm/abha integration, loinc coding for 90+ parameters.

## architecture

```
document in -> phi deid -> classify -> extract (vlm) -> confidence score -> review queue
                                                                              |
                                                            confirm -> enrich ranges -> disease protocols -> store
```

## key files

```
services/ingestion/
  main.py                          # fastapi app
  config.py                        # env-based settings
  routes/ingest.py                 # upload, confirm, chunked upload
  routes/health.py                 # health, metrics, documents, reviews, analysis
  pipeline/
    extractor.py                   # vlm extraction + confidence scoring
    classifier.py                  # document type classification
    clinical_nlp.py                # negation/uncertainty detection (context engine)
    disease_protocols.py           # diabetes/thyroid/ckd/cardiac/anemia/liver interpretation
    phi_deid.py                    # presidio + regex de-identification
    confidence.py                  # field-level confidence thresholds
  services/
    database.py                    # supabase-py typed client
    drug_formulary.py              # 40 drugs, 10 interactions, dose validation
    loinc_mapping.py               # 90+ loinc codes, fhir coding
    reference_ranges.py            # indian population ranges + flagging
    review_queue.py                # human-in-the-loop verification
    fhir_mapper.py                 # fhir r4 bundle generation
    audit.py                       # audit logging
    consent.py                     # dpdp act consent + right to erasure
supabase/migrations/               # 8 migrations
```

## tests

```bash
cd services/ingestion
python -m pytest tests/ -v --tb=short
# 261 tests
```

## api

the service exposes ~30 endpoints. run it and go to `/docs` for the full openapi spec.

the important ones:

```
POST /ingest/upload              # upload a document
POST /ingest/confirm             # confirm extracted parameters
POST /analyze/disease            # disease protocol analysis
POST /analyze/prescription       # prescription safety check
POST /analyze/interactions       # drug-drug interactions
GET  /reviews/pending            # human review queue
GET  /parameters/trend           # parameter trend over time
GET  /fhir/bundle/{id}           # fhir r4 export
```

## releases

- v1.0.0 — disease protocols, loinc, review queue, drug formulary, dev tooling
- v0.2.0 — chunked upload phi fix, signal-derived confidence, drug formulary
- v0.1.0 — phi de-identification, supabase migration, clinical nlp
