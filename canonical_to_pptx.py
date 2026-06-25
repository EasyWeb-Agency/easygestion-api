import json, re
from pathlib import Path

def strip_md(text):
    if not text: return ""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text.strip()

def convert(canonical):
    return {
        "meta": canonical.get("meta", {}),
        "projet": canonical.get("projet", {}),
        "client": canonical.get("client", {}),
        "emetteur": canonical.get("emetteur", {}),
        "sections": canonical.get("sections", {}),
        "budget_detail": canonical.get("budget_detail", {})
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    canonical = json.loads(Path(args.input).read_text())
    Path(args.output).write_text(json.dumps(convert(canonical), ensure_ascii=False, indent=2))
