import axios from "axios";
import type {
  Project,
  ProjectListResponse,
  Scan,
  Finding,
  FindingListResponse,
  ScanListResponse,
} from "@/types";

const api = axios.create({
  baseURL: "/api",
});

export async function uploadProject(
  file: File,
  name?: string,
): Promise<Project> {
  const formData = new FormData();
  formData.append("file", file);
  if (name) formData.append("name", name);
  const { data } = await api.post<Project>("/projects/upload", formData);
  return data;
}

export async function listProjects(
  skip = 0,
  limit = 20,
): Promise<ProjectListResponse> {
  const { data } = await api.get<ProjectListResponse>("/projects", {
    params: { skip, limit },
  });
  return data;
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await api.get<Project>(`/projects/${id}`);
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/projects/${id}`);
}

export async function startScan(projectId: string): Promise<Scan> {
  const { data } = await api.post<Scan>(`/projects/${projectId}/scan`);
  return data;
}

export async function getScan(id: string): Promise<Scan> {
  const { data } = await api.get<Scan>(`/scans/${id}`);
  return data;
}

export async function getFindings(
  scanId: string,
  skip = 0,
  limit = 50,
  severity?: string,
): Promise<FindingListResponse> {
  const { data } = await api.get<FindingListResponse>(
    `/scans/${scanId}/findings`,
    { params: { skip, limit, severity } },
  );
  return data;
}

export async function getProjectScans(
  projectId: string,
  skip = 0,
  limit = 20,
): Promise<ScanListResponse> {
  const { data } = await api.get<ScanListResponse>(
    `/projects/${projectId}/scans`,
    { params: { skip, limit } },
  );
  return data;
}

export function getReportDownloadUrl(scanId: string): string {
  return `/api/scans/${scanId}/report`;
}
