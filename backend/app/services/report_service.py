import io
import re
import uuid
from datetime import datetime

from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.scan import Scan, Finding


SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


class ReportPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, "OpenAudit Security Report", align="L")
            self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def _safe_text(text: str | None) -> str:
    if not text:
        return "N/A"
    # Replace characters that fpdf2 can't encode in latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _severity_label(sev: str | None) -> str:
    return (sev or "info").upper()


class ReportService:
    @staticmethod
    async def generate_scan_report(
        db: AsyncSession, scan_id: uuid.UUID
    ) -> tuple[io.BytesIO, str]:
        # Fetch scan with project and findings
        result = await db.execute(
            select(Scan)
            .options(selectinload(Scan.project), selectinload(Scan.findings))
            .where(Scan.id == scan_id)
        )
        scan = result.scalar_one_or_none()
        if not scan:
            raise ValueError("Scan not found")

        project = scan.project
        findings = sorted(
            scan.findings,
            key=lambda f: SEVERITY_ORDER.index(f.severity)
            if f.severity in SEVERITY_ORDER
            else 99,
        )

        # Severity breakdown
        severity_counts: dict[str, int] = {}
        for f in findings:
            sev = f.severity or "info"
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Build PDF
        pdf = ReportPDF()
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(auto=True, margin=20)

        # --- Title Page ---
        pdf.add_page()
        pdf.ln(50)
        pdf.set_font("Helvetica", "B", 28)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 15, "OpenAudit", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 18)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(
            0, 12, "Security Audit Report", align="C", new_x="LMARGIN", new_y="NEXT"
        )
        pdf.ln(20)
        pdf.set_font("Helvetica", "", 14)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(
            0,
            10,
            _safe_text(f"Project: {project.name}"),
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.cell(
            0,
            10,
            f"Scan Date: {scan.created_at.strftime('%Y-%m-%d %H:%M')}",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.cell(
            0,
            10,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )

        # --- Summary Page ---
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 12, "Summary", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(50, 50, 50)
        summary_items = [
            ("Project", _safe_text(project.name)),
            ("Filename", _safe_text(project.original_filename)),
            ("Files Analyzed", str(project.file_count)),
            ("Total Findings", str(len(findings))),
        ]
        for label, value in summary_items:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(50, 8, f"{label}:")
            pdf.set_font("Helvetica", "", 11)
            pdf.cell(0, 8, value, new_x="LMARGIN", new_y="NEXT")

        # Severity breakdown
        pdf.ln(8)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Severity Breakdown", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        for sev in SEVERITY_ORDER:
            count = severity_counts.get(sev, 0)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(30, 8, f"  {sev.upper()}")
            pdf.set_font("Helvetica", "", 11)
            pdf.cell(0, 8, str(count), new_x="LMARGIN", new_y="NEXT")

        # --- Detailed Findings ---
        if findings:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 12, "Detailed Findings", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)

            for i, finding in enumerate(findings, 1):
                # Check if we need a new page (at least 60mm needed for a finding)
                if pdf.get_y() > 230:
                    pdf.add_page()

                # Finding header
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_text_color(30, 30, 30)
                sev_label = _severity_label(finding.severity)
                vuln_type = _safe_text(finding.vulnerability_type) or "Unknown"
                pdf.cell(
                    0,
                    10,
                    f"#{i}  [{sev_label}] {vuln_type}",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )

                # Metadata
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(80, 80, 80)
                if finding.source_location:
                    pdf.cell(
                        0,
                        7,
                        f"Location: {_safe_text(finding.source_location)}",
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
                if finding.confidence is not None:
                    pdf.cell(
                        0,
                        7,
                        f"Confidence: {finding.confidence:.0%}",
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )

                # Source code
                if finding.source_code:
                    pdf.ln(3)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(50, 50, 50)
                    pdf.cell(0, 7, "Source Code:", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Courier", "", 9)
                    pdf.set_text_color(60, 60, 60)
                    # Truncate very long source code
                    code = _safe_text(finding.source_code)
                    code_lines = code.split("\n")[:15]
                    for line in code_lines:
                        pdf.cell(
                            0,
                            5,
                            f"  {line[:120]}",
                            new_x="LMARGIN",
                            new_y="NEXT",
                        )
                    if len(finding.source_code.split("\n")) > 15:
                        pdf.cell(
                            0, 5, "  ... (truncated)", new_x="LMARGIN", new_y="NEXT"
                        )

                # AI Analysis
                if finding.ai_analysis:
                    pdf.ln(3)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(50, 50, 50)
                    pdf.cell(0, 7, "AI Analysis:", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", "", 10)
                    pdf.set_text_color(60, 60, 60)
                    analysis = _safe_text(finding.ai_analysis)
                    pdf.multi_cell(0, 6, analysis)

                # Data flow path
                if finding.flow_code_snippets and finding.flow_code_snippets.get(
                    "flow"
                ):
                    pdf.ln(3)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(50, 50, 50)
                    pdf.cell(0, 7, "Data Flow:", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Courier", "", 9)
                    pdf.set_text_color(60, 60, 60)
                    for step in finding.flow_code_snippets["flow"][:10]:
                        loc = _safe_text(step.get("file", ""))
                        line = step.get("line", "")
                        code = _safe_text(step.get("code", ""))
                        pdf.cell(
                            0,
                            5,
                            f"  {loc}:{line}  {code[:100]}",
                            new_x="LMARGIN",
                            new_y="NEXT",
                        )

                # Separator
                pdf.ln(5)
                pdf.set_draw_color(200, 200, 200)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
                pdf.ln(5)

        # Output
        buf = io.BytesIO(pdf.output())
        safe_name = re.sub(r"[^\w\-.]", "_", project.name)
        filename = f"openaudit_{safe_name}_{scan.created_at.strftime('%Y%m%d')}.pdf"
        return buf, filename
