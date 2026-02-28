import os
import uuid
import shutil
import zipfile
import tarfile
from pathlib import Path

import aiofiles
from fastapi import UploadFile


class FileService:
    async def save_and_extract(
        self, file: UploadFile, upload_dir: str, workspace_dir: str
    ) -> tuple[str, str, int]:
        """Save uploaded file and extract it. Returns (upload_path, extracted_path, file_count)."""
        project_id = str(uuid.uuid4())
        upload_path = Path(upload_dir) / project_id
        upload_path.mkdir(parents=True, exist_ok=True)

        # Save the uploaded file
        file_path = upload_path / file.filename
        async with aiofiles.open(str(file_path), "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                await f.write(chunk)

        # Extract to workspace
        extract_path = Path(workspace_dir) / project_id
        extract_path.mkdir(parents=True, exist_ok=True)

        filename_lower = file.filename.lower()
        if filename_lower.endswith(".zip"):
            self._extract_zip(str(file_path), str(extract_path))
        elif filename_lower.endswith((".tar.gz", ".tgz")):
            self._extract_tar(str(file_path), str(extract_path))
        else:
            raise ValueError(f"Unsupported archive format: {file.filename}")

        # Flatten single top-level directory
        extract_path = self._flatten_if_single_dir(extract_path)

        # Count source files
        file_count = self._count_source_files(extract_path)

        return str(upload_path), str(extract_path), file_count

    def _extract_zip(self, file_path: str, extract_path: str) -> None:
        with zipfile.ZipFile(file_path, "r") as zf:
            # Security: check for path traversal
            for member in zf.namelist():
                member_path = Path(extract_path) / member
                if not str(member_path.resolve()).startswith(
                    str(Path(extract_path).resolve())
                ):
                    raise ValueError(f"Zip path traversal detected: {member}")
            zf.extractall(extract_path)

    def _extract_tar(self, file_path: str, extract_path: str) -> None:
        with tarfile.open(file_path, "r:gz") as tf:
            # Security: check for path traversal
            for member in tf.getmembers():
                member_path = Path(extract_path) / member.name
                if not str(member_path.resolve()).startswith(
                    str(Path(extract_path).resolve())
                ):
                    raise ValueError(f"Tar path traversal detected: {member.name}")
            tf.extractall(extract_path, filter="data")

    def _flatten_if_single_dir(self, extract_path: Path) -> Path:
        """If extraction produced a single top-level directory, use it as the root."""
        entries = list(extract_path.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        return extract_path

    def _count_source_files(self, path: Path) -> int:
        """Count source code files in the extracted directory."""
        source_extensions = {
            ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
            ".java", ".py", ".js", ".ts", ".jsx", ".tsx",
            ".go", ".rs", ".rb", ".php", ".cs", ".swift",
            ".kt", ".kts", ".scala", ".m", ".mm",
        }
        count = 0
        for root, dirs, files in os.walk(path):
            # Skip hidden dirs and common non-source dirs
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in ("node_modules", "__pycache__", "vendor", "target", "build")
            ]
            for f in files:
                if Path(f).suffix.lower() in source_extensions:
                    count += 1
        return count
