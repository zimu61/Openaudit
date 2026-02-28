import Link from "next/link";
import type { Project } from "@/types";

interface ProjectCardProps {
  project: Project;
  onDelete: (id: string) => void;
}

const statusConfig: Record<string, { color: string; bg: string }> = {
  uploaded: { color: "text-gray-300", bg: "bg-gray-600" },
  scanning: { color: "text-yellow-300", bg: "bg-yellow-600" },
  completed: { color: "text-green-300", bg: "bg-green-600" },
  failed: { color: "text-red-300", bg: "bg-red-600" },
};

export function ProjectCard({ project, onDelete }: ProjectCardProps) {
  const status = statusConfig[project.status] || statusConfig.uploaded;

  return (
    <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 hover:border-gray-600 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <Link
          href={`/projects/${project.id}`}
          className="text-lg font-semibold text-white hover:text-blue-400 transition-colors"
        >
          {project.name}
        </Link>
        <span
          className={`${status.bg} text-white text-xs px-2 py-0.5 rounded-full`}
        >
          {project.status}
        </span>
      </div>

      <p className="text-gray-400 text-sm mb-4 truncate">
        {project.original_filename}
      </p>

      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">
          {project.file_count} files
        </span>
        <div className="flex items-center gap-3">
          <Link
            href={`/projects/${project.id}`}
            className="text-blue-400 hover:text-blue-300"
          >
            View
          </Link>
          {project.status === "completed" && (
            <Link
              href={`/projects/${project.id}`}
              className="text-green-400 hover:text-green-300"
            >
              Reports
            </Link>
          )}
          <button
            onClick={() => onDelete(project.id)}
            className="text-red-400 hover:text-red-300"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
