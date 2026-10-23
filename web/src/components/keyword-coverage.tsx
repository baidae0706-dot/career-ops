"use client";

import { uiLabel } from "@/lib/ui-labels";
import { useEffect, useState } from "react";
import { ScanSearch } from "lucide-react";
import { coverageModel, coverageBand } from "@/lib/keyword-coverage.mjs";
import type { CoverageModel } from "@/lib/keyword-coverage.mjs";

// ATS keyword coverage for this report's JD against the CV, from the core's
// keyword-match.mjs via /api/keyword-match.
//
// Sits on the report because that is where the decision is — "is my CV going to
// read as a match for this JD?" is asked while looking at the offer, not on a
// separate page.
//
// DIAGNOSTIC, and the UI has to keep it that way. There is no pass mark and no
// red state: the script's own header states the project rule that keywords get
// reformulated, never fabricated, and a failing grade is what pushes someone to
// paste the missing terms in verbatim.
const BAND_CLASS: Record<string, string> = {
  high: "text-brand-text",
  mid: "text-foreground",
  low: "text-foreground",
  unknown: "text-faint",
};

const REASON_COPY: Record<string, string> = {
  "no-keywords": "这份报告没有提取关键词，暂时无法与简历比较。",
  "no-script": "当前 career-ops 中缺少 keyword-match.mjs。",
  "no-report": "未找到报告文件。",
  failed: "关键词检查未完成。",
  unparseable: "关键词检查返回了无法读取的结果。",
  unavailable: "关键词检查暂不可用。",
};

export function KeywordCoverage({ reportId }: { reportId: string }) {
  const [model, setModel] = useState<CoverageModel | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`/api/keyword-match?report=${encodeURIComponent(reportId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => alive && setModel(coverageModel(d)))
      .catch(() => alive && setModel(coverageModel(null)));
    return () => {
      alive = false;
    };
  }, [reportId]);

  if (!model) {
    return (
      <section className="mt-8 rounded-2xl border border-border bg-surface/40 px-5 py-4">
        <div className="h-5 w-44 animate-pulse rounded bg-muted/25" aria-hidden />
        <div className="mt-3 h-16 w-full animate-pulse rounded bg-muted/25" aria-hidden />
      </section>
    );
  }

  if (!model.available) {
    // Stated, not hidden: "no keywords block" is a fact about this report that
    // tells the reader what to do next, and silently omitting the panel would
    // read as the check having passed.
    return (
      <section className="mt-8 rounded-2xl border border-border bg-surface/40 px-5 py-4">
        <Header />
        <p className="mt-2 text-sm text-muted">{REASON_COPY[model.reason ?? "unavailable"] ?? REASON_COPY.unavailable}</p>
      </section>
    );
  }

  const band = coverageBand(model.coveragePct);

  return (
    <section className="mt-8 rounded-2xl border border-border bg-surface/40 px-5 py-4">
      <Header />

      <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={`text-3xl tabular-nums ${BAND_CLASS[band]}`}>
          {model.coveragePct === null ? "—" : `${model.coveragePct}%`}
        </span>
        <span className="text-sm text-muted">
          共 {model.total} 个职位关键词，其中 {model.presentCount} 个已在你的简历中找到
        </span>
      </div>

      <div className="mt-4 grid gap-3">
        {model.tiers.map((tier) =>
          tier.terms.length === 0 ? null : (
            <div key={tier.key}>
              <p className="text-xs uppercase tracking-wide text-faint">
                {uiLabel(tier.label)} <span className="normal-case tracking-normal">· {uiLabel(tier.hint)}</span>
              </p>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {tier.terms.map((term, i) => (
                  <li
                    key={`${i}:${term}`}
                    className={
                      tier.key === "missing"
                        ? "rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted"
                        : "rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-foreground"
                    }
                  >
                    {term}
                  </li>
                ))}
              </ul>
            </div>
          ),
        )}
      </div>

      <p className="mt-4 text-xs text-faint">
        仅用于诊断，此处不会修改你的简历。可以调整真实经历的表述，但不要添加缺乏事实依据的关键词。
      </p>
    </section>
  );
}

function Header() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <ScanSearch className="size-4 text-brand" />
      <h2 className="font-display text-base text-landing">ATS 关键词覆盖度</h2>
      <span className="text-xs text-faint">职位描述与简历的对比</span>
    </div>
  );
}
