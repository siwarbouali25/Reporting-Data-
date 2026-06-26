# ============================================================
# LLM STYLE NOTE EXTRACTION
# ============================================================

STYLE_CHUNK_SYSTEM_PROMPT = """
You are a senior sustainability reporting style analyst.

You extract reusable style, structure, formatting, and disclosure presentation patterns from a reference IFRS S1/S2 sustainability report.

Important:
- Do not copy sentences from the reference report.
- Do not extract company-specific facts, metrics, names, amounts, achievements, targets, people, committees, or claims as reusable content.
- Focus only on abstract writing style and structure.
- The output will be used to guide report generation for a different company.
- Return valid JSON only.
""".strip()


def build_style_chunk_prompt(section_name: str, chunk_index: int, chunk_text: str) -> str:
    return f"""
Analyze this excerpt from the reference report section: {section_name}.

Extract only reusable style and structure patterns.

Return JSON with this schema:
{{
  "section_name": "{section_name}",
  "chunk_index": {chunk_index},
  "tone_patterns": [],
  "paragraph_patterns": [],
  "heading_patterns": [],
  "table_patterns": [],
  "figure_or_diagram_patterns": [],
  "disclosure_language_patterns": [],
  "evidence_presentation_patterns": [],
  "section_specific_observations": [],
  "things_to_avoid_copying": [],
  "content_specific_items_detected_and_excluded": []
}}

Rules:
- Do not quote the reference report.
- Do not include Emirates NBD-specific names, facts, amounts, targets, awards, committees, people, or numbers as style rules.
- Do not include any copied sentence.
- Use abstract descriptions only.

REFERENCE EXCERPT:
{chunk_text}
""".strip()


style_chunk_notes = {}

for section_name, chunks in section_chunks.items():
    style_chunk_notes[section_name] = []

    for idx, chunk in enumerate(chunks, start=1):
        print(f"Extracting style notes: {section_name} chunk {idx}/{len(chunks)}")

        result = azure_chat_json(
            system_prompt=STYLE_CHUNK_SYSTEM_PROMPT,
            user_prompt=build_style_chunk_prompt(section_name, idx, chunk),
            request_label=f"Style notes {section_name} {idx}",
        )

        style_chunk_notes[section_name].append(result)

        time.sleep(STYLE_INTER_REQUEST_DELAY_SECONDS)


# Save raw notes
raw_notes_path = INTERMEDIATE_DIR / "style_chunk_notes.json"

with open(raw_notes_path, "w", encoding="utf-8") as f:
    json.dump(style_chunk_notes, f, ensure_ascii=False, indent=2)

print("Saved:", raw_notes_path)