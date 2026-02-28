interface ScanProgressBarProps {
  progress: number;
  status: string;
  currentStep: string | null;
}

const statusLabels: Record<string, string> = {
  pending: "Queued",
  importing_cpg: "Importing Code",
  extracting_candidates: "Extracting Candidates",
  identifying_sources: "AI: Identifying Sources",
  extracting_flows: "Extracting Data Flows",
  analyzing: "AI: Analyzing Vulnerabilities",
  completed: "Complete",
  failed: "Failed",
};

export function ScanProgressBar({
  progress,
  status,
  currentStep,
}: ScanProgressBarProps) {
  const label = statusLabels[status] || status;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-300">{label}</span>
        <span className="text-sm text-gray-400">{progress}%</span>
      </div>
      <div className="w-full bg-gray-800 rounded-full h-2.5">
        <div
          className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      {currentStep && (
        <p className="text-xs text-gray-500 mt-2">{currentStep}</p>
      )}
    </div>
  );
}
