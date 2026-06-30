# ── PREMIUM PDF EXPORT (cover + page-numbered TOC + section dividers) ──
# Improvements:
# 1) real cover page with logo auto-detection, report title, reporting year and bank name
# 2) clean table of contents with PDF page numbers via WeasyPrint target counters
# 3) section divider pages before each main report section
#
# Requires:
# pip install markdown weasyprint

from pathlib import Path as _PPath
import re as _re
import json as _json
import html as _html
import markdown as _md
import weasyprint as _wp


_DESIGN_ACCENT = "#D5DE00"       # neon yellow/lime accent from the slide style
_DESIGN_DARK = "#111111"         # premium black
_DESIGN_INK = "#1c2b2f"
_DESIGN_MUTED = "#667477"
_DESIGN_TEAL = "#14323b"


def _pdf_report_root() -> _PPath:
    """
    Default report root.

    Uses OUTPUT_DIR if the notebook already defines it.
    Otherwise falls back to:
    gen_data/generated_reports/agentic_ifrs_report
    """
    if "OUTPUT_DIR" in globals():
        try:
            return _PPath(OUTPUT_DIR)
        except Exception:
            pass

    return _PPath("gen_data/generated_reports/agentic_ifrs_report")


def _pdf_safe_bank_id() -> str:
    if "_safe_bank_id" in globals():
        try:
            return str(_safe_bank_id())
        except Exception:
            pass

    for candidate in [globals().get("bank_id"), globals().get("BANK_ID"), "BANK01"]:
        if candidate:
            return str(candidate)

    return "BANK01"


def _pdf_safe_bank_name() -> str:
    if "_safe_bank_name" in globals():
        try:
            return str(_safe_bank_name())
        except Exception:
            pass

    for candidate in [globals().get("bank_name"), globals().get("BANK_NAME")]:
        if candidate:
            return str(candidate)

    return _pdf_safe_bank_id()


def _pdf_safe_reporting_year() -> str:
    if "_safe_reporting_year" in globals():
        try:
            return str(_safe_reporting_year())
        except Exception:
            pass

    for candidate in [globals().get("reporting_year"), globals().get("REPORTING_YEAR"), "2024"]:
        if candidate:
            return str(candidate)

    return "2024"


def _slugify_pdf_section(title: str) -> str:
    slug = _re.sub(r"[^a-zA-Z0-9\s-]", "", title).strip().lower()
    slug = _re.sub(r"\s+", "-", slug)
    return f"section-{slug}"


def _find_report_logo() -> str:
    """
    Return a file:// URI for a logo if the project has one; otherwise return an empty string.

    Add your logo to one of these paths to make the cover use it automatically:
    - outputs/logo.png
    - outputs/assets/logo.png
    - assets/logo.png
    - images/logo.png
    - images/ey_logo.png
    - images/bank_logo.png
    """
    candidates = [
        _PPath("outputs/logo.png"),
        _PPath("outputs/logo.jpg"),
        _PPath("outputs/assets/logo.png"),
        _PPath("outputs/assets/logo.jpg"),
        _PPath("assets/logo.png"),
        _PPath("assets/logo.jpg"),
        _PPath("images/logo.png"),
        _PPath("images/logo.jpg"),
        _PPath("images/ey_logo.png"),
        _PPath("images/bank_logo.png"),
    ]

    for path in candidates:
        if path.exists():
            return path.resolve().as_uri()

    return ""


def _strip_markdown_cover_and_toc(report_md: str) -> str:
    """
    The markdown report may already contain a simple cover and markdown TOC.
    For the PDF, we replace them with designed HTML pages.
    """
    text = report_md.strip()

    first_section = _re.search(
        r"(?m)^#{1,3}\s+(General Requirements|Governance|Strategy|Risk Management|Metrics and Targets)\s*$",
        text,
    )

    if first_section:
        return text[first_section.start():].strip()

    return text


def _split_report_into_major_blocks(report_body_md: str):
    """
    Split markdown into major blocks so we can insert divider pages.

    Returns:
        list of (title, slug, markdown_block)
    """
    section_titles = [
        "General Requirements",
        "Governance",
        "Strategy",
        "Risk Management",
        "Metrics and Targets",
        "Appendices",
    ]

    pattern = r"(?m)^#{1,3}\s+(" + "|".join(_re.escape(t) for t in section_titles) + r")\s*$"
    matches = list(_re.finditer(pattern, report_body_md))

    if not matches:
        return [("Report", "section-report", report_body_md)]

    blocks = []

    for i, match in enumerate(matches):
        title = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(report_body_md)
        block = report_body_md[start:end].strip()
        slug = _slugify_pdf_section(title)
        blocks.append((title, slug, block))

    return blocks


