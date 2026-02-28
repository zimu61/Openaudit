interface CodeViewerProps {
  code: string;
  location?: string;
}

export function CodeViewer({ code, location }: CodeViewerProps) {
  return (
    <div className="bg-[#1a1a2e] border border-gray-700 rounded-lg overflow-hidden">
      {location && (
        <div className="bg-[#16213e] px-3 py-1.5 text-xs text-gray-400 border-b border-gray-700 font-mono">
          {location}
        </div>
      )}
      <pre className="p-3 text-sm text-gray-300 overflow-x-auto font-mono">
        <code>{code}</code>
      </pre>
    </div>
  );
}
