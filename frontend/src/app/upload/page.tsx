"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { uploadProject } from "@/lib/api";
import { FileUpload } from "@/components/FileUpload";

export default function UploadPage() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");

  const handleUpload = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const project = await uploadProject(file, projectName || undefined);
        router.push(`/projects/${project.id}`);
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Upload failed";
        setError(msg);
      } finally {
        setUploading(false);
      }
    },
    [projectName, router],
  );

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Upload Project</h1>

      <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-6">
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Project Name (optional)
          </label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Derived from filename if empty"
            className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        <FileUpload onUpload={handleUpload} uploading={uploading} />

        {error && (
          <div className="mt-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
      </div>

      <p className="text-gray-500 text-sm mt-4">
        Supported formats: .zip, .tar.gz, .tgz (max 100MB)
      </p>
    </div>
  );
}