def _replace_first_heading_with_anchor(block_md: str, title: str, slug: str) -> str:
    escaped_title = _html.escape(title)

    return _re.sub(
        r"(?m)^#{1,3}\s+" + _re.escape(title) + r"\s*$",
        f'<h3 id="{slug}">{escaped_title}</h3>',
        block_md,
        count=1,
    )


def _build_cover_html(bank_name: str, reporting_year: str) -> str:
    logo_uri = _find_report_logo()

    if logo_uri:
        logo_html = f'<img src="{logo_uri}" class="cover-logo" alt="logo">'
    else:
        logo_html = '<div class="cover-logo-placeholder">ESG</div>'

    return f"""
    <section class="cover-page">
        <div class="cover-topline"></div>
        <div class="cover-header">
            {logo_html}
            <div class="cover-label">Sustainability reporting package</div>
        </div>
        <div class="cover-main">
            <div class="cover-kicker">{_html.escape(str(reporting_year))}</div>
            <h1>{_html.escape(str(bank_name))}</h1>
            <h2>Sustainability-related Financial Disclosures</h2>
            <p>Prepared with reference to IFRS S1 and IFRS S2</p>
        </div>
        <div class="cover-footer">
            <span>ESG Risk Intelligence System</span>
            <span>Generated disclosure report</span>
        </div>
    </section>
    """


def _build_toc_html(blocks) -> str:
    main_blocks = [(title, slug) for title, slug, _ in blocks]
    rows = []

    for idx, (title, slug) in enumerate(main_blocks, start=1):
        rows.append(
            f'<li><a href="#{slug}"><span class="toc-number">{idx:02d}</span>'
            f'<span class="toc-title">{_html.escape(title)}</span></a></li>'
        )

    return f"""
    <section class="toc-page">
        <div class="toc-eyebrow">Contents</div>
        <h2>Table of contents</h2>
        <ol class="pdf-toc">
            {''.join(rows)}
        </ol>
    </section>
    """


def _build_section_divider_html(title: str, index: int) -> str:
    return f"""
    <section class="section-divider-page">
        <div class="divider-number">{index:02d}</div>
        <div class="divider-rule"></div>
        <h2>{_html.escape(title)}</h2>
        <p>Key disclosures, evidence boundaries and supporting exhibits.</p>
    </section>
    """


