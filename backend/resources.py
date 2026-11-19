from pathlib import Path
from pypdf import PdfReader #type:ignore
import json

DATA_DIR = Path(__file__).resolve().parent / "data"

#Read LinkedIn PDF
try: 
    reader = PdfReader(DATA_DIR / "linkedin.pdf")
    linkedin = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            linkedin += text

except FileNotFoundError:
    linkedin="LinkedIn profile not available"
    
#Read other data files
with open(DATA_DIR / "summary.txt","r",encoding="utf-8") as f:
    summary = f.read()
    
with open(DATA_DIR / "style.txt","r", encoding="utf-8") as f:
    style = f.read()
    
with open(DATA_DIR / "facts.json","r", encoding="utf-8") as f:
    facts = json.load(f)


def rag_documents() -> list[dict[str, str]]:
    """Return the source material that is indexed for retrieval."""
    return [
        {"id": "profile:facts", "source": "facts.json", "text": json.dumps(facts, indent=2)},
        {"id": "profile:summary", "source": "summary.txt", "text": summary},
        {"id": "profile:linkedin", "source": "linkedin.pdf", "text": linkedin},
        {"id": "profile:style", "source": "style.txt", "text": style},
    ]


    
