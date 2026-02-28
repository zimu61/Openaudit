"use client";

import { useState } from "react";
import type { Finding } from "@/types";
import { CodeViewer } from "@/components/CodeViewer";

interface FindingCardProps {
  finding: Finding;
}

const severityColors: Record<string, string> = {
  critical: "border-red-600 bg-red-900/20",
  high: "border-orange-600 bg-orange-900/20",
  medium: "border-yellow-600 bg-yellow-900/20",
  low: "border-blue-600 bg-blue-900/20",
  info: "border-gray-600 bg-gray-900/20",
};

const severityBadge: Record<string, string> = {
  critical: "bg-red-600",
  high: "bg-orange-600",
  medium: "bg-yellow-600",
  low: "bg-blue-600",
  info: "bg-gray-600",
};

export function FindingCard({ finding }: FindingCardProps) {
  const [expanded, setExpanded] = useState(false);
  const severity = finding.severity || "info";
  const borderClass = severityColors[severity] || severityColors.info;
  const badgeClass = severityBadge[severity] || severityBadge.info;

  return (
    <div
      className={`border rounded-xl p-5 ${borderClass} cursor-pointer`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <span
              className={`${badgeClass} text-white text-xs px-2 py-0.5 rounded-full uppercase font-medium`}
            >
              {severity}
            </span>
            <span className="text-white font-semibold">
              {finding.vulnerability_type || "Unknown"}
            </span>
            {finding.confidence != null && (
              <span className="text-gray-400 text-xs">
                {Math.round(finding.confidence * 100)}% confidence
              </span>
            )}
          </div>
          <p className="text-gray-400 text-sm">
            {finding.source_location}
          </p>
        </div>
        <span className="text-gray-500 text-xl">
          {expanded ? "\u25B2" : "\u25BC"}
        </span>
      </div>

      {expanded && (
        <div className="mt-4 space-y-4">
          {finding.ai_analysis && (
            <div>
              <h4 className="text-sm font-medium text-gray-300 mb-2">
                Analysis
              </h4>
              <p className="text-gray-400 text-sm whitespace-pre-wrap">
                {finding.ai_analysis}
              </p>
            </div>
          )}

          {finding.source_code && (
            <div>
              <h4 className="text-sm font-medium text-gray-300 mb-2">
                Source
              </h4>
              <CodeViewer
                code={finding.source_code}
                location={finding.source_location || undefined}
              />
            </div>
          )}

          {finding.flow_code_snippets?.flow &&
            finding.flow_code_snippets.flow.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">
                  Data Flow
                </h4>
                <div className="space-y-2">
                  {finding.flow_code_snippets.flow.map((node, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-3 text-sm"
                    >
                      <span className="text-gray-500 font-mono w-6 text-right flex-shrink-0">
                        {i + 1}.
                      </span>
                      <div>
                        <span className="text-gray-500">
                          {node.file}:{node.line}
                        </span>
                        <CodeViewer code={node.code || ""} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
        </div>
      )}
    </div>
  );
}
