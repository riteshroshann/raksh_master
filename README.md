# raksh

clinical document ingestion backend. takes medical documents (lab reports, prescriptions, discharge summaries, imaging), extracts structured data using a vision language model, and stores it in a typed schema with full audit trail.

built for indian healthcare. hipaa and dpdp act 2023 compliant.

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

2. **phi de-identification** — all documents pass through presidio + regex before anything is stored. aadhaar, pan, abha, phone, email — redacted before persistence.

3. **unit normalisation** — indian labs report in mixed units (mmol/L, µmol/L, mg/dL). all values are normalised to conventional units for consistent storage and trend comparison. originals preserved.

4. **confidence scoring** — each extracted field gets a signal-derived confidence score. low-confidence fields get routed to a human review queue. high-risk medications (insulin, warfarin) require 0.99 confidence.

5. **constitutional filter** — output-layer middleware scans all api responses for prohibited diagnostic terms. the system is architecturally incapable of producing diagnostic strings in patient-facing context.

6. **fasting enforcement** — parameters requiring fasting status (lipids, glucose) block save if fasting status is not confirmed. 422 with affected parameter list.

7. **reference range enrichment** — indian population-specific ranges (icmr/api india citations) auto-applied on confirmation. critical/normal flagging.

8. **interop** — fhir r4 bundle export, abdm/abha integration, loinc coding for 90+ parameters.

## architecture

```
document in -> phi deid -> classify -> extract (vlm) -> unit normalise -> confidence score -> review queue
                                                                                                |
                                                                  confirm -> enrich ranges -> fasting check -> store
                                                                                                |
                                                                                    constitutional filter (output)
```

## key files

```
services/ingestion/
  main.py                          # fastapi app
  config.py                        # env-based settings
  routes/ingest.py                 # upload, confirm, chunked upload
  routes/health.py                 # health, metrics, documents, reviews
  pipeline/
    extractor.py                   # vlm extraction + confidence scoring
    classifier.py                  # document type classification
    clinical_nlp.py                # negation/uncertainty detection
    unit_normaliser.py             # mmol/L -> mg/dL, µmol/L -> mg/dL
    phi_deid.py                    # presidio + regex de-identification
    confidence.py                  # field-level confidence thresholds
    validator.py                   # prohibited content filter + field validation
  middleware/
    constitutional_filter.py       # output-layer diagnostic term filter
    auth.py                        # api key authentication
  services/
    database.py                    # supabase-py typed client
    loinc_mapping.py               # 90+ loinc codes, fhir coding
    reference_ranges.py            # indian population ranges + flagging
    review_queue.py                # human-in-the-loop verification
    drug_formulary.py              # 40 drugs, interactions, dose validation
    fhir_mapper.py                 # fhir r4 bundle generation
    audit.py                       # audit logging
    consent.py                     # dpdp act consent + right to erasure
supabase/migrations/               # 8 migrations
```

## tests

```bash
cd services/ingestion
python -m pytest tests/ -v --tb=short
```

## api

the service exposes ~30 endpoints. run it and go to `/docs` for the full openapi spec.

the important ones:

```
POST /ingest/upload              # upload a document
POST /ingest/confirm             # confirm extracted parameters (fasting enforced)
GET  /reviews/pending            # human review queue
POST /reviews/{id}/approve       # approve extraction
POST /reviews/{id}/correct       # correct extraction
GET  /parameters/trend           # parameter trend over time
GET  /reference-ranges/lookup    # indian reference range lookup
GET  /fhir/bundle/{id}           # fhir r4 export
```

## releases

- v1.0.0 — unit normalisation, constitutional filter, fasting enforcement, review queue, loinc
- v0.2.0 — chunked upload phi fix, signal-derived confidence, drug formulary
- v0.1.0 — phi de-identification, supabase migration, clinical nlp
