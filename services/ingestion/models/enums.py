from enum import Enum


class IngestChannel(str, Enum):
    UPLOAD = "upload"
    EMAIL = "email"
    FOLDER = "folder"
    FAX = "fax"
    SCANNER = "scanner"
    EMR = "emr"
    PACS = "pacs"


class DocumentType(str, Enum):
    LAB_REPORT = "lab_report"
    PRESCRIPTION = "prescription"
    DISCHARGE_SUMMARY = "discharge_summary"
    DOCTOR_NOTES = "doctor_notes"
    PATHOLOGY_REPORT = "pathology_report"
    REFERRAL_LETTER = "referral_letter"
    INSURANCE_BILLING = "insurance_billing"
    XRAY = "xray"
    MRI = "mri"
    CT_SCAN = "ct_scan"
    ULTRASOUND = "ultrasound"
    ECG_EEG = "ecg_eeg"
    RADIOLOGY_REPORT = "radiology_report"


class ParameterFlag(str, Enum):
    NORMAL = "normal"
    ABOVE_RANGE = "above_range"
    BELOW_RANGE = "below_range"
    UNCONFIRMED = "unconfirmed"


class FastingStatus(str, Enum):
    FASTING = "fasting"
    NON_FASTING = "non_fasting"
    UNKNOWN = "unknown"


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    ANY = "any"


class ReferenceSource(str, Enum):
    ICMR = "ICMR"
    RSSDI = "RSSDI"
    IHG = "IHG"
    LAB = "lab"
    WESTERN = "western"


class ExtractionBackend(str, Enum):
    API = "api"
    LOCAL = "local"


class ConsentPurpose(str, Enum):
    HEALTH_RECORD_STORAGE = "health_record_storage"
    DATA_SHARING = "data_sharing"
    ABDM_LINKING = "abdm_linking"
