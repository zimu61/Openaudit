import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.project import Project
from app.models.scan import Scan, Finding
from app.services.joern_service import JoernService
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# Timeout for a single AI call (including retries within _call_with_retry)
AI_FIRST_PASS_TIMEOUT = 90
AI_RETRY_TIMEOUT = 180


def _create_session_factory():
    """Create a new engine and session factory bound to the current event loop."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class ScanService:
    def __init__(self):
        self.joern = JoernService()
        self.ai = AIService()

    async def run_scan(self, project_id: str, scan_id: str) -> None:
        """Execute the full scan workflow."""
        engine, session_factory = _create_session_factory()
        try:
            async with session_factory() as db:
                try:
                    scan = await self._get_scan(db, scan_id)
                    project = await self._get_project(db, project_id)

                    if not scan or not project:
                        logger.error(f"Scan {scan_id} or project {project_id} not found")
                        return

                    # Step 1: Import CPG
                    await self._update_progress(
                        db, scan, "importing_cpg", 5, "Importing code into CPG..."
                    )
                    workspace = os.path.join(settings.WORKSPACE_DIR, f"scan_{scan_id}")
                    os.makedirs(workspace, exist_ok=True)

                    cpg_path = await self.joern.import_cpg(project.upload_path, workspace)

                    # Step 2: Extract candidates
                    await self._update_progress(
                        db, scan, "extracting_candidates", 20,
                        "Extracting function parameters and calls..."
                    )
                    candidates = await self.joern.extract_candidates(cpg_path)

                    if not candidates or (
                        not candidates.get("parameters") and not candidates.get("calls")
                    ):
                        await self._update_progress(
                            db, scan, "completed", 100,
                            "No candidates found. Scan complete."
                        )
                        scan.completed_at = datetime.now(timezone.utc)
                        project.status = "completed"
                        await db.commit()
                        return

                    # Group candidates by file
                    file_candidates = self._group_by_file(candidates)
                    total_files = len(file_candidates)
                    logger.info(
                        f"Found {len(candidates.get('parameters', []))} parameters and "
                        f"{len(candidates.get('calls', []))} calls across {total_files} files"
                    )

                    # Step 3: AI Source Identification (per file, sequential)
                    await self._update_progress(
                        db, scan, "identifying_sources", 30,
                        f"AI analyzing {total_files} files for user-controlled inputs..."
                    )

                    all_source_ids = []
                    source_info_map = {}
                    timed_out_files = []

                    # First pass
                    for i, (file_path, file_cands) in enumerate(file_candidates.items()):
                        progress = 30 + int(15 * (i + 1) / total_files)
                        await self._update_progress(
                            db, scan, "identifying_sources", progress,
                            f"Analyzing file {i + 1}/{total_files}: {Path(file_path).name}"
                        )

                        method_snippets = self._extract_method_snippets(
                            file_cands, project.upload_path, file_path
                        )

                        try:
                            source_ids = await asyncio.wait_for(
                                self.ai.identify_sources(method_snippets, file_cands, file_path),
                                timeout=AI_FIRST_PASS_TIMEOUT,
                            )
                            all_source_ids.extend(source_ids)
                            for sid in source_ids:
                                info = self._find_candidate_by_id(file_cands, sid)
                                if info:
                                    info["source_code_context"] = info.get("method_code", "")
                                    source_info_map[sid] = info
                        except asyncio.TimeoutError:
                            logger.warning(f"AI timed out for {file_path}, will retry")
                            timed_out_files.append((file_path, file_cands, method_snippets))
                        except Exception as e:
                            logger.error(f"AI failed for {file_path}: {e}")
                            timed_out_files.append((file_path, file_cands, method_snippets))

                    # Retry pass for timed-out files
                    failed_files = []
                    if timed_out_files:
                        await self._update_progress(
                            db, scan, "identifying_sources", 46,
                            f"Retrying {len(timed_out_files)} timed-out files..."
                        )
                        for j, (file_path, file_cands, method_snippets) in enumerate(timed_out_files):
                            progress = 46 + int(4 * (j + 1) / len(timed_out_files))
                            await self._update_progress(
                                db, scan, "identifying_sources", progress,
                                f"Retrying: {Path(file_path).name}"
                            )
                            try:
                                source_ids = await asyncio.wait_for(
                                    self.ai.identify_sources(method_snippets, file_cands, file_path),
                                    timeout=AI_RETRY_TIMEOUT,
                                )
                                all_source_ids.extend(source_ids)
                                for sid in source_ids:
                                    info = self._find_candidate_by_id(file_cands, sid)
                                    if info:
                                        info["source_code_context"] = info.get("method_code", "")
                                        source_info_map[sid] = info
                            except (asyncio.TimeoutError, Exception) as e:
                                logger.error(f"AI retry failed for {file_path}: {e}")
                                failed_files.append(file_path)

                    if failed_files:
                        logger.warning(f"AI analysis failed for files: {failed_files}")

                    if not all_source_ids:
                        msg = "No user-controlled sources identified. Scan complete."
                        if failed_files:
                            names = ", ".join(Path(f).name for f in failed_files)
                            msg = f"No sources identified. AI timed out on: {names}"
                        await self._update_progress(db, scan, "completed", 100, msg)
                        scan.completed_at = datetime.now(timezone.utc)
                        project.status = "completed"
                        await db.commit()
                        return

                    logger.info(f"AI identified {len(all_source_ids)} user-controlled sources")

                    # Step 4: Extract flows
                    await self._update_progress(
                        db, scan, "extracting_flows", 55,
                        f"Extracting data flows from {len(all_source_ids)} sources..."
                    )

                    flows = await self.joern.extract_flows(cpg_path, all_source_ids)
                    logger.info(f"Extracted {len(flows)} data flows")

                    if not flows:
                        await self._update_progress(
                            db, scan, "completed", 100,
                            "No exploitable data flows found. Scan complete."
                        )
                        scan.completed_at = datetime.now(timezone.utc)
                        project.status = "completed"
                        await db.commit()
                        return

                    # Step 5: AI Vulnerability Analysis (per flow, sequential)
                    await self._update_progress(
                        db, scan, "analyzing", 65,
                        f"AI analyzing {len(flows)} data flows for vulnerabilities..."
                    )

                    total_flows = len(flows)
                    findings_count = 0
                    timed_out_flows = []

                    # First pass
                    for i, flow in enumerate(flows):
                        progress = 65 + int(25 * (i + 1) / total_flows)
                        await self._update_progress(
                            db, scan, "analyzing", progress,
                            f"Analyzing flow {i + 1}/{total_flows}..."
                        )

                        source_id = flow.get("source_id")
                        source_info = source_info_map.get(source_id, {})
                        code_snippets = self._extract_code_snippets(flow)

                        try:
                            analysis = await asyncio.wait_for(
                                self.ai.analyze_vulnerability(source_info, flow, code_snippets),
                                timeout=AI_FIRST_PASS_TIMEOUT,
                            )
                            self._save_finding_if_vulnerable(
                                db, scan, source_id, source_info, flow, analysis
                            )
                            findings_count += 1 if analysis.get("vulnerability_type") and analysis.get("vulnerability_type") != "none" else 0
                        except asyncio.TimeoutError:
                            logger.warning(f"AI timed out for flow {i + 1}, will retry")
                            timed_out_flows.append((i, flow, source_id, source_info, code_snippets))
                        except Exception as e:
                            logger.error(f"AI failed for flow {i + 1}: {e}")
                            timed_out_flows.append((i, flow, source_id, source_info, code_snippets))

                    # Retry pass for timed-out flows
                    failed_flows = []
                    if timed_out_flows:
                        await self._update_progress(
                            db, scan, "analyzing", 91,
                            f"Retrying {len(timed_out_flows)} timed-out flows..."
                        )
                        for j, (idx, flow, source_id, source_info, code_snippets) in enumerate(timed_out_flows):
                            progress = 91 + int(4 * (j + 1) / len(timed_out_flows))
                            await self._update_progress(
                                db, scan, "analyzing", progress,
                                f"Retrying flow {idx + 1}..."
                            )
                            try:
                                analysis = await asyncio.wait_for(
                                    self.ai.analyze_vulnerability(source_info, flow, code_snippets),
                                    timeout=AI_RETRY_TIMEOUT,
                                )
                                self._save_finding_if_vulnerable(
                                    db, scan, source_id, source_info, flow, analysis
                                )
                                findings_count += 1 if analysis.get("vulnerability_type") and analysis.get("vulnerability_type") != "none" else 0
                            except (asyncio.TimeoutError, Exception) as e:
                                logger.error(f"AI retry failed for flow {idx + 1}: {e}")
                                sink_name = flow.get("sink", "unknown")
                                failed_flows.append(f"flow {idx + 1} (sink: {sink_name})")

                    if failed_flows:
                        logger.warning(f"AI analysis failed for flows: {failed_flows}")

                    # Step 6: Complete
                    await db.commit()

                    msg = f"Scan complete. Found {findings_count} potential vulnerabilities."
                    warnings = []
                    if failed_files:
                        names = ", ".join(Path(f).name for f in failed_files)
                        warnings.append(f"AI timed out on files: {names}")
                    if failed_flows:
                        warnings.append(f"AI timed out on: {', '.join(failed_flows)}")
                    if warnings:
                        msg += " WARNING: " + "; ".join(warnings)

                    await self._update_progress(db, scan, "completed", 100, msg)
                    scan.completed_at = datetime.now(timezone.utc)
                    project.status = "completed"
                    await db.commit()

                    logger.info(
                        f"Scan {scan_id} completed. Found {findings_count} findings."
                    )

                except Exception as e:
                    logger.exception(f"Scan {scan_id} failed: {e}")
                    try:
                        await db.rollback()

                        scan = await self._get_scan(db, scan_id)
                        if scan:
                            scan.status = "failed"
                            scan.error_message = str(e)[:2000]
                            scan.completed_at = datetime.now(timezone.utc)

                        project = await self._get_project(db, project_id)
                        if project:
                            project.status = "failed"

                        await db.commit()
                        await self._publish_progress(scan_id, {
                            "scan_id": scan_id,
                            "status": "failed",
                            "progress": scan.progress if scan else 0,
                            "current_step": "Failed",
                            "message": str(e)[:500],
                        })
                    except Exception:
                        logger.exception("Failed to update scan status after error")
        finally:
            await engine.dispose()

    def _save_finding_if_vulnerable(
        self, db, scan, source_id, source_info, flow, analysis
    ):
        """Save a finding to DB if the analysis indicates a vulnerability."""
        if analysis.get("vulnerability_type") and analysis.get("vulnerability_type") != "none":
            finding = Finding(
                scan_id=scan.id,
                source_node_id=source_id,
                source_code=source_info.get("code", ""),
                source_location=f"{source_info.get('file', '?')}:{source_info.get('line', '?')}",
                flow_description=analysis.get("ai_analysis", ""),
                flow_code_snippets={"flow": flow.get("path", [])},
                vulnerability_type=analysis.get("vulnerability_type"),
                severity=analysis.get("severity", "info"),
                ai_analysis=analysis.get("ai_analysis", ""),
                confidence=analysis.get("confidence", 0.5),
            )
            db.add(finding)

    async def _get_scan(self, db: AsyncSession, scan_id: str) -> Scan | None:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        return result.scalar_one_or_none()

    async def _get_project(self, db: AsyncSession, project_id: str) -> Project | None:
        result = await db.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def _update_progress(
        self, db: AsyncSession, scan: Scan,
        status: str, progress: int, step: str
    ) -> None:
        """Update scan progress in DB and publish to Redis."""
        scan.status = status
        scan.progress = progress
        scan.current_step = step
        await db.commit()

        await self._publish_progress(str(scan.id), {
            "scan_id": str(scan.id),
            "status": status,
            "progress": progress,
            "current_step": step,
            "message": step,
        })

    async def _publish_progress(self, scan_id: str, data: dict) -> None:
        """Publish progress to Redis pub/sub."""
        try:
            r = redis.from_url(settings.REDIS_URL)
            channel = f"scan_progress:{scan_id}"
            await r.publish(channel, json.dumps(data))
            await r.close()
        except Exception as e:
            logger.warning(f"Failed to publish progress to Redis: {e}")

    def _group_by_file(self, candidates: dict) -> dict:
        """Group candidates by file path."""
        grouped = defaultdict(lambda: {"parameters": [], "calls": []})

        for param in candidates.get("parameters", []):
            file_path = param.get("file", "unknown")
            grouped[file_path]["parameters"].append(param)

        for call in candidates.get("calls", []):
            file_path = call.get("file", "unknown")
            grouped[file_path]["calls"].append(call)

        return dict(grouped)

    def _extract_method_snippets(
        self, file_cands: dict, project_path: str, file_path: str
    ) -> list[dict]:
        """Extract unique method snippets from candidates' enclosing methods.

        Uses method_code from Joern when available, falls back to reading
        a ±20 line window from the source file around the candidate.

        Returns:
            [{"method_name": str, "method_line": int, "code": str}, ...]
        """
        seen = set()
        snippets = []

        all_cands = file_cands.get("parameters", []) + file_cands.get("calls", [])

        for cand in all_cands:
            method_name = cand.get("method_name", "")
            method_line = cand.get("method_line", -1)
            method_code = cand.get("method_code", "")

            if method_code:
                key = (method_name, method_line)
                if key in seen:
                    continue
                seen.add(key)
                snippets.append({
                    "method_name": method_name,
                    "method_line": method_line,
                    "code": method_code,
                })
            else:
                # Fallback: read ±20 lines around the candidate
                cand_line = cand.get("line", -1)
                if cand_line < 0:
                    continue
                key = ("(around line)", cand_line)
                if key in seen:
                    continue
                seen.add(key)

                source = self._read_source_file(project_path, file_path)
                if source.startswith("// Source file not found"):
                    continue

                lines = source.splitlines()
                start = max(0, cand_line - 21)
                end = min(len(lines), cand_line + 20)
                window = "\n".join(lines[start:end])
                snippets.append({
                    "method_name": f"(around line {cand_line})",
                    "method_line": cand_line,
                    "code": window,
                })

        return snippets

    def _read_source_file(self, project_path: str, relative_path: str) -> str:
        """Read a source file from the project directory."""
        # Try the path as-is first, then relative to project
        candidates = [
            relative_path,
            os.path.join(project_path, relative_path),
            os.path.join(project_path, os.path.basename(relative_path)),
        ]

        for path in candidates:
            if os.path.isfile(path):
                try:
                    with open(path, "r", errors="replace") as f:
                        return f.read()
                except Exception:
                    continue

        return f"// Source file not found: {relative_path}"

    def _find_candidate_by_id(self, candidates: dict, node_id: int) -> dict | None:
        """Find a candidate node by its ID."""
        for param in candidates.get("parameters", []):
            if param.get("id") == node_id:
                return param
        for call in candidates.get("calls", []):
            if call.get("id") == node_id:
                return call
        return None

    def _extract_code_snippets(self, flow: dict) -> str:
        """Extract code snippets from a flow's path nodes."""
        snippets = []
        for node in flow.get("path", []):
            code = node.get("code", "")
            file = node.get("file", "?")
            line = node.get("line", "?")
            if code:
                snippets.append(f"// {file}:{line}\n{code}")
        return "\n\n".join(snippets)
