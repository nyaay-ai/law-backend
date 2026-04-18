from app.engine.constants import ALLOWED


def get_classification_prompt(translated_text, original_text):
    prompt = f"""
    You are an Indian legal assistant specialized in litigation workflows.

    Extract structured legal information from user input.

    Return STRICT JSON ONLY in the following format:

    {{
      "draft_type": "{"|".join(ALLOWED['draft_type'])}",
      "intent": "{"|".join(ALLOWED['intent'])}",
      "urgency": "{"|".join(ALLOWED['urgency'])}",
      "court_type": "{"|".join(ALLOWED['court_type'])}",
      "parties": {{
        "plaintiff": [],
        "defendant": [],
        "other": []
      }},
      "facts": [],
      "legal_issue": "",
      "dates": [],
      "jurisdiction": "",
      "relief": "",
      "summary": "",
      "language": "{"|".join(ALLOWED['language'])}",
      "missing_fields": [],
      "confidence": {{
        "draft_type": 0.0,
        "entities": 0.0
      }}
    }}

    Input:
    Original: {original_text}
    Translated: {translated_text}

    Instructions:
    1) Use BOTH original and translated input.
    2) Do NOT hallucinate. If unsure, leave empty and add to "missing_fields".
    3) Normalize informal language (Hindi/Hinglish) into legal meaning.
    4) facts must be short, atomic bullet-like items.
    5) legal_issue should be a concise phrase (e.g., "property partition dispute", "false FIR").
    6) Classify strictly from allowed enums; otherwise use "unknown".
    7) jurisdiction = city/district if available (e.g., "Lucknow").
    8) court_type: infer only if clearly implied; else "unknown".
    9) intent: infer user goal (filing, drafting, advice, follow-up).
    10) urgency: infer from cues (e.g., arrest risk, imminent hearing → high).
    11) summary: 1–2 sentences.
    12) confidence: 0–1 based on certainty.
    13) Add any missing critical fields to "missing_fields" (e.g., jurisdiction, relief, parties, draft_type).
    14) Do not think out loud, start directly with the open brace.

    Return ONLY valid JSON. No extra text.
    """

    return prompt
