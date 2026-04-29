"""
Registry of all documents that must be generated per draft type.
Each entry is what the LLM prompt must produce in one shot.
"""

from app.engine.constants import DraftType

DRAFT_DOCUMENTS: dict[DraftType, list[dict]] = {
    DraftType.WRIT_PETITION: [
        {
            "key": "writ_petition",
            "title": "Writ Petition",
            "description": "Main petition under Article 226/227 with synopsis, list of dates, facts, grounds, prayers, and verification.",
            "mandatory": True,
        },
        {
            "key": "affidavit_in_support",
            "title": "Affidavit in Support",
            "description": "Sworn affidavit by the petitioner verifying the facts stated in the writ petition.",
            "mandatory": True,
        },
        {
            "key": "vakalatnama",
            "title": "Vakalatnama",
            "description": "Authority letter from petitioner authorising the advocate to appear and act.",
            "mandatory": True,
        },
        {
            "key": "index_of_papers",
            "title": "Index of Papers",
            "description": "Numbered index listing all documents filed with the writ petition.",
            "mandatory": True,
        },
        {
            "key": "urgent_application",
            "title": "Application for Urgent Listing",
            "description": "Short application requesting urgent/out-of-turn listing with reasons.",
            "mandatory": False,
        },
        {
            "key": "interim_relief_application",
            "title": "Application for Interim Relief / Stay",
            "description": "Separate application praying for ad-interim stay or interim injunction pending final hearing.",
            "mandatory": False,
        },
    ],
    DraftType.CIVIL_SUIT: [
        {
            "key": "plaint",
            "title": "Plaint",
            "description": "Main plaint under Order VII Rule 1 CPC with full parties, jurisdictional facts, cause of action, and prayer.",
            "mandatory": True,
        },
        {
            "key": "vakalatnama",
            "title": "Vakalatnama",
            "description": "Authority letter from plaintiff authorising the advocate.",
            "mandatory": True,
        },
        {
            "key": "affidavit_verification",
            "title": "Affidavit of Verification",
            "description": "Verification affidavit to accompany the plaint.",
            "mandatory": True,
        },
        {
            "key": "index_of_papers",
            "title": "Index of Papers / Documents Relied Upon",
            "description": "List of all documents filed with the plaint.",
            "mandatory": True,
        },
        {
            "key": "application_for_injunction",
            "title": "Application for Temporary Injunction (Order 39 R 1&2 CPC)",
            "description": "Application for ad-interim / temporary injunction if relief requires it.",
            "mandatory": False,
        },
    ],
    DraftType.CRIMINAL_COMPLAINT: [
        {
            "key": "complaint",
            "title": "Criminal Complaint / FIR Narrative",
            "description": "Formal complaint under Section 223 BNSS 2023 with facts, offences alleged, and prayer to register FIR.",
            "mandatory": True,
        },
        {
            "key": "affidavit_in_support",
            "title": "Affidavit in Support",
            "description": "Sworn affidavit by the complainant verifying the complaint.",
            "mandatory": True,
        },
        {
            "key": "vakalatnama",
            "title": "Vakalatnama",
            "description": "Authority letter authorising the advocate.",
            "mandatory": True,
        },
        {
            "key": "list_of_witnesses",
            "title": "List of Witnesses",
            "description": "Names and addresses of witnesses to be examined.",
            "mandatory": False,
        },
        {
            "key": "list_of_documents",
            "title": "List of Documents",
            "description": "Documents relied upon to substantiate the complaint.",
            "mandatory": False,
        },
    ],
    DraftType.BAIL_APPLICATION: [
        {
            "key": "bail_application",
            "title": "Bail Application",
            "description": "Application for bail under Section 483 BNSS 2023 with grounds, personal details, and sureties proposed.",
            "mandatory": True,
        },
        {
            "key": "affidavit_in_support",
            "title": "Affidavit in Support",
            "description": "Affidavit by the applicant or surety supporting the bail application.",
            "mandatory": True,
        },
        {
            "key": "vakalatnama",
            "title": "Vakalatnama",
            "description": "Authority letter authorising the advocate.",
            "mandatory": True,
        },
        {
            "key": "surety_affidavit",
            "title": "Surety Affidavit",
            "description": "Affidavit by the proposed surety with details of property/assets offered as security.",
            "mandatory": False,
        },
    ],
    DraftType.LEGAL_NOTICE: [
        {
            "key": "legal_notice",
            "title": "Legal Notice",
            "description": "Formal legal notice from advocate with facts, demand, deadline, and consequence clause.",
            "mandatory": True,
        },
        {
            "key": "covering_letter",
            "title": "Covering Letter for Registered Post",
            "description": "Short covering letter addressed to the postmaster / recipient for registered AD dispatch.",
            "mandatory": False,
        },
        {
            "key": "acknowledgement_record",
            "title": "Record of Notice (Office Copy)",
            "description": "Office copy / file copy of the notice with dispatch details.",
            "mandatory": False,
        },
    ],
}


def get_documents_for_draft(draft_type: DraftType) -> list[dict]:
    return DRAFT_DOCUMENTS.get(draft_type, [])


def get_mandatory_documents(draft_type: DraftType) -> list[dict]:
    return [d for d in get_documents_for_draft(draft_type) if d["mandatory"]]


def get_document_titles(draft_type: DraftType) -> list[str]:
    return [d["title"] for d in get_documents_for_draft(draft_type)]
