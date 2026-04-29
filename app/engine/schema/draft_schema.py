"""
draft_schema.py

Pydantic models for the structured JSON output produced by the LLM.
The LLM is instructed to return one of these schemas; we validate here
before handing off to the template engine.

Flow:
  LLM → raw JSON str
      → DraftPackageSchema (Pydantic validation)
      → TemplateEngine (docxtpl)
      → PostProcessor (python-docx)
      → Final .docx bytes
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Shared primitives ─────────────────────────────────────────────────────────


class PartyBlock(BaseModel):
    name: str
    role: str  # "Petitioner" | "Respondent" | "Plaintiff" | "Defendant" etc.
    address: str
    advocate_name: Optional[str] = None
    advocate_address: Optional[str] = None

    @field_validator("name", "role", "address")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Party fields must not be blank")
        return v.strip()


class CourtBlock(BaseModel):
    court_name: str
    bench: Optional[str] = None  # e.g. "Hon'ble High Court of Delhi"
    case_number: Optional[str] = None


class FactParagraph(BaseModel):
    number: int
    text: str  # begins with prefix e.g. "That, ..."

    @field_validator("text")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Fact paragraph text must not be blank")
        return v.strip()


class Ground(BaseModel):
    label: str  # e.g. "A." or "I." or a bold heading
    heading: Optional[str] = None
    text: str


class Prayer(BaseModel):
    serial: str  # "a.", "b.", "i." etc.
    text: str


class VerificationBlock(BaseModel):
    place: str
    date: str
    deponent_name: str
    formula: Optional[str] = None  # override default verification text


class SignatureBlock(BaseModel):
    advocate_name: str
    enrollment_number: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


# ── Per-document schemas ──────────────────────────────────────────────────────


class MainPetitionDoc(BaseModel):
    """
    Covers: Writ Petition, Civil Suit, Criminal Complaint body.
    """

    title: str  # full court-facing title
    court: CourtBlock
    parties: list[PartyBlock]
    facts: list[FactParagraph]
    grounds: list[Ground]
    prayers: list[Prayer]
    legal_sections: list[str] = Field(default_factory=list)
    precedents: list[str] = Field(default_factory=list)
    verification: VerificationBlock
    signature: SignatureBlock

    @field_validator("facts", "grounds", "prayers", "parties")
    @classmethod
    def non_empty_list(cls, v: list) -> list:
        if not v:
            raise ValueError("List must have at least one entry")
        return v

    @model_validator(mode="after")
    def facts_sequential(self) -> "MainPetitionDoc":
        for i, f in enumerate(self.facts, start=1):
            if f.number != i:
                raise ValueError(
                    f"Fact paragraphs must be sequentially numbered. "
                    f"Expected {i}, got {f.number}."
                )
        return self


class AffidavitDoc(BaseModel):
    deponent: PartyBlock
    court: CourtBlock
    statements: list[str]  # numbered statements
    verification: VerificationBlock
    signature: SignatureBlock


class VakalatnaamaDoc(BaseModel):
    client: PartyBlock
    advocate: SignatureBlock
    court: CourtBlock
    case_title: str
    date: str


class InterimApplicationDoc(BaseModel):
    """IA / Stay Application / Injunction Application."""

    title: str
    court: CourtBlock
    parties: list[PartyBlock]
    grounds_for_urgency: list[str]
    prayers: list[Prayer]
    verification: VerificationBlock
    signature: SignatureBlock


class LegalNoticeDoc(BaseModel):
    sender: PartyBlock
    recipient: PartyBlock
    subject: str
    facts: list[FactParagraph]
    demands: list[str]
    deadline_days: int = 15
    date: str
    place: str
    signature: SignatureBlock


class BailApplicationDoc(BaseModel):
    accused: PartyBlock
    court: CourtBlock
    fir_details: dict[
        str, Any
    ]  # {"fir_number": ..., "police_station": ..., "sections": [...]}
    grounds: list[Ground]
    prayers: list[Prayer]
    surety_details: Optional[dict[str, Any]] = None
    verification: VerificationBlock
    signature: SignatureBlock


# ── Top-level package ─────────────────────────────────────────────────────────

_DOC_TYPE = Literal[
    "main_petition",
    "affidavit",
    "vakalatnama",
    "interim_application",
    "legal_notice",
    "bail_application",
]


class DraftPackageSchema(BaseModel):
    """
    Root schema returned by the LLM.
    Contains one entry per document in the draft package.
    The LLM must always populate `draft_type` and at least `main_petition`.
    """

    draft_type: str
    draft_language: Literal["hindi", "english", "hinglish"] = "english"
    case_id: str

    # mandatory documents — at least one must be present
    main_petition: Optional[MainPetitionDoc] = None
    affidavit: Optional[AffidavitDoc] = None
    vakalatnama: Optional[VakalatnaamaDoc] = None
    interim_application: Optional[InterimApplicationDoc] = None
    legal_notice: Optional[LegalNoticeDoc] = None
    bail_application: Optional[BailApplicationDoc] = None

    # metadata written to DB / audit
    documents_generated: list[str] = Field(default_factory=list)
    generation_notes: Optional[str] = None  # LLM may flag caveats here

    @model_validator(mode="after")
    def at_least_one_doc(self) -> "DraftPackageSchema":
        doc_fields = [
            self.main_petition,
            self.affidavit,
            self.vakalatnama,
            self.interim_application,
            self.legal_notice,
            self.bail_application,
        ]
        if not any(d is not None for d in doc_fields):
            raise ValueError(
                "DraftPackageSchema must contain at least one populated document."
            )
        return self

    def populated_documents(self) -> dict[str, Any]:
        """Returns {field_name: model} for every non-None document."""
        mapping = {
            "main_petition": self.main_petition,
            "affidavit": self.affidavit,
            "vakalatnama": self.vakalatnama,
            "interim_application": self.interim_application,
            "legal_notice": self.legal_notice,
            "bail_application": self.bail_application,
        }
        return {k: v for k, v in mapping.items() if v is not None}
