from app.engine.constants import ALLOWED


def get_classification_prompt(translated_text, original_text):
    prompt = f"""
      You are an Indian legal assistant specialized in litigation workflows.

      Extract structured legal information from user input.

      Return STRICT JSON ONLY in the following format:

      {{
        "draft_type": "{"|".join(ALLOWED["draft_type"])}",
        "intent": "{"|".join(ALLOWED["intent"])}",
        "urgency": "{"|".join(ALLOWED["urgency"])}",
        "court_type": "{"|".join(ALLOWED["court_type"])}",
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
        "language": "{"|".join(ALLOWED["language"])}",
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
      2) Do NOT hallucinate. If unsure, leave the field empty/null and add its key to "missing_fields".
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
      13) missing_fields RULES — add a field's key to "missing_fields" if ANY of the following is true:
          - A string field is "" or "unknown"
          - A list field is []
          - A nested object has all-empty lists (parties)
          - You could not confidently infer the value from the input
          Apply this check to every key: draft_type, intent, urgency, court_type,
          parties, facts, legal_issue, dates, jurisdiction, relief, summary.
      14) Do not think out loud, start directly with the open brace.

      Return ONLY valid JSON. No extra text.
    """

    return prompt


def get_process_missing_fields_prompt(data):
    prompt = f"""
    You are an Indian legal assistant specialized in litigation workflows.

    We have previously extracted structured legal information from user input, but some critical fields were missing.
    We have the data for it now. Can you update the missing fields based on the new data and return the updated JSON?

    Missing fields answers:
    {data.get("missing_fields_answers")}

    Old JSON with missing fields:
    {data.get("old_json")}

    Instructions:
    1) Provide accurate information for each missing field.
    2) Do NOT hallucinate. If unsure, use "unknown".
    3) Normalize informal language (Hindi/Hinglish) into legal meaning.
    4) Return STRICT JSON ONLY in the following format:
    5) Do not update anything else other than the missing fields.

    The ouput should be only in the below format. Do not deviate from it. Do not add any extra text. Do not update any fields other than the missing ones. If you are not sure about a field, set it to "unknown".
    We have given you all the answers and you have to fill in the missing fields in the JSON based on those answers. The rest of the JSON should remain exactly the same as before.
    Do not include any backticks, markdown, or explanations. Return ONLY valid JSON.
    {{
      "draft_type": "{"|".join(ALLOWED["draft_type"])}",
      "intent": "{"|".join(ALLOWED["intent"])}",
      "urgency": "{"|".join(ALLOWED["urgency"])}",
      "court_type": "{"|".join(ALLOWED["court_type"])}",
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
      "language": "{"|".join(ALLOWED["language"])}",
      "missing_fields": [],
      "confidence": {{
        "draft_type": 0.0,
        "entities": 0.0
      }}
    }}
    Return ONLY valid JSON. No extra text.
    """

    return prompt
