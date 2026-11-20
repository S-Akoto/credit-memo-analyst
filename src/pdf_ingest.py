import argparse
import json
import os
from pathlib import Path
from google import genai
from google.genai import types
from pypdf import PdfReader
from src.models import BorrowerPacket


def extract_packet_from_pdf(pdf_path: str | Path, policy_id: str = "sme_commercial") -> BorrowerPacket:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for PDF financial packet extraction.")

    reader = PdfReader(str(pdf_path))
    raw_text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not raw_text:
        raise ValueError(f"No extractable text found in {pdf_path}")

    client = genai.Client(api_key=api_key, http_options={"timeout": 45})
    prompt = f"""
Extract the borrower profile, facility request, multi-year financial statements, and qualitative context
from the following commercial lending packet text into the exact BorrowerPacket JSON schema.
Use policy_id="{policy_id}" unless explicitly stated otherwise. Convert all dollar values to plain numbers.

DOCUMENT TEXT:
{raw_text[:25000]}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BorrowerPacket,
            temperature=0.0,
        ),
    )
    return BorrowerPacket.model_validate_json(response.text)


def main():
    parser = argparse.ArgumentParser(description="Extract structured BorrowerPacket JSON from a PDF.")
    parser.add_argument("--pdf", required=True, help="Path to borrower PDF packet")
    parser.add_argument("--policy", default="sme_commercial", choices=["sme_commercial", "agri_supply_chain"])
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    packet = extract_packet_from_pdf(args.pdf, policy_id=args.policy)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(packet.model_dump(), indent=2), encoding="utf-8")
    print(f"[ok] Extracted {packet.borrower_name} -> {out_path}")


if __name__ == "__main__":
    main()
