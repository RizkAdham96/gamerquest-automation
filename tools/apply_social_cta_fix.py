from pathlib import Path

path = Path(__file__).resolve().parents[1] / "social" / "render.py"
text = path.read_text(encoding="utf-8")

needle = '''    r"\\s*Découvrir la suite "\n    r"sur GamerQuest(?:\\.fr|fr)?\\.?",\n)'''
replacement = '''    r"\\s*Découvrir la suite "\n    r"sur GamerQuest(?:\\.fr|fr)?\\.?",\n\n    r"\\s*Découvrez plus "\n    r"sur GamerQuest(?:\\.fr|fr)?\\.?",\n)'''

if needle not in text:
    raise SystemExit("CTA insertion point not found")

path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
print("Social CTA cleaner patched.")
# Trigger after apply workflow is present.
