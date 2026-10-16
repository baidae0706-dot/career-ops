import { ChevronDown, ExternalLink } from "lucide-react";

// Transparency = our differentiator ("why it's a 4.0 for YOU"). The wording is
// the CANONICAL public text from career-ops.org/methodology + /docs — rendered
// verbatim, NOT a web reinterpretation of the rubric (whose weights live in the
// core, modes/_shared.md). Native <details> → no client JS.

const DIMENSIONS: [string, string][] = [
  ["匹配度", "简历与岗位要求的匹配程度"],
  ["职业目标一致性", "此岗位能让你多大程度上接近已设定的职业目标"],
  ["薪酬", "岗位待遇与市场薪酬的比较；缺少薪酬信息时显示“数据不足”，不会编造数值"],
  ["文化信号", "招聘信息体现的团队、价值观和工作方式"],
  ["风险信号", "虚假招聘、诈骗或不匹配的提示"],
  ["综合", "汇总以上维度后的总体评分"],
];

const BLOCKS: [string, string][] = [
  ["A", "用清晰语言概述职位"],
  ["B", "对照表：简历与各项要求的匹配情况、要求的重要程度和差距"],
  ["C", "策略：如何为此岗位定位自己"],
  ["D", "薪酬研究：比较岗位待遇与市场水平"],
  ["E", "申请的个性化建议"],
  ["F", "面试准备：为此岗位定制 STAR 经历"],
  ["G", "职位真实性：检查招聘是否真实，是否存在诈骗或虚假岗位"],
];

export function ScoreMethodology() {
  return (
    <details className="group mt-10 overflow-hidden rounded-2xl border border-border bg-surface/30">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-3.5 text-sm font-medium transition-colors hover:bg-surface-hover">{"career-ops 如何评分，以及为什么适合"}<span className="text-landing">{"你"}</span>
        <ChevronDown className="ml-auto size-4 text-faint transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-5 border-t border-border px-5 py-4 text-sm">
        <p className="text-muted">{"每个职位都会按"}<strong className="text-foreground">1.0–5.0</strong>{"六个维度评分。"}{" "}
          <strong className="text-brand">4.0</strong>{"是申请推荐线；低于此分数时，career-ops 建议不申请。"}</p>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-faint">{"六个评分维度"}</div>
          <ul className="space-y-1.5">
            {DIMENSIONS.map(([k, v]) => (
              <li key={k}>
                <span className="font-medium text-foreground">{k}</span> <span className="text-muted">— {v}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-faint">{"报告各部分的含义"}</div>
          <ul className="space-y-2">
            {BLOCKS.map(([k, v]) => (
              <li key={k} className="flex items-start gap-2.5">
                <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded bg-brand-soft text-xs font-semibold text-brand">
                  {k}
                </span>
                <span className="text-muted">{v}</span>
              </li>
            ))}
          </ul>
        </div>
        <a
          href="https://career-ops.org/methodology"
          target="_blank"
          rel="noreferrer"
          aria-label="完整评分方法（在新标签页打开）"
          className="inline-flex min-h-[24px] items-center gap-1 text-xs text-brand transition-colors hover:underline max-sm:min-h-[44px]"
        >{"完整评分方法"}<ExternalLink className="size-3" aria-hidden="true" />
        </a>
      </div>
    </details>
  );
}
