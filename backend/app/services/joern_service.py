import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class JoernService:
    def __init__(self):
        self.joern_cli = settings.JOERN_CLI_PATH
        self.joern_parse = settings.JOERN_PARSE_PATH
        self.import_timeout = settings.JOERN_IMPORT_TIMEOUT
        self.query_timeout = settings.JOERN_QUERY_TIMEOUT

    async def import_cpg(self, project_path: str, workspace: str) -> str:
        """Run joern-parse to create CPG from source code. Returns cpg_path."""
        cpg_path = os.path.join(workspace, "cpg.bin")

        cmd = [
            self.joern_parse,
            project_path,
            "--output", cpg_path,
        ]

        logger.info(f"Importing CPG: {' '.join(cmd)}")
        stdout, stderr = await self._run_command(cmd, timeout=self.import_timeout)

        if not os.path.exists(cpg_path):
            raise RuntimeError(
                f"CPG import failed. No output at {cpg_path}. stderr: {stderr}"
            )

        logger.info(f"CPG created at {cpg_path}")
        return cpg_path

    async def extract_candidates(self, cpg_path: str) -> dict:
        """Extract function parameters and calls from CPG.

        Returns:
            {
                "parameters": [{
                    "id": int, "name": str, "method": str, "file": str,
                    "line": int, "type": str,
                    "method_code": str, "method_name": str,
                    "method_line": int, "method_line_end": int
                }, ...],
                "calls": [{
                    "id": int, "name": str, "file": str, "line": int,
                    "code": str,
                    "method_code": str, "method_name": str,
                    "method_line": int, "method_line_end": int
                }, ...]
            }

        The method_* fields describe the enclosing method/function for each
        candidate. method_code contains the full body (truncated at 8000 chars).
        These fields may be empty/``-1`` when Joern cannot resolve the enclosing
        method (e.g. top-level code or macros).
        """
        query_path = self._get_query_path("extract_candidates.sc")
        result = await self._run_joern_query(cpg_path, query_path)
        return self._parse_json_output(result)

    async def extract_flows(self, cpg_path: str, source_ids: list[int]) -> list[dict]:
        """Extract data flows from given source node IDs.

        Returns list of flow dicts with nodes and edges.
        """
        query_path = self._get_query_path("extract_flows.sc")

        # Write source IDs to a temp file for the query to read
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(source_ids, f)
            ids_file = f.name

        try:
            result = await self._run_joern_query(
                cpg_path, query_path, extra_args=["--param", f"sourceIdsFile={ids_file}"]
            )
            return self._parse_json_output(result)
        finally:
            os.unlink(ids_file)

    async def get_node_code(self, cpg_path: str, node_ids: list[int]) -> dict:
        """Get source code for specific nodes. Returns {node_id: code_string}."""
        if not node_ids:
            return {}

        # Build inline query to get code for node IDs
        ids_str = ",".join(str(i) for i in node_ids)
        script = r'''
        import io.shiftleft.semanticcpg.language._
        import scala.util.{Try, Success, Failure}

        val ids = List(%s)
        val result = ids.flatMap { id =>
            cpg.all.id(id).l.map { node =>
                val code = node.properties.getOrElse("CODE", "").toString.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
                "\"" + id.toString + "\": \"" + code + "\""
            }
        }
        println("{" + result.mkString(",") + "}")
        ''' % ids_str

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sc", delete=False
        ) as f:
            f.write(script)
            script_path = f.name

        try:
            result = await self._run_joern_query(cpg_path, script_path)
            return self._parse_json_output(result)
        finally:
            os.unlink(script_path)

    def _get_query_path(self, filename: str) -> str:
        """Get path to a Joern query script."""
        query_dir = Path(__file__).parent.parent / "joern_queries"
        path = query_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Joern query script not found: {path}")
        return str(path)

    async def _run_joern_query(
        self, cpg_path: str, script_path: str, extra_args: list[str] | None = None
    ) -> str:
        """Run a Joern query script against a CPG."""
        cmd = [
            self.joern_cli,
            "--script", script_path,
            "--param", f"cpgFile={cpg_path}",
        ]
        if extra_args:
            cmd.extend(extra_args)

        logger.info(f"Running Joern query: {' '.join(cmd)}")
        stdout, stderr = await self._run_command(cmd, timeout=self.query_timeout)
        return stdout

    async def _run_command(
        self, cmd: list[str], timeout: int = 120
    ) -> tuple[str, str]:
        """Run a subprocess command asynchronously with timeout."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                logger.error(
                    f"Command failed (rc={process.returncode}): {' '.join(cmd)}\n"
                    f"stderr: {stderr_str}"
                )
                raise RuntimeError(
                    f"Command failed with return code {process.returncode}: {stderr_str}"
                )

            return stdout_str, stderr_str

        except asyncio.TimeoutError:
            process.kill()
            raise TimeoutError(
                f"Command timed out after {timeout}s: {' '.join(cmd)}"
            )

    def _parse_json_output(self, output: str) -> dict | list:
        """Parse JSON from Joern stdout. Handles extra output before/after JSON."""
        lines = output.strip().split("\n")
        decoder = json.JSONDecoder()

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped[0] not in "{[":
                continue
            # Skip Joern log lines like [INFO ], [WARN ], [ERROR ]
            if stripped[0] == "[" and not stripped.startswith("[{") and not stripped.startswith("[\"") and stripped != "[]":
                continue

            remaining = "\n".join(lines[i:])
            try:
                result, _ = decoder.raw_decode(remaining)
                return result
            except json.JSONDecodeError:
                continue

        logger.warning(f"Could not parse JSON from Joern output: {output[:500]}")
        return {}
