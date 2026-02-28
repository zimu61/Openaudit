"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getScan, getFindings, getReportDownloadUrl } from "@/lib/api";
import { connectScanWebSocket } from "@/lib/ws";
import type { Scan, Finding, ScanProgress } from "@/types";
import { ScanProgressBar } from "@/components/ScanProgress";
import { FindingCard } from "@/components/FindingCard";

export default function ScanResultsPage() {
  const params = useParams();
  const scanId = params.id as string;

  const [scan, setScan] = useState<Scan | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<ScanProgress | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const scanData = await getScan(scanId);
      setScan(scanData);
      if (
        scanData.status === "completed" ||
        scanData.status === "failed"
      ) {
        const findingsData = await getFindings(scanId);
        setFindings(findingsData.findings);
      }
    } catch {
      console.error("Failed to fetch scan data");
    } finally {
      setLoading(false);
    }
  }, [scanId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // WebSocket for live progress
  useEffect(() => {
    if (!scan) return;
    if (scan.status === "completed" || scan.status === "failed") return;

    const ws = connectScanWebSocket(
      scanId,
      (data) => {
        setProgress(data);
        setScan((prev) =>
          prev
            ? {
                ...prev,
                status: data.status as Scan["status"],
                progress: data.progress,
                current_step: data.current_step,
              }
            : prev,
        );
        // Fetch findings when scan completes
        if (data.status === "completed" || data.status === "failed") {
          fetchData();
        }
      },
      () => {
        // On disconnect, poll once for final state
        fetchData();
      },
    );

    return () => ws.close();
  }, [scan?.status, scanId, fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading scan...</div>
      </div>
    );
  }

  if (!scan) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400 text-lg">Scan not found</p>
        <Link href="/" className="text-blue-400 hover:underline mt-4 inline-block">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const isRunning =
    scan.status !== "completed" && scan.status !== "failed";

  const severityCounts = findings.reduce(
    (acc, f) => {
      const sev = f.severity || "info";
      acc[sev] = (acc[sev] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  return (
    <div>
      <div className="flex items-center gap-4 mb-8">
        <Link
          href={`/projects/${scan.project_id}`}
          className="text-gray-400 hover:text-white"
        >
          &larr; Back to Project
        </Link>
      </div>

      {/* Progress / Status */}
      <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold text-white">
            Scan {isRunning ? "in Progress" : scan.status === "completed" ? "Complete" : "Failed"}
          </h1>
          <span className="text-gray-400 text-sm">
            {new Date(scan.created_at).toLocaleString()}
          </span>
        </div>

        {isRunning && (
          <ScanProgressBar
            progress={progress?.progress ?? scan.progress}
            status={progress?.status ?? scan.status}
            currentStep={progress?.current_step ?? scan.current_step}
          />
        )}

        {scan.status === "failed" && scan.error_message && (
          <div className="p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
            {scan.error_message}
          </div>
        )}

        {scan.status === "completed" && (
          <div>
            <div className="flex items-center gap-4 mt-2">
              <div className="flex gap-4">
                {["critical", "high", "medium", "low", "info"].map((sev) =>
                  severityCounts[sev] ? (
                    <div key={sev} className="text-center">
                      <p className="text-2xl font-bold" style={{ color: `var(--severity-${sev}, #888)` }}>
                        {severityCounts[sev]}
                      </p>
                      <p className="text-xs text-gray-400 capitalize">{sev}</p>
                    </div>
                  ) : null,
                )}
                {findings.length === 0 && (
                  <p className="text-green-400">
                    No vulnerabilities found
                  </p>
                )}
              </div>
              <div className="ml-auto">
                <a
                  href={getReportDownloadUrl(scanId)}
                  download
                  className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors text-sm inline-block"
                >
                  Download PDF Report
                </a>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Findings */}
      {findings.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">
            Findings ({findings.length})
          </h2>
          <div className="space-y-4">
            {findings
              .sort((a, b) => {
                const order = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
                return (
                  (order[a.severity || "info"] ?? 5) -
                  (order[b.severity || "info"] ?? 5)
                );
              })
              .map((finding) => (
                <FindingCard key={finding.id} finding={finding} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
