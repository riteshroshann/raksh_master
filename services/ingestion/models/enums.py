from enum import Enum


class IngestChannel(str, Enum):
    UPLOAD = "upload"
    FOLDER_WATCH = "folder_watch"
    EMAIL = "email"
    FAX = "fax"
    SCANNER = "scanner"
    EMR_EHR = "emr_ehr"
    PACS = "pacs"
    HL7 = "hl7"
    ABDM = "abdm"


class DocumentType(str, Enum):
    LAB_REPORT = "lab_report"
    PRESCRIPTION = "prescription"
    DISCHARGE_SUMMARY = "discharge_summary"
    DOCTOR_NOTES = "doctor_notes"
    PATHOLOGY_REPORT = "pathology_report"
    REFERRAL_LETTER = "referral_letter"
    INSURANCE_BILLING = "insurance_billing"
    RADIOLOGY_REPORT = "radiology_report"
    XRAY = "xray"
    MRI = "mri"
    CT_SCAN = "ct_scan"
    ULTRASOUND = "ultrasound"
    ECG_EEG = "ecg_eeg"
    MAMMOGRAM = "mammogram"
    VACCINATION_RECORD = "vaccination_record"
    SURGICAL_REPORT = "surgical_report"
    PHYSIOTHERAPY_NOTES = "physiotherapy_notes"
    DIETICIAN_PLAN = "dietician_plan"
    MENTAL_HEALTH_ASSESSMENT = "mental_health_assessment"
    DENTAL_RECORD = "dental_record"
    EYE_EXAMINATION = "eye_examination"
    CONSENT_FORM = "consent_form"


class ParameterFlag(str, Enum):
    NORMAL = "normal"
    ABOVE_RANGE = "above_range"
    BELOW_RANGE = "below_range"
    CRITICAL_HIGH = "critical_high"
    CRITICAL_LOW = "critical_low"
    UNCONFIRMED = "unconfirmed"
    BORDERLINE = "borderline"


class FastingStatus(str, Enum):
    FASTING = "fasting"
    NON_FASTING = "non_fasting"
    UNKNOWN = "unknown"


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class ExtractionBackend(str, Enum):
    API = "api"
    LOCAL = "local"
    HYBRID = "hybrid"


class ConsentPurpose(str, Enum):
    DATA_STORAGE = "data_storage"
    DATA_PROCESSING = "data_processing"
    SHARING_WITH_DOCTOR = "sharing_with_doctor"
    ABDM_LINKING = "abdm_linking"
    ANALYTICS = "analytics"
    RESEARCH = "research"


class AuditEvent(str, Enum):
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    EXTRACTION_COMPLETED = "EXTRACTION_COMPLETED"
    DOCUMENT_CONFIRMED = "DOCUMENT_CONFIRMED"
    DUPLICATE_DETECTED = "DUPLICATE_DETECTED"
    CLASSIFICATION_FAILED = "CLASSIFICATION_FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    PATIENT_LINKED = "PATIENT_LINKED"
    UNLINKED_QUEUED = "UNLINKED_QUEUED"
    ABBREVIATION_HAZARD_DETECTED = "ABBREVIATION_HAZARD_DETECTED"
    CORRUPTED_FILE_DETECTED = "CORRUPTED_FILE_DETECTED"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    RIGHT_TO_ERASURE_INITIATED = "RIGHT_TO_ERASURE_INITIATED"
    RIGHT_TO_ERASURE_COMPLETED = "RIGHT_TO_ERASURE_COMPLETED"
    FHIR_BUNDLE_GENERATED = "FHIR_BUNDLE_GENERATED"
    ABDM_CONSENT_REQUESTED = "ABDM_CONSENT_REQUESTED"
    ABDM_DATA_PUSHED = "ABDM_DATA_PUSHED"
    PHI_DETECTED = "PHI_DETECTED"
    DEIDENTIFICATION_COMPLETED = "DEIDENTIFICATION_COMPLETED"


class DicomModality(str, Enum):
    CR = "CR"
    CT = "CT"
    MR = "MR"
    US = "US"
    NM = "NM"
    PT = "PT"
    XA = "XA"
    MG = "MG"
    DX = "DX"
    OT = "OT"


class ImageQuality(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    UNUSABLE = "unusable"


class ProcessingStatus(str, Enum):
    RECEIVED = "received"
    PREPROCESSING = "preprocessing"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    SCORING = "scoring"
    VALIDATING = "validating"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    DUPLICATE = "duplicate"
