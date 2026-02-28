import type { ScanProgress } from "@/types";

export function connectScanWebSocket(
  scanId: string,
  onMessage: (data: ScanProgress) => void,
  onClose?: () => void,
): WebSocket {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  // WebSocket connects to backend directly via the host machine's mapped port.
  // In production, use the same host; for dev, backend is exposed on port 8000.
  const host = window.location.hostname;
  const wsPort = process.env.NEXT_PUBLIC_WS_PORT || "8000";
  const wsUrl = `${protocol}//${host}:${wsPort}/ws/scans/${scanId}`;

  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data: ScanProgress = JSON.parse(event.data);
      onMessage(data);
    } catch {
      console.error("Failed to parse WebSocket message:", event.data);
    }
  };

  ws.onclose = () => {
    onClose?.();
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  return ws;
}