_PREMIUM_PDF_CSS = f"""
@page {{
    size: A4;
    margin: 22mm 20mm 20mm 20mm;
    @bottom-center {{ content: counter(page) " / " counter(pages); font-size: 8pt; color: #7b8587; }}
}}

@page cover {{
    margin: 0;
    @bottom-center {{ content: none; }}
}}

@page toc {{
    margin: 24mm 22mm 22mm 22mm;
    @bottom-center {{ content: counter(page) " / " counter(pages); font-size: 8pt; color: #7b8587; }}
}}

@page divider {{
    margin: 0;
    @bottom-center {{ content: none; }}
}}

html {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 10.4pt;
    color: {_DESIGN_INK};
    line-height: 1.5;
}}

body {{
    margin: 0;
}}

/* Cover page */
.cover-page {{
    page: cover;
    height: 297mm;
    background: {_DESIGN_DARK};
    color: #ffffff;
    position: relative;
    page-break-after: always;
    overflow: hidden;
}}

.cover-topline {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 8mm;
    background: {_DESIGN_ACCENT};
}}

.cover-header {{
    position: absolute;
    top: 24mm;
    left: 24mm;
    right: 24mm;
    display: flex;
    align-items: center;
    justify-content: space-between;
}}

.cover-logo {{
    max-width: 38mm;
    max-height: 18mm;
    object-fit: contain;
    background: #ffffff;
    padding: 4mm;
    border-radius: 2mm;
}}

.cover-logo-placeholder {{
    width: 24mm;
    height: 24mm;
    border: 1.2mm solid {_DESIGN_ACCENT};
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    color: {_DESIGN_ACCENT};
    letter-spacing: 1pt;
}}

.cover-label {{
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 1.5pt;
    color: #d9dddf;
}}

.cover-main {{
    position: absolute;
    left: 24mm;
    right: 24mm;
    top: 92mm;
}}

.cover-kicker {{
    color: {_DESIGN_ACCENT};
    font-size: 16pt;
    font-weight: 800;
    margin-bottom: 10mm;
}}

.cover-main h1 {{
    color: #ffffff;
    font-size: 34pt;
    line-height: 1.05;
    margin: 0 0 8mm 0;
    max-width: 150mm;
}}

.cover-main h2 {{
    color: #ffffff;
    font-size: 18pt;
    font-weight: 400;
    margin: 0 0 5mm 0;
}}

.cover-main p {{
    color: #d5dcdf;
    font-size: 11pt;
    margin: 0;
    text-align: left;
}}

.cover-footer {{
    position: absolute;
    left: 24mm;
    right: 24mm;
    bottom: 22mm;
    display: flex;
    justify-content: space-between;
    color: #c9d0d2;
    font-size: 9pt;
    border-top: 0.4mm solid #313a3d;
    padding-top: 6mm;
}}

/* TOC with page numbers */
.toc-page {{
    page: toc;
    page-break-after: always;
}}

.toc-eyebrow {{
    color: {_DESIGN_ACCENT};
    text-transform: uppercase;
    letter-spacing: 1.5pt;
    font-weight: 700;
    font-size: 9pt;
    margin-bottom: 5mm;
}}

.toc-page h2 {{
    font-size: 28pt;
    color: {_DESIGN_TEAL};
    margin: 0 0 14mm 0;
}}

.pdf-toc {{
    list-style: none;
    padding: 0;
    margin: 0;
}}

.pdf-toc li {{
    margin: 0;
    padding: 5mm 0;
    border-bottom: 0.25mm solid #d9e1e3;
}}

.pdf-toc a {{
    color: {_DESIGN_INK};
    text-decoration: none;
    display: block;
    width: 100%;
    font-size: 12pt;
}}

.pdf-toc a::after {{
    content: leader('.') target-counter(attr(href), page);
    color: {_DESIGN_MUTED};
}}

.toc-number {{
    color: {_DESIGN_ACCENT};
    background: {_DESIGN_DARK};
    padding: 1.5mm 2.2mm;
    margin-right: 5mm;
    font-size: 8pt;
    font-weight: 700;
}}

.toc-title {{
    font-weight: 650;
}}

/* Section divider pages */
.section-divider-page {{
    page: divider;
    height: 297mm;
    background: {_DESIGN_DARK};
    color: #ffffff;
    position: relative;
    page-break-after: always;
    overflow: hidden;
}}

.divider-number {{
    position: absolute;
    top: 24mm;
    left: 24mm;
    color: {_DESIGN_ACCENT};
    font-size: 24pt;
    font-weight: 800;
}}

.divider-rule {{
    position: absolute;
    top: 61mm;
    left: 24mm;
    width: 36mm;
    height: 1.2mm;
    background: {_DESIGN_ACCENT};
}}

.section-divider-page h2 {{
    position: absolute;
    left: 24mm;
    right: 24mm;
    top: 82mm;
    color: #ffffff;
    font-size: 32pt;
    line-height: 1.08;
    margin: 0;
}}

.section-divider-page p {{
    position: absolute;
    left: 24mm;
    bottom: 32mm;
    color: #d5dcdf;
    font-size: 11pt;
    text-align: left;
    margin: 0;
}}

/* Report body */
h1 {{
    font-size: 23pt;
    color: {_DESIGN_TEAL};
    margin: 0 0 2pt 0;
}}

h2 {{
    font-size: 13pt;
    font-weight: 500;
    color: #2e7d7d;
    margin: 0 0 14pt 0;
}}

h3 {{
    font-size: 15.5pt;
    color: {_DESIGN_TEAL};
    border-bottom: 2px solid {_DESIGN_ACCENT};
    padding-bottom: 4px;
    margin: 0 0 12pt 0;
    page-break-after: avoid;
}}

h4 {{
    font-size: 11.5pt;
    color: #1f4e5f;
    margin: 16pt 0 6pt 0;
    page-break-after: avoid;
}}

p {{
    margin: 0 0 8pt 0;
    text-align: justify;
}}

ul {{
    margin: 0 0 8pt 0;
}}

li {{
    margin: 0 0 3pt 0;
}}

strong {{
    color: {_DESIGN_TEAL};
}}

table {{
    border-collapse: collapse;
    width: 100%;
    margin: 4pt 0 14pt 0;
    font-size: 8.4pt;
    page-break-inside: avoid;
}}

thead {{
    display: table-header-group;
}}

.exhibit-caption {{
    page-break-after: avoid;
    margin: 14pt 0 4pt 0;
    font-weight: 700;
    color: {_DESIGN_TEAL};
}}

th {{
    background: {_DESIGN_TEAL};
    color: #fff;
    text-align: left;
    padding: 5px 7px;
    font-weight: 600;
}}

td {{
    border-bottom: 1px solid #d6dee0;
    padding: 4px 7px;
    vertical-align: top;
}}

tr:nth-child(even) td {{
    background: #f3f6f6;
}}

img {{
    max-width: 100%;
    margin: 5pt auto 12pt auto;
    display: block;
}}

hr {{
    border: none;
    border-top: 1px solid #d6dee0;
    margin: 16pt 0;
}}

a {{
    color: #1f4e5f;
    text-decoration: none;
}}

.report-section {{
    page-break-before: always;
}}

.report-section:first-of-type {{
    page-break-before: auto;
}}
"""


