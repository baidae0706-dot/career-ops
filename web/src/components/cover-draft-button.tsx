"use client";

import { uiLabel } from "@/lib/ui-labels";
import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { FileText, Loader2, Mail, RotateCcw, TriangleAlert } from "lucide-react";
import { useJobs } from "@/components/jobs/job-store";
import { CostBadge } from "@/components/cost/cost-badge";
import { pdfButtonState } from "@/lib/pdf-button-state.mjs";
import { COVER_TONES } from "@/lib/cover-tones.mjs";

// Fires the real career-ops `cover` mode (worker kind "cover") for THIS
// application. cover.md will not draft until the candidate answers its four
// Step 6 prompts, so the button opens those questions first. The draft lands in
// the run log. Rendering it to PDF is still the CLI's Step 9.
const QUESTIONS = [
  { name: "why", label: "为什么选择这个职位或公司？", hint: "写一两个角度，例如规模、使命、发展阶段，或你希望学到的东西。" },
  { name: "problem", label: "你想为他们解决什么问题？", hint: "调研时会将这一点与公司公开信息核对。" },
  { name: "approach", label: "入职第一天，你会如何着手？", hint: "一两句话即可。这是求职信中最具体的部分。" },
] as const;

const fieldClass =
  "mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand/50 focus:outline-none";

export function CoverDraftButton({ n, company }: { n: string; company: string }) {
  const { jobs, startJob } = useJobs();
  const [open, setOpen] = useState(false);
  const [savedBrief, setSavedBrief] = useState<Record<string, string> | null>(null);
  const job = useMemo(
    () => jobs.filter((j) => j.kind === "cover" && j.input === n).sort((a, b) => b.startedAt - a.startedAt)[0],
    [jobs, n],
  );
  // A cover run can finish with VERDICT 1/5 and no letter. Only treat a real
  // draft as ready; weak verdicts surface as a retry failure beside the form.
  const base = pdfButtonState(job, false);
  const weakDraft = job?.status === "done" && job.result?.score != null && job.result.score < 2;
  const state = weakDraft
    ? {
        kind: "idle" as const,
        failure: {
          jobId: job.id,
          reason: job.result?.summary || "求职信任务已结束，但没有可用草稿。",
        },
      }
    : base;

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const brief = Object.fromEntries(["why", "problem", "approach", "tone"].map((k) => [k, String(data.get(k) ?? "")]));
    setSavedBrief(brief);
    startJob({ title: `求职信 · ${company}`, subtitle: "为这个职位起草", kind: "cover", input: n, page: `/pipeline/${n}`, brief });
    setOpen(false);
  };

  if (state.kind === "running")
    return (
      <Link href={`/jobs/${state.jobId}`} className="inline-flex items-center justify-center gap-1.5 rounded-full border border-brand/40 bg-brand-soft px-3 py-1 text-xs font-medium text-brand max-sm:min-h-[44px]">
        <Loader2 className="size-3.5 motion-safe:animate-spin" /> 正在起草求职信…
      </Link>
    );

  return (
    <>
      {state.kind === "ready" && job ? (
        <span className="inline-flex items-center gap-1">
          <Link
            href={`/jobs/${job.id}`}
            className="inline-flex items-center justify-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-500/15 dark:text-emerald-400 max-sm:min-h-[44px]"
          >
            <FileText className="size-3.5" /> 查看求职信草稿
          </Link>
          <button
            onClick={() => setOpen((o) => !o)}
            title={"重新起草求职信"}
            aria-expanded={open}
            className="inline-flex items-center justify-center rounded-full p-1 text-faint transition-colors hover:text-brand max-sm:min-h-[44px] max-sm:min-w-[44px]"
          >
            <RotateCcw className="size-3" />
          </button>
        </span>
      ) : (
        <button
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="inline-flex items-center justify-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs font-medium text-muted transition-colors hover:border-brand/40 hover:text-brand max-sm:min-h-[44px]"
          title={"使用你的 AI CLI 为这个职位起草求职信"}
        >
          <Mail className="size-3.5" /> 起草求职信
        </button>
      )}
      {state.failure && (
        <Link
          href={`/jobs/${state.failure.jobId}`}
          role="alert"
          title={"打开运行日志"}
          className="inline-flex max-w-md items-start gap-1 text-xs text-red-700 hover:underline dark:text-red-400"
        >
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>求职信尚未起草。 {state.failure.reason}</span>
        </Link>
      )}
      {open && (
        <form onSubmit={submit} aria-label={"求职信问题"} className="basis-full rounded-2xl border border-border bg-surface/50 p-4">
          {QUESTIONS.map((q) => (
            <label key={q.name} className="mb-3 block text-sm font-medium text-foreground">
              {q.label}
              <span className="block text-xs font-normal text-muted">{q.hint}</span>
              <textarea name={q.name} required maxLength={1000} rows={2} defaultValue={savedBrief?.[q.name] ?? ""} className={fieldClass} />
            </label>
          ))}
          <label className="mb-4 block text-sm font-medium text-foreground">
            语气
            <select name="tone" defaultValue={savedBrief?.tone ?? "mirror"} className={fieldClass}>
              {Object.entries(COVER_TONES).map(([id, label]) => (
                <option key={id} value={id}>{uiLabel(label)}</option>
              ))}
            </select>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className="inline-flex items-center gap-1.5 rounded-full bg-brand px-3 py-1.5 text-xs font-medium text-brand-foreground shadow-sm transition-colors hover:bg-brand-200 max-sm:min-h-[44px]">
              <Mail className="size-3.5" /> 起草求职信
            </button>
            <CostBadge kind="spend" size="xs" />
            <button type="button" onClick={() => setOpen(false)} className="text-xs text-muted hover:text-brand max-sm:min-h-[44px]">
              取消
            </button>
          </div>
        </form>
      )}
    </>
  );
}
