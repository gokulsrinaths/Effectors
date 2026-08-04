"""Server-side PDF report generation for completed jobs.

The web UI's "Download PDF Report" button is `window.print()`, which produces
nothing the server can attach to an email. This module builds a real PDF from
the stored result JSON so the same report can be mailed and downloaded.

Every failure path returns ``None`` rather than raising: a job that has already
completed must never be failed by a reporting problem.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

from ..config import get_settings

logger = logging.getLogger(__name__)

# TM-score bands, per Zhang & Skolnick 2005 — kept identical to backend/main.py
# and the web UI legend.
TM_SAME_FOLD_MIN = 0.50
TM_UNRELATED_MAX = 0.20

_BAND_GOOD = "#1a7f37"
_BAND_WEAK = "#b35c00"
_BAND_POOR = "#b32020"
_DOMAIN = "#0b6bcb"
_INK = "#212529"
_MUTED = "#5b6675"

_FALLBACK_LABELS = {
    "full_fold": "Known structural family",
    "domain_match": "Partial / domain match",
    "ambiguous": "Ambiguous structural similarity",
    "unrelated": "Novel structure",
}

_TYPE_SHORT = {
    "full_fold": "Same fold",
    "domain_match": "Domain match",
    "ambiguous": "Ambiguous",
    "unrelated": "Unrelated",
}


def _alignment_labels() -> dict[str, str]:
    """Prefer backend/main.py as the source of truth so labels cannot drift."""
    try:
        import sys

        backend_root = Path(__file__).resolve().parents[2]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from main import ALIGNMENT_TYPE_LABELS  # type: ignore

        return dict(ALIGNMENT_TYPE_LABELS)
    except Exception:
        return dict(_FALLBACK_LABELS)


def _band_color(score: float | None) -> str:
    if score is None:
        return _MUTED
    if score >= TM_SAME_FOLD_MIN:
        return _BAND_GOOD
    if score >= TM_UNRELATED_MAX:
        return _BAND_WEAK
    return _BAND_POOR


def _fmt(v: Any, digits: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:.{digits}f}" if isinstance(v, float) else str(v)
    return str(v)


def _fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def _find_structure_image(job_id: str, result: dict) -> Path | None:
    """Locate the rendered structure PNG.

    Checks the path recorded in the result first, then the job-scoped name, then
    the legacy shared name still present in artifacts written before that was
    fixed.
    """
    settings = get_settings()
    candidates = []
    recorded = result.get("structure_image_local_path") or result.get("structure_image_path")
    if recorded:
        candidates.append(Path(str(recorded)))
    candidates.append(settings.results_dir / f"{job_id}.structure.png")
    candidates.append(settings.results_dir / "structure_preview.png")
    for path in candidates:
        try:
            if path.exists() and path.stat().st_size > 0:
                return path
        except OSError:
            continue
    return None


def build_job_report_pdf(job_id: str, result: dict | None = None) -> Path | None:
    """Render a PDF report for one completed job.

    Returns the written path, or ``None`` if anything went wrong — callers treat
    a missing PDF as "send the email without an attachment".
    """
    try:
        return _build(job_id, result)
    except Exception as exc:  # noqa: BLE001 — reporting must never fail a job
        logger.warning("PDF report generation failed for %s: %s: %s", job_id, type(exc).__name__, exc)
        return None


def _build(job_id: str, result: dict | None) -> Path | None:
    # Imported lazily so a missing dependency degrades to a text-only email
    # instead of breaking module import for the whole worker.
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    settings = get_settings()

    if result is None:
        result_path = settings.results_dir / f"{job_id}.json"
        if not result_path.exists():
            logger.warning("No result JSON for %s; cannot build PDF", job_id)
            return None
        result = json.loads(result_path.read_text(encoding="utf-8"))

    labels = _alignment_labels()
    results_list = (result.get("processing_result") or {}).get("results") or []
    first = results_list[0] if results_list else {}
    tm = first.get("tm_align_result") or {}
    summary = result.get("summary") or {}

    classification = first.get("classification") or summary.get("classification") or "—"
    best_match = first.get("best_match_id") or summary.get("best_match_id")
    chain1 = tm.get("tm_score_chain1", first.get("tm_score"))
    chain2 = tm.get("tm_score_chain2")
    best_score = tm.get("tm_score_best")
    if best_score is None:
        best_score = max([s for s in (chain1, chain2) if s is not None], default=None)
    alignment_type = tm.get("alignment_type")

    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=13,
                          textColor=colors.HexColor(_INK), alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10,
                           textColor=colors.HexColor(_MUTED))
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=17, leading=21,
                        textColor=colors.HexColor(_INK), spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, leading=14,
                        textColor=colors.HexColor(_INK), spaceBefore=14, spaceAfter=6)

    out_path = settings.results_dir / f"{job_id}.report.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title=f"EffectorDB Report {job_id}", author="EffectorDB",
    )
    avail = doc.width
    story: list[Any] = []

    # ── Header ──────────────────────────────────────────────────────────────
    story.append(Paragraph("EffectorDB Analysis Report", h1))
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    query_id = first.get("query_id") or "—"
    story.append(Paragraph(
        f"Job <b>{job_id}</b> &nbsp;·&nbsp; Query <b>{query_id}</b> &nbsp;·&nbsp; Generated {generated}",
        small))
    story.append(Spacer(1, 14))

    # ── Verdict ─────────────────────────────────────────────────────────────
    verdict_color = _DOMAIN if alignment_type == "domain_match" else _band_color(best_score)
    story.append(Paragraph(
        f'<font size="13" color="{verdict_color}"><b>{classification}</b></font>', body))
    if best_match:
        story.append(Paragraph(f'Best match: <b>{best_match}</b>', body))

    # ── Summary metrics ─────────────────────────────────────────────────────
    story.append(Paragraph("Summary", h2))
    rows = [
        ["TM-score, query-normalized (Chain 1)", _fmt(chain1)],
        ["TM-score, target-normalized (Chain 2)", _fmt(chain2)],
        ["Best of the two", _fmt(best_score)],
        ["Alignment type", labels.get(alignment_type, "—") if alignment_type else "—"],
        ["Coverage (query / target)",
         f"{_fmt_pct(tm.get('coverage_query'))} / {_fmt_pct(tm.get('coverage_target'))}"],
        ["Structural sequence identity", _fmt_pct(tm.get("seq_id"))],
        ["Aligned length", _fmt(tm.get("alignment_length"), 0)],
    ]
    alphafold_status = (result.get("alphafold") or {}).get("status")
    if alphafold_status:
        rows.append(["AlphaFold prediction", str(alphafold_status)])

    meta = Table([[Paragraph(k, body), Paragraph(f"<b>{v}</b>", body)] for k, v in rows],
                 colWidths=[avail * 0.55, avail * 0.45])
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e6e8eb")),
    ]))
    story.append(meta)

    # ── Top matches ─────────────────────────────────────────────────────────
    top = tm.get("top_matches") or []
    story.append(Paragraph("Top TM-align Matches", h2))
    if top:
        story.append(Paragraph("Ranked by the better of the two normalized scores.", small))
        story.append(Spacer(1, 5))
        head = ["#", "Structure", "Chain 1", "Chain 2", "Alignment", "Aligned"]
        data = [[Paragraph(f"<b>{c}</b>", small) for c in head]]
        for i, m in enumerate(top[:10], start=1):
            c1 = m.get("tm_score_chain1", m.get("tm_score"))
            c2 = m.get("tm_score_chain2")
            mtype = m.get("alignment_type")
            data.append([
                Paragraph(str(i), small),
                Paragraph(str(m.get("structure", "—")), small),
                Paragraph(f'<font color="{_band_color(c1)}"><b>{_fmt(c1)}</b></font>', small),
                Paragraph(f'<font color="{_band_color(c2)}"><b>{_fmt(c2)}</b></font>', small),
                Paragraph(_TYPE_SHORT.get(mtype, mtype or "—"), small),
                Paragraph(_fmt(m.get("aligned_length"), 0), small),
            ])
        widths = [avail * w for w in (0.06, 0.34, 0.14, 0.14, 0.18, 0.14)]
        tbl = Table(data, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dee2e6")),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("<i>No structural matches were returned for this job.</i>", small))

    # ── Structure image ─────────────────────────────────────────────────────
    img_path = _find_structure_image(job_id, result)
    story.append(Paragraph("Best-Match Structure", h2))
    if img_path:
        try:
            iw, ih = ImageReader(str(img_path)).getSize()
            w = min(avail, 4.6 * inch)
            story.append(Image(str(img_path), width=w, height=w * (ih / iw)))
            story.append(Paragraph("Rendered with PyMOL — rainbow cartoon, ray-traced.", small))
        except Exception as exc:  # noqa: BLE001 — an unreadable image must not abort the report
            logger.warning("Could not embed structure image for %s: %s", job_id, exc)
            story.append(Paragraph("<i>Structure rendering could not be embedded.</i>", small))
    else:
        story.append(Paragraph("<i>Structure rendering unavailable for this job.</i>", small))

    # ── Legend ──────────────────────────────────────────────────────────────
    # Kept as one block: a legend split across a page break leaves the reader
    # holding numbers with no key to them.
    legend: list[Any] = [
        Paragraph("Interpreting these scores", h2),
        Paragraph(
            "TM-align reports <b>two</b> scores because structural similarity is directional. "
            "<b>Chain 1</b> is normalized by the length of the query; <b>Chain 2</b> by the length "
            "of the database structure. A high Chain 2 with a low Chain 1 means the query "
            "<i>contains</i> that structure as a domain rather than matching it as a whole.", body),
        Spacer(1, 6),
    ]
    for color, label in (
        (_BAND_GOOD, "<b>&#8805; 0.50</b> — same fold (SCOP/CATH)"),
        (_BAND_WEAK, "<b>0.20 – 0.50</b> — ambiguous"),
        (_BAND_POOR, "<b>&lt; 0.20</b> — unrelated, at the level of randomly chosen proteins"),
    ):
        legend.append(Paragraph(f'<font color="{color}">&#9632;</font> {label}', body))
    legend.append(Spacer(1, 8))
    legend.append(Paragraph(
        "Thresholds per Zhang &amp; Skolnick, <i>Nucleic Acids Research</i> 33:2302–2309 (2005).", small))
    legend.append(Spacer(1, 14))
    legend.append(Paragraph(
        "Automated report generated by EffectorDB. Please do not reply to this message.", small))
    story.append(KeepTogether(legend))

    doc.build(story)
    return out_path if out_path.exists() else None
