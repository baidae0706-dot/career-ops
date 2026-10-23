import { cn } from "@/lib/cn";
import { coverageBand } from "@/lib/keyword-coverage.mjs";

export function CoverageMeter({ coverage, dropped }: { coverage: { present: string[]; missing: string[]; pct: number | null }; dropped: string[] }) {
  const total = coverage.present.length + coverage.missing.length;
  if (!total) {
    return <p className="rounded-2xl border border-border bg-surface/40 px-5 py-3 text-sm text-muted">这份报告没有提取出的关键词，暂不计算覆盖度。</p>;
  }
  const band = coverageBand(coverage.pct);
  const bar = { high: "bg-emerald-500", mid: "bg-amber-500", low: "bg-red-400", unknown: "bg-muted" }[band];
  return (
    <section aria-label={"关键词覆盖度"} className="rounded-2xl border border-border bg-surface/40 px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium text-foreground">职位关键词覆盖度</h2>
        <p className="font-mono text-sm text-foreground" data-testid="coverage-count">
          {coverage.present.length}/{total} · {coverage.pct}%
        </p>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted/20" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={coverage.pct ?? 0}>
        <div className={cn("h-full rounded-full transition-[width] duration-300", bar)} style={{ width: `${coverage.pct ?? 0}%` }} />
      </div>
      {dropped.length > 0 && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-300" role="status">
          你的编辑移除了 {dropped.join(", ")}，定制简历原本覆盖了这些词。
        </p>
      )}
      {coverage.missing.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          未覆盖： {coverage.missing.join(", ")}。只有在符合你的真实经历时才添加。
        </p>
      )}
    </section>
  );
}
