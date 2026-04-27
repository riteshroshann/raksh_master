# reference range decisions

this document explains every reference range in the raksh database, its source citation, and where it deviates from western standards. it exists for the medical advisor, not for engineers.

when a doctor questions a flagging decision, the answer should come from this document, not from grep.

## how ranges are selected

the system uses a fallback chain:
1. indian population range (icmr, rssdi, api india) — used first
2. western range — used only when no indian data exists, with an explicit warning log

ranges are versioned with `effective_from`/`effective_to`. no range can be added without a source citation. the `approved_by` field creates a medical advisor approval gate.

## parameters with indian-specific corrections

these parameters deviate from western textbook values. each deviation has a clinical reason.

### hemoglobin

| sex | indian lower | western lower | unit | source |
|-----|-------------|---------------|------|--------|
| male | 13.0 | 13.5 | g/dL | ICMR-NIN 2020 |
| female | 11.5 | 12.0 | g/dL | ICMR-NIN 2020 |
| female (pregnant) | 11.0 | 11.0 | g/dL | ICMR-NIN 2020 |

the 11.5 g/dL lower limit for indian women (vs 12.0 western) is based on the ICMR-NIN Nutrient Requirements 2020, Table 4.1. the correction accounts for lower mean hemoglobin in the indian female population due to dietary iron bioavailability differences. using the western 12.0 threshold over-flags normal indian women.

### tsh

| age | indian upper | western upper | unit | source |
|-----|-------------|---------------|------|--------|
| 18-59 | 5.5 | 4.0-4.5 | mIU/L | API India 2023 |
| 60+ | 6.37 | 4.0-4.5 | mIU/L | API India 2023 |

the API India Thyroid Guidelines 2023 set the indian upper limit at 5.5 mIU/L (not 4.0). the elderly adjustment to 6.37 prevents over-diagnosis of subclinical hypothyroidism in patients over 60, which is a known problem when using western thresholds on indian elderly populations.

### platelets

| population | indian lower | western lower | unit | source |
|------------|-------------|---------------|------|--------|
| adult | 115.6 | 150.0 | 10^3/uL | ICMR 2022 |

the ICMR multicentric study found the 2.5th percentile for indian adults at 115.6 × 10^3/uL, not 150. using the western 150 threshold incorrectly flags ~15% of healthy indian adults as thrombocytopenic.

### hdl cholesterol

| sex | indian lower | western lower | unit | source |
|-----|-------------|---------------|------|--------|
| male | 40 | 40 | mg/dL | ICMR CVD 2023 |
| female | 50 | 50 | mg/dL | ICMR CVD 2023 |

gender-split matches western values here but many indian labs incorrectly use a single 40 mg/dL threshold for both sexes. the system enforces the split.

### creatinine

| sex | indian range | western range | unit | source |
|-----|-------------|---------------|------|--------|
| male | 0.7–1.2 | 0.7–1.3 | mg/dL | ICMR 2022 |
| female | 0.5–0.9 | 0.6–1.1 | mg/dL | ICMR 2022 |

indian women have a lower creatinine baseline. the ICMR correction prevents missing early renal decline in female patients.

### egfr

| population | indian lower | western lower | unit | source |
|------------|-------------|---------------|------|--------|
| adult | 90 | 90 | mL/min/1.73m2 | ICMR 2022 |

same threshold, but the citation specifies CKD-EPI with indian population adaptation coefficients. the western CKD-EPI formula without ethnicity correction overestimates GFR in south asian populations.

## parameters matching western standards

these parameters use the same ranges as western references. the indian citations confirm the same values.

| parameter | range | unit | source |
|-----------|-------|------|--------|
| fasting glucose | 70–100 | mg/dL | RSSDI 2023 |
| postprandial glucose | 70–140 | mg/dL | RSSDI 2023 |
| hba1c | 4.0–5.6 | % | RSSDI 2023 |
| total cholesterol | 0–200 | mg/dL | ICMR CVD 2023 |
| ldl cholesterol | 0–100 | mg/dL | ICMR CVD 2023 |
| triglycerides | 0–150 | mg/dL | ICMR CVD 2023 |
| sodium | 136–145 | mEq/L | ICMR 2022 |
| potassium | 3.5–5.0 | mEq/L | ICMR 2022 |
| chloride | 98–106 | mEq/L | ICMR 2022 |
| calcium | 8.5–10.5 | mg/dL | ICMR 2022 |
| phosphorus | 2.5–4.5 | mg/dL | ICMR 2022 |
| magnesium | 1.7–2.2 | mg/dL | ICMR 2022 |
| sgpt/alt (male) | 7–56 | U/L | ICMR 2022 |
| sgpt/alt (female) | 7–45 | U/L | ICMR 2022 |
| sgot/ast | 8–48 | U/L | ICMR 2022 |
| total bilirubin | 0.1–1.2 | mg/dL | ICMR 2022 |
| albumin | 3.5–5.0 | g/dL | ICMR 2022 |
| total protein | 6.0–8.3 | g/dL | ICMR 2022 |
| vitamin d | 30–100 | ng/mL | ICMR 2022 |
| vitamin b12 | 200–900 | pg/mL | ICMR 2022 |
| pt/inr | 0.8–1.2 | ratio | ICMR 2022 |

## fasting-required parameters

these parameters require confirmed fasting status before the system accepts them. if fasting status is not confirmed, the confirmation route returns 422.

- fasting glucose
- total cholesterol
- ldl cholesterol
- hdl cholesterol (male and female)
- triglycerides
- vldl

## how to modify a range

1. identify the parameter in `supabase/seed.sql`
2. create a new row with updated values, a new `version`, and `effective_from` set to today
3. set `effective_to` on the old row to today
4. fill in `approved_by` with the medical advisor's name
5. update this document with the new values and the clinical reason for the change
6. the trend view (`v_parameter_trend`) will automatically use the correct range for each historical data point based on `effective_from`/`effective_to`

do not delete old range rows. the system needs them to correctly flag historical data points.
