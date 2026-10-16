import { uiLabel } from "@/lib/ui-labels";
import Link from "next/link";
import { ArrowUpRight, BarChart3, BriefcaseBusiness, CircleDollarSign, MapPin, Sparkles, Target } from "lucide-react";
import { PageFrame } from "@/components/page-frame";

type ProgressMetrics = {
  tracked: number;
  avgScore: number;
  activeApps: number;
  totalOffers: number;
  responseRate: number;
  interviewRate: number;
  offerRate: number;
  funnel: { label: string; count: number; pct: number }[];
  scoreDistribution: { label: string; count: number; pct: number }[];
  weeklyActivity: { week: string; shortWeek: string; count: number }[];
};

type StatsMetrics = {
  archetypes: { label: string; count: number; pct: number; avgScore: number }[];
  workModes: { label: string; count: number; pct: number }[];
  locations: { label: string; count: number; pct: number }[];
  qualityTiers: { label: string; count: number; pct: number }[];
  qualityBarPct: number;
  seniorityMix: { label: string; count: number; pct: number }[];
  pay: { count: number; postedCount: number; estimatedCount: number; avgPayMax: number; medianPayMax: number; maxPayMax: number };
  payHistogram: { label: string; count: number; pct: number }[];
};

const BAR_TONES = ["bg-brand", "bg-sky-400", "bg-emerald-400", "bg-yellow-300", "bg-orange-300", "bg-pink-400"];

export function AnalyticsShell({ total, view, children }: {
  total: number;
  view: "progress" | "search-stats" | "insights";
  children: React.ReactNode;
}) {
  return (
    <PageFrame>
      <header className="flex flex-col gap-5 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-brand">求职管理 / 数据分析</p>
          <h1 className="mt-2 font-display text-3xl tracking-tight text-landing sm:text-4xl">求职数据洞察</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
            了解目标职位、申请流转和有助于下一步行动的趋势。
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-faint">
          <span className="size-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
          <span className="tabular-nums">{total}</span> 个已记录的评估
        </div>
      </header>

      <nav aria-label="分析视图" className="mt-5 -mb-px flex gap-1 overflow-x-auto border-b border-border">
        <AnalyticsTab href="/analytics" active={view === "progress"} icon={<BarChart3 className="size-3.5" />}>
          进展总览
        </AnalyticsTab>
        <AnalyticsTab href="/analytics?view=insights" active={view === "insights"} icon={<Sparkles className="size-3.5" />}>
          洞察
        </AnalyticsTab>
        <AnalyticsTab href="/analytics?view=search-stats" active={view === "search-stats"} icon={<Target className="size-3.5" />}>
          搜索统计
        </AnalyticsTab>
      </nav>

      {children}
    </PageFrame>
  );
}

function AnalyticsTab({ href, active, icon, children }: { href: string; active: boolean; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`-mb-px inline-flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-xs font-semibold transition-colors ${
        active ? "border-brand text-foreground" : "border-transparent text-muted hover:border-border hover:text-foreground"
      }`}
    >
      {icon}
      {children}
    </Link>
  );
}

export function ProgressPanel({ metrics }: { metrics: ProgressMetrics }) {
  const maxWeeklyActivity = Math.max(1, ...metrics.weeklyActivity.map((row) => row.count));
  return (
    <div className="mt-6 space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label="已记录" value={metrics.tracked} icon={<BarChart3 className="size-4" />} />
        <MetricCard label="平均评分" value={metrics.avgScore ? `${metrics.avgScore.toFixed(2)}/5` : "—"} icon={<Sparkles className="size-4" />} />
        <MetricCard label="活跃申请" value={metrics.activeApps} icon={<BriefcaseBusiness className="size-4" />} />
        <MetricCard label="录用意向" value={metrics.totalOffers} icon={<ArrowUpRight className="size-4" />} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.85fr)]">
        <Panel eyebrow="转化漏斗" title="申请进展" description="累计到达各阶段的职位数。">
          <div className="mt-5 space-y-3.5">
            {metrics.funnel.map((stage, index) => (
              <BarRow key={stage.label} label={uiLabel(stage.label)} count={stage.count} pct={stage.pct} widthPct={metrics.tracked ? (stage.count / metrics.tracked) * 100 : 0} tone={index === metrics.funnel.length - 1 ? "bg-brand" : "bg-sky-400"} />
            ))}
          </div>
        </Panel>

        <Panel eyebrow="转化率" title="关键转化率" description="回复率、面试率和录用意向率均以已申请数为分母。">
          <div className="mt-5 grid grid-cols-3 gap-2 sm:gap-3 xl:grid-cols-1 xl:gap-0">
            <RateRow label="回复" value={metrics.responseRate} />
            <RateRow label="面试" value={metrics.interviewRate} />
            <RateRow label="录用意向" value={metrics.offerRate} />
          </div>
          <div className="mt-5 border-t border-border pt-4 text-xs text-muted">
            <span className="tabular-nums text-foreground">{metrics.activeApps}</span> 项活跃申请 · <span className="tabular-nums text-foreground">{metrics.totalOffers}</span> 个录用意向
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel eyebrow="匹配质量" title="评分分布" description="仅包含已有评分的评估。">
          <div className="mt-5 space-y-3">
            {metrics.scoreDistribution.map((bucket, index) => <BarRow key={bucket.label} label={uiLabel(bucket.label)} count={bucket.count} pct={bucket.pct} widthPct={bucket.pct} tone={BAR_TONES[index]} />)}
          </div>
        </Panel>
        <Panel eyebrow="活动节奏" title="每周活动" description="最近八个有活动的 ISO 周。">
          {metrics.weeklyActivity.length ? (
            <div className="mt-5 space-y-3">
              {metrics.weeklyActivity.map((week) => {
                return <BarRow key={week.week} label={week.week} count={week.count} widthPct={(week.count / maxWeeklyActivity) * 100} tone="bg-sky-400" />;
              })}
            </div>
          ) : <EmptyData label="暂无带日期的活动" detail="评估记录包含有效日期后，将显示每周活动。" />}
        </Panel>
      </div>
    </div>
  );
}

