import json


def safe_parse(output: str):
    try:
        return json.loads(output)
    except Exception:
        return {}