def build_full_report_pdf(md_path=None, pdf_path=None, html_path=None, include_section_dividers=True):
    bank_id = _pdf_safe_bank_id()
    bank_name = _pdf_safe_bank_name()
    reporting_year = _pdf_safe_reporting_year()

    report_root = _pdf_report_root()
    pdf_handoff_dir = report_root / "12_pdf_handoff"

    # Markdown source:
    # gen_data/generated_reports/agentic_ifrs_report/12_pdf_handoff/approved_report_markdown.md
    if md_path is None:
        md_path = pdf_handoff_dir / "approved_report_markdown.md"

    # PDF output:
    # gen_data/generated_reports/agentic_ifrs_report/full_report_BANK01_designed.pdf
    if pdf_path is None:
        pdf_path = report_root / f"full_report_{bank_id}_designed.pdf"

    # HTML output:
    # gen_data/generated_reports/agentic_ifrs_report/full_report_BANK01_designed.html
    if html_path is None:
        html_path = report_root / f"full_report_{bank_id}_designed.html"

    md_path = _PPath(md_path)
    pdf_path = _PPath(pdf_path)
    html_path = _PPath(html_path)

    if not md_path.exists():
        raise FileNotFoundError(
            f"Markdown report not found: {md_path}\n"
            "Expected the final approved Markdown report under:\n"
            "gen_data/generated_reports/agentic_ifrs_report/12_pdf_handoff/approved_report_markdown.md"
        )

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)

    report_md = md_path.read_text(encoding="utf-8")
    body_md = _strip_markdown_cover_and_toc(report_md)
    blocks = _split_report_into_major_blocks(body_md)

    cover_html = _build_cover_html(bank_name=bank_name, reporting_year=reporting_year)
    toc_html = _build_toc_html(blocks)

    section_html_parts = []

    for idx, (title, slug, block_md) in enumerate(blocks, start=1):
        if include_section_dividers:
            section_html_parts.append(_build_section_divider_html(title, idx))

        anchored_md = _replace_first_heading_with_anchor(block_md, title, slug)

        block_html = _md.markdown(
            anchored_md,
            extensions=["tables", "sane_lists", "attr_list", "md_in_html"],
            output_format="html5",
        )

        section_html_parts.append(f'<article class="report-section">{block_html}</article>')

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{_html.escape(bank_name)} - Sustainability-related Financial Disclosures {reporting_year}</title>
</head>
<body>
    {cover_html}
    {toc_html}
    {''.join(section_html_parts)}
</body>
</html>"""

    html_path.write_text(html_doc, encoding="utf-8")

    # base_url points to the markdown/report output folder,
    # so existing figure links like figures/x.png still resolve.
    _wp.HTML(
        string=html_doc,
        base_url=str(md_path.parent.resolve()),
    ).write_pdf(
        str(pdf_path),
        stylesheets=[_wp.CSS(string=_PREMIUM_PDF_CSS)],
    )

    design_meta = {
        "bank_id": bank_id,
        "bank_name": bank_name,
        "reporting_year": reporting_year,
        "source_markdown": str(md_path),
        "html_output": str(html_path),
        "pdf_output": str(pdf_path),
        "improvements_added": [
            "designed_cover_page_with_logo_autodetection",
            "page_numbered_table_of_contents",
            "section_divider_pages",
        ],
        "logo_detected": bool(_find_report_logo()),
        "section_dividers": [title for title, _, _ in blocks],
    }

    # Metadata output:
    # gen_data/generated_reports/agentic_ifrs_report/full_report_BANK01_designed.meta.json
    meta_path = report_root / f"full_report_{bank_id}_designed.meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    meta_path.write_text(
        _json.dumps(design_meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return str(pdf_path), str(html_path), str(meta_path)


pdf_output_path, html_output_path, pdf_meta_path = build_full_report_pdf()

print("Designed PDF written:", pdf_output_path)
print("HTML preview written:", html_output_path)
print("PDF design metadata:", pdf_meta_path)

try:
    import os as _os
    print("PDF size:", _os.path.getsize(pdf_output_path), "bytes")
except Exception:
    pass