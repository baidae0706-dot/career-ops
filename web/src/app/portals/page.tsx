import { Radar } from "lucide-react";
import path from "node:path";
import { PortalsView } from "@/components/portals-view";
import { careerOpsRoot } from "@/lib/career-ops";
import { loadPortalsDocument, watchedCompanies, type WatchedCompany } from "@/lib/portals-config.mjs";

export const dynamic = "force-dynamic";

function readWatched(): { watched: WatchedCompany[]; error: string | null } {
  const root = careerOpsRoot();
  try {
    const { doc, seeded } = loadPortalsDocument(path.join(root, "portals.yml"), path.join(root, "templates", "portals.example.yml"));
    return { watched: seeded ? [] : watchedCompanies(doc), error: null };
  } catch (e) {
    return { watched: [], error: e instanceof Error ? e.message : String(e) };
  }
}

export default function PortalsPage() {
  const { watched, error } = readWatched();
  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3">
        <Radar className="size-6 text-brand" />
        <h1 className="font-display text-2xl tracking-tight text-landing">{"招聘门户"}</h1>
      </div>
      <p className="mt-1.5 max-w-xl text-sm text-muted">{"career-ops 关注这些公司的新职位。运行健康检查可发现失效的招聘网站；链接损坏会导致该公司在后续扫描中被跳过。"}</p>
      <p className="mt-1.5 text-xs text-faint">{"配置文件："}<code className="text-muted">portals.yml</code>{"，可直接编辑，也可让助手修改。"}</p>
      {error && (
        <p role="alert" className="mt-4 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-600 dark:text-rose-400">
          无法读取 <code>portals.yml</code>: {error}
        </p>
      )}
      <div className="mt-6">
        <PortalsView watched={watched} />
      </div>
    </div>
  );
}
