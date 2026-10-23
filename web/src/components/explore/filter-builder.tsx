"use client";

import { useState } from "react";
import { X, Ban, Clock, MapPin, ChevronDown, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/cn";
import { ATS_LABEL, ATS_SOURCES, cleanChips, type AtsSource, type ExploreFilters } from "@/lib/explore";

import { CHINA_PRESET, CHINA_SOURCES, EMPLOYER_LABEL } from "@/lib/employer-preset.mjs";
import type { EmployerSource } from "@/lib/explore";

const RECENCY = [
  { label: "24 小时", days: 1 },
  { label: "3 天", days: 3 },
  { label: "7 天", days: 7 },
  { label: "14 天", days: 14 },
  { label: "30 天", days: 30 },
];

const STYLE = `
.co-fb__chip{display:inline-flex;align-items:center;gap:.3rem;border-radius:999px;padding:.2rem .5rem .2rem .6rem;font-size:12.5px;line-height:1.2;border:1px solid transparent}
.co-fb__chip button{display:inline-flex;opacity:.6;transition:opacity .15s}
.co-fb__chip button:hover{opacity:1}
.co-fb__chip.inc{color:hsl(26 78% 42%);background:hsl(26 73% 51% / .11);border-color:hsl(26 73% 51% / .26)}
html.dark .co-fb__chip.inc{color:hsl(26 86% 70%);background:hsl(26 80% 55% / .14);border-color:hsl(26 80% 55% / .28)}
.co-fb__field{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;min-height:2.6rem;padding:.45rem .55rem;border-radius:.7rem}
.co-fb__field input{flex:1;min-width:7rem;background:transparent;border:none;outline:none;font-size:13.5px;color:inherit}
.co-fb__field input::placeholder{color:var(--co-faint,hsl(0 0% 60%))}
@media (max-width:639px){.co-fb__chip button{min-width:44px;min-height:44px;justify-content:center}.co-fb__chip{min-height:44px}.co-fb__field{min-height:44px}.co-fb__field input{min-height:32px}}
`;

function KeywordField({
  values,
  tone,
  placeholder,
  ariaLabel,
  onChange,
}: {
  values: string[];
  tone: "inc" | "exc";
  placeholder: string;
  ariaLabel?: string;
  onChange: (v: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  // Split only on UNAMBIGUOUS item separators (comma / newline / semicolon) — never
  // bare spaces, which are legitimate inside multi-word entries ("AI platform",
  // "New York", "Costa Rica"). A space-only paste stays one chip on purpose (#1147).
  const commit = (text: string) => {
    const parts = text.split(/[,\n;\t\r]+/);
    const next = cleanChips([...values, ...parts]);
    onChange(next);
    setDraft("");
  };
  return (
    <div className={cn("co-fb__field border border-border bg-surface/40 focus-within:border-brand/40 transition-colors")}>
      {values.map((v) => (
        <span key={v} className={cn("co-fb__chip", tone === "inc" ? "inc" : "border-border bg-surface-hover text-muted")}>
          {tone === "exc" && <Ban className="size-3 opacity-70" />}
          {v}
          <button type="button" aria-label={`移除 ${v}`} onClick={() => onChange(values.filter((x) => x !== v))}>
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        aria-label={ariaLabel}
        value={draft}
        onChange={(e) => {
          const val = e.target.value;
          if (/[,\n;\t\r]$/.test(val)) commit(val);
          else setDraft(val);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && draft.trim()) {
            e.preventDefault();
            commit(draft);
          } else if (e.key === "Backspace" && !draft && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
        onPaste={(e) => {
          e.preventDefault();
          const text = e.clipboardData.getData("text");
          const merged = draft + text;
          // Only commit to chips when the paste contains item separators.
          // A plain-text paste (e.g. pasting "-EMEA" after typing "Remote")
          // stays in the input field so the user can keep editing.
          if (/[,;\n\t\r]/.test(text)) commit(merged);
          else setDraft(merged);
        }}
        onBlur={() => draft.trim() && commit(draft)}
        placeholder={values.length ? "" : placeholder}
      />
    </div>
  );
}

function Label({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-1.5 flex items-baseline justify-between gap-4">
      <span className="text-[13px] font-medium text-foreground">{children}</span>
      {hint && <span className="ml-4 text-right text-[11px] text-faint">{hint}</span>}
    </div>
  );
}

export function FilterBuilder({
  filters,
  onChange,
  seededFrom = [],
  disabled = false,
}: {
  filters: ExploreFilters;
  onChange: (f: ExploreFilters) => void;
  seededFrom?: string[];
  disabled?: boolean;
}) {
  const employer = filters.preset === CHINA_PRESET;
  const [advanced, setAdvanced] = useState(false);
  const set = (patch: Partial<ExploreFilters>) => onChange({ ...filters, ...patch });
  const toggleAts = (a: AtsSource) => {
    const has = filters.ats.includes(a);
    const next = has ? filters.ats.filter((x) => x !== a) : [...filters.ats, a];
    set({ ats: next.length ? next : filters.ats });
  };

  return (
    <fieldset disabled={disabled} className="space-y-4">
      <style>{STYLE}</style>
      <fieldset>
        <legend className="mb-1.5 text-[13px] font-medium">发现来源</legend>
        <div className="flex flex-wrap gap-4 text-sm">
          <label className="inline-flex items-center gap-2"><input type="radio" name="explore-preset" checked={!employer} onChange={() => set({ preset: undefined })} />公开 ATS 招聘网络</label>
          <label className="inline-flex items-center gap-2"><input type="radio" name="explore-preset" checked={employer} onChange={() => set({ preset: CHINA_PRESET, employers: [...CHINA_SOURCES] as EmployerSource[] })} />中国雇主预设</label>
        </div>
      </fieldset>
      {employer && <fieldset aria-describedby="employer-scope employer-selection">
        <legend className="mb-2 text-[13px] font-medium">雇主</legend>
        <div className="flex flex-wrap gap-4">{CHINA_SOURCES.map(id => <label key={id} className="inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={filters.employers?.includes(id as EmployerSource) ?? false} onChange={e => set({ employers: e.target.checked ? [...(filters.employers ?? []), id as EmployerSource] : (filters.employers ?? []).filter(x => x !== id) })} />{EMPLOYER_LABEL[id as keyof typeof EMPLOYER_LABEL]}
        </label>)}</div>
        <p id="employer-selection" className="mt-2 text-xs text-muted">{filters.employers?.length ? "只扫描选定的雇主。" : "请至少选择一家雇主再开始扫描。"}</p>
        <p id="employer-scope" className="mt-2 text-xs text-muted">选择雇主不代表职位一定面向中国大陆、技术岗或社招。请核对职位原文。职位和地点关键词可留空；地点未知的职位可能保留，标题含远程信息的职位也可能匹配。地点只按关键词过滤，不检查应聘资格。此预设没有发布日期截止限制，其他 ATS 筛选条件不生效。每家雇主最多扫描 10 页；达到上限或来源异常时会标记为未完成。</p>
      </fieldset>}

      <div>
        <Label hint={filters.positive.length === 0 ? (employer ? "留空表示所有职位名称" : "留空表示所有新职位") : undefined}>想找的职位</Label>
        <KeywordField ariaLabel="想找的职位" values={filters.positive} tone="inc" placeholder={"AI 平台、机器学习基础设施、资深工程师…"} onChange={(v) => set({ positive: v })} />
        {!employer && seededFrom.length > 0 && filters.positive.length > 0 && (
          <p className="mt-1 text-[11px] text-faint">初始值来自你的 {seededFrom.join(" + ")} ，可自由修改。</p>
        )}
      </div>

      {!employer && <div>
        <Label>排除</Label>
        <KeywordField ariaLabel="排除职位" values={filters.negative} tone="exc" placeholder={"经理、销售、合同工…"} onChange={(v) => set({ negative: v })} />
      </div>}

      <div>
        <Label hint="匹配城市、地区、国家或远程">
          <span className="inline-flex items-center gap-1.5">
            <MapPin className="size-3.5 text-muted" />{"城市或地点"}</span>
        </Label>
        <KeywordField
          values={filters.allow}
          tone="inc"
          placeholder="多伦多、纽约、远程…"
          ariaLabel="城市或地点"
          onChange={(v) => set({ allow: v })}
        />
      </div>

      {!employer && <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
        <div className="min-w-[18rem]">
          <Label hint="此时间范围内发布的职位">
            <span className="inline-flex items-center gap-1.5">
              <Clock className="size-3.5 text-muted" />{"发布时间"}</span>
          </Label>
          <div className="inline-flex rounded-lg border border-border bg-surface/40 p-0.5">
            {RECENCY.map((r) => (
              <button
                key={r.days}
                type="button"
                onClick={() => set({ sinceDays: r.days })}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors max-sm:min-h-[44px]",
                  filters.sinceDays === r.days ? "bg-brand-soft text-brand" : "text-muted hover:text-foreground",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <Label hint={filters.ats.length === 0 ? "至少选择一个" : undefined}>{"来源"}</Label>
          <div className="flex flex-wrap gap-1.5">
            {ATS_SOURCES.map((a) => {
              const on = filters.ats.includes(a);
              return (
                <button
                  key={a}
                  type="button"
                  onClick={() => toggleAts(a)}
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors max-sm:min-h-[44px]",
                    on ? "border-brand/40 bg-brand-soft text-brand" : "border-border text-muted hover:text-foreground",
                  )}
                >
                  {ATS_LABEL[a]}
                </button>
              );
            })}
          </div>
        </div>
      </div>}

      {!employer && <button
        type="button"
        onClick={() => setAdvanced((v) => !v)}
        className="inline-flex items-center gap-1.5 text-[12px] text-muted hover:text-foreground transition-colors max-sm:min-h-[44px]"
      >
        <SlidersHorizontal className="size-3.5" />
        更多地点选项与扫描深度
        <ChevronDown className={cn("size-3.5 transition-transform", advanced && "rotate-180")} />
      </button>}

      {!employer && advanced && (
        <div className="space-y-3 rounded-xl border border-border bg-surface/30 p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label hint="保留符合此地点的多地点职位">{"始终包含"}</Label>
              <KeywordField ariaLabel="始终包含的地点" values={filters.alwaysAllow} tone="inc" placeholder="多伦多…" onChange={(v) => set({ alwaysAllow: v })} />
            </div>
            <div>
              <Label hint="若同时符合“始终包含”，仍会保留">{"排除地点"}</Label>
              <KeywordField ariaLabel="排除地点" values={filters.block} tone="exc" placeholder="印度…" onChange={(v) => set({ block: v })} />
            </div>
          </div>
          <div>
            <Label hint="强制排除，优先于“始终包含”">{"始终排除"}</Label>
            <KeywordField ariaLabel="始终排除的地点" values={filters.blockHard} tone="exc" placeholder="美国、巴西…" onChange={(v) => set({ blockHard: v })} />
          </div>
          <div>
            <Label hint={`${filters.limitPerAts} 家公司 / 来源`}>{"扫描深度"}</Label>
            <input
              type="range"
              min={50}
              max={500}
              step={50}
              value={filters.limitPerAts}
              aria-label="扫描深度"
              onChange={(e) => set({ limitPerAts: Number(e.target.value) })}
              className="w-full accent-brand"
            />
          </div>
        </div>
      )}
    </fieldset>
  );
}
