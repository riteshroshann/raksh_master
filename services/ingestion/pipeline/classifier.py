import io

import pdfplumber
import structlog
from pypdf import PdfReader

from models.enums import DocumentType

logger = structlog.get_logger()

IMAGING_CONTENT_TYPES = {"application/dicom"}

TEXTUAL_DOCUMENT_TYPES = {
    DocumentType.LAB_REPORT,
    DocumentType.PRESCRIPTION,
    DocumentType.DISCHARGE_SUMMARY,
    DocumentType.DOCTOR_NOTES,
    DocumentType.PATHOLOGY_REPORT,
    DocumentType.REFERRAL_LETTER,
    DocumentType.INSURANCE_BILLING,
}

IMAGING_DOCUMENT_TYPES = {
    DocumentType.XRAY,
    DocumentType.MRI,
    DocumentType.CT_SCAN,
    DocumentType.ULTRASOUND,
    DocumentType.ECG_EEG,
    DocumentType.RADIOLOGY_REPORT,
}

CLASSIFICATION_KEYWORDS = {
    DocumentType.LAB_REPORT: [
        "hemoglobin", "hb", "cbc", "complete blood count", "blood test",
        "pathology", "laboratory", "lab report", "test result", "reference range",
        "wbc", "rbc", "platelet", "hematocrit", "esr", "creatinine",
        "cholesterol", "triglyceride", "glucose", "hba1c", "tsh", "thyroid",
        "liver function", "kidney function", "lipid profile", "urine",
    ],
    DocumentType.PRESCRIPTION: [
        "rx", "prescription", "tab", "tablet", "capsule", "syrup",
        "injection", "mg", "ml", "twice daily", "once daily", "after food",
        "before food", "od", "bd", "tds", "sos", "prn", "dispense",
    ],
    DocumentType.DISCHARGE_SUMMARY: [
        "discharge summary", "discharge", "admitted", "discharged",
        "hospital stay", "final diagnosis", "treatment given",
        "follow up", "discharge medication",
    ],
    DocumentType.DOCTOR_NOTES: [
        "clinical notes", "progress notes", "soap", "chief complaint",
        "history of present illness", "physical examination", "assessment",
        "plan", "consultation", "opd",
    ],
    DocumentType.PATHOLOGY_REPORT: [
        "histopathology", "biopsy", "cytology", "gross examination",
        "microscopic", "immunohistochemistry", "staging", "grading",
        "malignant", "benign", "specimen",
    ],
    DocumentType.REFERRAL_LETTER: [
        "referral", "refer", "referred to", "opinion requested",
        "kindly see", "please evaluate", "specialist opinion",
    ],
    DocumentType.INSURANCE_BILLING: [
        "claim", "insurance", "pre-authorization", "pre-auth",
        "tpa", "policy number", "cashless", "reimbursement",
        "bill", "invoice", "explanation of benefits",
    ],
    DocumentType.RADIOLOGY_REPORT: [
        "radiology", "radiologist", "impression", "findings",
        "x-ray", "ct scan", "mri", "ultrasound", "usg",
    ],
}


def _is_dicom(contents: bytes) -> bool:
    if len(contents) < 132:
        return False
    return contents[128:132] == b"DICM"


def _classify_dicom(contents: bytes) -> DocumentType:
    return DocumentType.XRAY


def _extract_text_from_pdf(contents: bytes) -> str:
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception:
        try:
            reader = PdfReader(io.BytesIO(contents))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        except Exception:
            pass
    return "\n".join(text_parts).lower()


def _classify_by_keywords(text: str) -> DocumentType:
    scores: dict[DocumentType, int] = {}
    for doc_type, keywords in CLASSIFICATION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return DocumentType.LAB_REPORT

    return max(scores, key=scores.get)


async def classify_document(contents: bytes, content_type: str) -> DocumentType:
    logger.info("classification_started", content_type=content_type, size_bytes=len(contents))

    if content_type in IMAGING_CONTENT_TYPES or _is_dicom(contents):
        doc_type = _classify_dicom(contents)
        logger.info("classification_completed", doc_type=doc_type.value, method="dicom_metadata")
        return doc_type

    if content_type == "application/pdf":
        text = _extract_text_from_pdf(contents)
        if text.strip():
            doc_type = _classify_by_keywords(text)
            logger.info("classification_completed", doc_type=doc_type.value, method="keyword_analysis")
            return doc_type

    if content_type in {"image/jpeg", "image/png", "image/heic", "image/tiff"}:
        logger.info("classification_completed", doc_type=DocumentType.PRESCRIPTION.value, method="image_default")
        return DocumentType.PRESCRIPTION

    logger.info("classification_completed", doc_type=DocumentType.LAB_REPORT.value, method="fallback")
    return DocumentType.LAB_REPORT
