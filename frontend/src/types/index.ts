export interface Project {
  id: string;
  name: string;
  original_filename: string;
  upload_path: string;
  language: string | null;
  file_count: number;
  status: "uploaded" | "scanning" | "completed" | "failed";
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface Scan {
  id: string;
  project_id: string;
  status:
    | "pending"
    | "importing_cpg"
    | "extracting_candidates"
    | "identifying_sources"
    | "extracting_flows"
    | "analyzing"
    | "completed"
    | "failed";
  progress: number;
  current_step: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Finding {
  id: string;
  scan_id: string;
  source_node_id: number | null;
  source_code: string | null;
  source_location: string | null;
  flow_description: string | null;
  flow_code_snippets: {
    flow?: Array<{
      id?: number;
      code?: string;
      file?: string;
      line?: number;
    }>;
  } | null;
  vulnerability_type: string | null;
  severity: "critical" | "high" | "medium" | "low" | "info" | null;
  ai_analysis: string | null;
  confidence: number | null;
  created_at: string;
}

export interface FindingListResponse {
  findings: Finding[];
  total: number;
}

export interface ScanListResponse {
  scans: Scan[];
  total: number;
}

export interface ScanProgress {
  scan_id: string;
  status: string;
  progress: number;
  current_step: string | null;
  message: string | null;
}
