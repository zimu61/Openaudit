"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getProject, startScan, getProjectScans, getReportDownloadUrl } from "@/lib/api";
import type { Project, Scan } from "@/types";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [scans, setScans] = useState<Scan[]>([]);
  const [loading, setLoading] = useState(true);
  const [startingscan, setStartingscan] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [proj, scanData] = await Promise.all([
          getProject(projectId),
          getProjectScans(projectId),
        ]);
        setProject(proj);
        setScans(scanData.scans);
      } catch {
        console.error("Failed to fetch project");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [projectId]);

  const activeScan = scans.find(
    (s) => s.status !== "completed" && s.status !== "failed",
  );

  const handleStartScan = async () => {
    if (!project) return;
    setStartingscan(true);
    try {
      const scan = await startScan(project.id);
      router.push(`/scans/${scan.id}`);
    } catch (err) {
      console.error("Failed to start scan:", err);
      alert("Failed to start scan. Check if one is already running.");
    } finally {
      setStartingscan(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading project...</div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400 text-lg">Project not found</p>
        <Link href="/" className="text-blue-400 hover:underline mt-4 inline-block">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const statusColors: Record<string, string> = {
    uploaded: "bg-gray-600",
    scanning: "bg-yellow-600",
    completed: "bg-green-600",
    failed: "bg-red-600",
  };

  const scanStatusColors: Record<string, string> = {
    pending: "bg-gray-600",
    importing_cpg: "bg-yellow-600",
    extracting_candidates: "bg-yellow-600",
    identifying_sources: "bg-yellow-600",
    extracting_flows: "bg-yellow-600",
    analyzing: "bg-yellow-600",
    completed: "bg-green-600",
    failed: "bg-red-600",
  };

  return (
    <div>
      <div className="flex items-center gap-4 mb-8">
        <Link href="/" className="text-gray-400 hover:text-white">
          &larr; Back
        </Link>
      </div>

      <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-6 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">{project.name}</h1>
            <p className="text-gray-400 mt-1">{project.original_filename}</p>
          </div>
          <span
            className={`${statusColors[project.status] || "bg-gray-600"} text-white text-xs px-3 py-1 rounded-full`}
          >
            {project.status}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-4 mt-6">
          <div>
            <p className="text-gray-500 text-sm">Files</p>
            <p className="text-white text-lg font-semibold">
              {project.file_count}
            </p>
          </div>
          <div>
            <p className="text-gray-500 text-sm">Language</p>
            <p className="text-white text-lg font-semibold">
              {project.language || "Auto-detect"}
            </p>
          </div>
          <div>
            <p className="text-gray-500 text-sm">Created</p>
            <p className="text-white text-lg font-semibold">
              {new Date(project.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-4">
          {activeScan ? (
            <Link
              href={`/scans/${activeScan.id}`}
              className="bg-yellow-600 hover:bg-yellow-700 text-white px-6 py-2 rounded-lg transition-colors inline-block"
            >
              View Live Scan Progress
            </Link>
          ) : (
            <button
              onClick={handleStartScan}
              disabled={startingscan}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg transition-colors"
            >
              {startingscan ? "Starting..." : "Start Security Scan"}
            </button>
          )}
        </div>
      </div>

      {/* Scan History */}
      {scans.length > 0 && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Scan History ({scans.length})
          </h2>
          <div className="space-y-3">
            {scans.map((scan) => (
              <div
                key={scan.id}
                className="flex items-center justify-between p-4 bg-[var(--background)] rounded-lg border border-[var(--card-border)] hover:border-gray-600 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <span
                    className={`${scanStatusColors[scan.status] || "bg-gray-600"} text-white text-xs px-2 py-0.5 rounded-full`}
                  >
                    {scan.status}
                  </span>
                  <span className="text-gray-400 text-sm">
                    {new Date(scan.created_at).toLocaleString()}
                  </span>
                  {scan.completed_at && (
                    <span className="text-gray-500 text-xs">
                      Completed {new Date(scan.completed_at).toLocaleString()}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <Link
                    href={`/scans/${scan.id}`}
                    className="text-blue-400 hover:text-blue-300 text-sm"
                  >
                    View Results
                  </Link>
                  {scan.status === "completed" && (
                    <a
                      href={getReportDownloadUrl(scan.id)}
                      download
                      onClick={(e) => e.stopPropagation()}
                      className="text-green-400 hover:text-green-300 text-sm"
                    >
                      Download Report
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