export function StatsPanel({ metrics, insights }: { metrics: StatsMetrics; insights: string[] }) {
  const scoredRoleCount = metrics.qualityTiers.reduce((sum, row) => sum + row.count, 0);
  return (
    <div className="mt-6 space-y-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Panel eyebrow="趋势信号" title="求职策略洞察" icon={<Sparkles className="size-4" />}>
          {insights.length ? <ul className="mt-4 space-y-3 text-sm leading-6 text-muted">{insights.map((insight) => <li key={insight} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" aria-hidden="true" />{insight}</li>)}</ul> : <EmptyData label="暂时没有足够的数据" detail="随着职位类型、工作模式和薪酬数据积累，将显示相应洞察。" />}
        </Panel>
        <Panel eyebrow="匹配质量" title="达到推荐线的职位" description="按评估阈值对已有评分的职位分组。">
          <div className="mt-4 flex items-end justify-between gap-4">
            <div className="font-display text-4xl tracking-tight text-landing">{scoredRoleCount ? `${Math.round(metrics.qualityBarPct)}%` : "—"}</div>
            <div className="text-right text-xs text-muted">达到 ≥4.0<br /><span className="tabular-nums">{scoredRoleCount}</span> 个已评分职位</div>
          </div>
          <Distribution rows={metrics.qualityTiers} />
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(280px,0.75fr)]">
        <Panel eyebrow="职位类型" title="搜索关注的职位" description="按数量排列的规范职位类型，并列出匹配评分。">
          {metrics.archetypes.length ? <div className="mt-4 space-y-3">{metrics.archetypes.map((row, index) => <div key={row.label} className="grid grid-cols-[minmax(0,1fr)_minmax(100px,0.8fr)_auto] items-center gap-3 text-sm"><div className="min-w-0"><div className="break-words text-foreground">{row.label}</div><div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-hover"><div className={`h-full rounded-full ${BAR_TONES[index % BAR_TONES.length]}`} style={{ width: `${Math.max(row.pct, row.count ? 3 : 0)}%` }} /></div></div><div className="text-right text-xs text-muted tabular-nums">{row.count} <span className="text-faint">({Math.round(row.pct)}%)</span></div><div className="min-w-14 text-right text-xs font-semibold tabular-nums text-brand">{row.avgScore ? `★ ${row.avgScore.toFixed(1)}` : "—"}</div></div>)}</div> : <EmptyData label="暂无职位类型数据" detail="报告中包含职位类型信息后，将在这里显示。" />}
        </Panel>
        <Panel eyebrow="职级" title="职级分布" icon={<BriefcaseBusiness className="size-4" />}>
          <Distribution rows={metrics.seniorityMix} emptyLabel="暂无职级数据" />
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel eyebrow="工作模式" title="职位的工作安排"><BreakdownList rows={metrics.workModes} icon={<BriefcaseBusiness className="size-3.5" />} emptyLabel="暂无工作模式数据" /></Panel>
        <Panel eyebrow="地点" title="职位所在地"><BreakdownList rows={metrics.locations} icon={<MapPin className="size-3.5" />} emptyLabel="暂无地点数据" /></Panel>
      </div>

      <Panel eyebrow="薪酬" title="美元薪酬范围与分布" icon={<CircleDollarSign className="size-4" />}>
        {metrics.pay.count ? <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            <PayStat label="平均值" value={money(metrics.pay.avgPayMax)} />
            <PayStat label="中位数" value={money(metrics.pay.medianPayMax)} />
            <PayStat label="最高值" value={money(metrics.pay.maxPayMax)} />
            <PayStat label="数据条数" value={metrics.pay.count} />
            <PayStat label="公布 / 估算" value={`${metrics.pay.postedCount} / ${metrics.pay.estimatedCount}`} />
          </div>
          <div className="mt-6 border-t border-border pt-5"><p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-muted">薪酬区间分布</p><div className="mt-4 space-y-3">{metrics.payHistogram.map((row, index) => <BarRow key={row.label} label={row.label} count={row.count} pct={row.pct} widthPct={row.pct} tone={BAR_TONES[index]} />)}</div></div>
        </> : <EmptyData label="暂无美元薪酬数据" detail="跟踪备注包含以美元计价的公布或估算薪酬范围后，将在这里显示。" />}
      </Panel>
    </div>
  );
}

function Panel({ eyebrow, title, description, icon, children }: { eyebrow: string; title: string; description?: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-border bg-surface/55 p-4 sm:p-5"><div className="flex items-start justify-between gap-4"><div><p className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.17em] text-brand">{icon}{eyebrow}</p><h2 className="mt-2 font-display text-xl tracking-tight text-landing">{title}</h2>{description && <p className="mt-1 max-w-xl text-xs leading-5 text-muted">{description}</p>}</div></div>{children}</section>;
}

function MetricCard({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return <div className="rounded-xl border border-border bg-surface/45 p-4"><div className="flex items-center justify-between text-brand"><span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-muted">{label}</span>{icon}</div><div className="mt-3 font-display text-3xl tracking-tight text-landing tabular-nums">{value}</div></div>;
}

function RateRow({ label, value }: { label: string; value: number }) {
  return <div className="flex items-center justify-between gap-3 border-b border-border py-3 last:border-0 xl:first:pt-0"><span className="text-sm text-muted">{label}率</span><span className="font-mono text-lg font-semibold tabular-nums text-foreground">{value.toFixed(1)}%</span></div>;
}

function BarRow({ label, count, pct, widthPct, tone }: { label: string; count: number; pct?: number; widthPct: number; tone: string }) {
  const accessibleValue = pct === undefined ? `${label}: ${count}` : `${label}: ${count}, ${Math.round(pct)}%`;
  return <div className="grid grid-cols-[minmax(94px,0.45fr)_minmax(80px,1fr)_auto] items-center gap-3"><span className="break-words text-xs text-muted" title={label}>{label}</span><div className="h-2 overflow-hidden rounded-full bg-surface-hover" role="img" aria-label={accessibleValue}><div className={`h-full rounded-full ${tone} transition-[width] duration-500`} style={{ width: `${Math.min(100, Math.max(0, widthPct))}%` }} /></div><span className="min-w-16 text-right font-mono text-xs tabular-nums text-foreground">{count}{pct === undefined ? null : <> <span className="text-faint">({Math.round(pct)}%)</span></>}</span></div>;
}

function Distribution({ rows, emptyLabel = "暂无分布数据" }: { rows: { label: string; count: number; pct: number }[]; emptyLabel?: string }) {
  if (!rows.length) return <EmptyData label={emptyLabel} detail="需要更多已评估职位才能显示此项分布。" />;
  return <div className="mt-5"><div className="flex h-3 overflow-hidden rounded-full bg-surface-hover" aria-hidden="true">{rows.map((row, index) => <div key={row.label} className={BAR_TONES[index % BAR_TONES.length]} style={{ width: `${row.pct}%` }} />)}</div><div className="mt-4 grid gap-2 sm:grid-cols-2">{rows.map((row, index) => <div key={row.label} className="flex items-center gap-2 text-xs"><span className={`size-2 rounded-full ${BAR_TONES[index % BAR_TONES.length]}`} aria-hidden="true" /><span className="min-w-0 flex-1 truncate text-muted">{uiLabel(row.label)}</span><span className="font-mono tabular-nums text-foreground">{row.count} <span className="text-faint">({Math.round(row.pct)}%)</span></span></div>)}</div></div>;
}

function BreakdownList({ rows, icon, emptyLabel }: { rows: { label: string; count: number; pct: number }[]; icon: React.ReactNode; emptyLabel: string }) {
  if (!rows.length) return <EmptyData label={emptyLabel} detail="在跟踪备注中明确工作模式或地点后，将显示此项数据。" />;
  return <div className="mt-4 space-y-3">{rows.map((row, index) => <div key={row.label} className="flex items-center gap-2 text-sm"><span className="text-brand">{icon}</span><span className="min-w-0 flex-1 break-words text-muted">{uiLabel(row.label)}</span><span className="font-mono text-xs tabular-nums text-foreground">{row.count}</span><span className="w-12 text-right font-mono text-[11px] tabular-nums text-faint">{Math.round(row.pct)}%</span></div>)}</div>;
}

function PayStat({ label, value }: { label: string; value: string | number }) { return <div><p className="text-[11px] text-faint">{label}</p><p className="mt-1 font-mono text-sm font-semibold tabular-nums text-foreground">{value}</p></div>; }
function EmptyData({ label, detail }: { label: string; detail: string }) { return <div className="mt-4 rounded-xl border border-dashed border-border bg-surface/30 px-4 py-6 text-center"><p className="font-display text-lg text-landing">{label}</p><p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-muted">{detail}</p></div>; }
function money(value: number) { return value ? `$${Math.round(value / 1000)}K` : "—"; }
