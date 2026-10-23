"use client";

import { uiLabel } from "@/lib/ui-labels";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, CircleHelp, Sparkles, ArrowRight } from "lucide-react";
import { instrumentSerif } from "@/lib/fonts";
import { HeroGlow } from "@/components/hero-glow";
import type { Application, InboxJob } from "@/lib/career-ops";
import type { DiscoveredOffer } from "@/lib/explore";
import { DiscoveryCard } from "@/components/explore/discovery-card";
import { FollowUpCard, type FollowUp } from "@/components/home/follow-up-card";
import { DecisionCard } from "@/components/home/decision-card";
import type { CardReason } from "@/lib/machine-summary.mjs";
import { QuickEvaluate } from "@/components/quick-evaluate";
import { FollowupsDueSectionSkeleton } from "@/components/page-loading-skeletons";
import { scoreNum } from "@/lib/format";
import { pickAwaitingDecision, groupAwaiting } from "@/lib/home/awaiting.mjs";
import { companyPresentation } from "@/lib/company-presentation.mjs";
import { resolveHeroState, mayClaimAllClear, showsQueue, missingSourceLabel, displayCounts } from "@/lib/home/hero-state.mjs";

// The retention "Today": a dual-loop action queue (the maintainer's
// "N new matches this week · M follow-ups due"). SUPPLY loop = fresh free-scan
// matches (zero tokens, /api/whats-new); DEMAND loop = follow-ups due
// (/api/followups). Each item one-tap actionable. Home stays a VIEW over the
// canonical files — every action dispatches a real registry action / route.
export function TodayDashboard({
  applications,
  reasons,
  legitimacy,
  inbox,
  inBetween,
}: {
  applications: Application[];
  reasons: Record<string, CardReason>;
  /** Block-G legitimacy per report number, read by the page from each report. */
  legitimacy: Record<string, string>;
  inbox: Pick<InboxJob, "url" | "done">[];
  inBetween: boolean;
}) {
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [overdue, setOverdue] = useState(0);
  const [followupsLoading, setFollowupsLoading] = useState(true);
  const [followupsError, setFollowupsError] = useState(false);
  const [followupsEnabled, setFollowupsEnabled] = useState(true);
  const [upcoming, setUpcoming] = useState<FollowUp[]>([]);
  const [fresh, setFresh] = useState<DiscoveredOffer[]>([]);
  const [freshCount, setFreshCount] = useState(0);
  const [freshLoading, setFreshLoading] = useState(true);
  const [freshError, setFreshError] = useState(false);
  const requestGeneration = useRef(0);
  const router = useRouter();
  const dateLabel = useMemo(() => new Date().toLocaleDateString("zh-CN", { weekday: "long", month: "short", day: "numeric" }), []);

  const refetch = useCallback(() => {
    const generation = ++requestGeneration.current;
    const isLatest = () => generation === requestGeneration.current;
    setFollowupsLoading(true);
    setFollowupsError(false);
    fetch("/api/followups")
      .then((r) => {
        if (!r.ok) throw new Error("跟进请求失败");
        return r.json();
      })
      .then((d) => {
        if (!isLatest()) return;
        // The cadence route reports engine failures as HTTP 200 with
        // available:false; that is unavailable, not an empty action queue.
        if (d.available === false) throw new Error("暂时无法获取跟进");
        // /api/followups already filters to urgency 'urgent'/'overdue' — due
        // now, never 'waiting'/'cold' (#86). Both count toward "due"; a
        // missing metadata.overdue must read as 0 due, never as "every entry
        // is overdue" (the old `?? d.entries?.length` fallback).
        setFollowups(Array.isArray(d.entries) ? d.entries : []);
        setOverdue((d.metadata?.overdue ?? 0) + (d.metadata?.urgent ?? 0));
        setFollowupsEnabled(d.followupsEnabled !== false);
        setUpcoming(Array.isArray(d.upcoming) ? d.upcoming : []);
      })
      .catch(() => { if (isLatest()) setFollowupsError(true); })
      .finally(() => { if (isLatest()) setFollowupsLoading(false); });
    setFreshLoading(true);
    setFreshError(false);
    fetch("/api/whats-new")
      .then((r) => {
        if (!r.ok) throw new Error("新匹配请求失败");
        return r.json();
      })
      .then((d) => {
        if (!isLatest()) return;
        const offers = Array.isArray(d.offers) ? d.offers : [];
        const count = Number(d.count);
        setFresh(offers);
        setFreshCount(Number.isFinite(count) ? Math.max(0, Math.trunc(count)) : offers.length);
      })
      .catch(() => { if (isLatest()) setFreshError(true); })
      .finally(() => { if (isLatest()) setFreshLoading(false); });
  }, []);

  useEffect(() => {
    refetch();
    // A worker (evaluate/pdf) just wrote a real tracker row — refresh the server
    // snapshot (applications/inbox props) + the client loops so the freshly-scored
    // role appears in "Awaiting your decision" without a manual reload.
    const onDone = () => {
      router.refresh();
      refetch();
    };
    window.addEventListener("co-job-done", onDone);
    return () => {
      window.removeEventListener("co-job-done", onDone);
      requestGeneration.current += 1;
    };
  }, [refetch, router]);

  // Awaiting decision: scored (Evaluated) but no terminal status yet. The
  // ordering lives in lib/home/awaiting.mjs so it can be tested — see the file
  // for why "first six in the array" was a bug waiting for #3529.
  const awaiting = useMemo(() => pickAwaitingDecision(applications, scoreNum), [applications]);
  // With the legitimacy, a flagged posting is grouped as the report page
  // labels it (#5300), so "Apply next" below never points at one.
  const awaitingGroups = useMemo(() => groupAwaiting(awaiting, (a) => legitimacy[a.n]), [awaiting, legitimacy]);
  const recommended = awaitingGroups.find(([label]) => label === "Recommended")?.[1] ?? [];

  const newThisWeek = freshCount;
  const dataLoading = followupsLoading || freshLoading;
  const dataError = followupsError || freshError;
  // Derived from the flags refetch() already maintains — no second fetch loop
  // and no second source of truth. The only thing added is the distinction
  // dataError cannot make: a failure with known work still has a queue to show.
  const heroState = resolveHeroState({
    followupsLoading,
    freshLoading,
    followupsError,
    freshError,
    overdue,
    newThisWeek,
    awaitingCount: awaiting.length,
  });
  const allClear = mayClaimAllClear(heroState);
  const missingSources = uiLabel(missingSourceLabel({ followupsError, freshError }) ?? "");
  // Printed instead of the raw state: refetch() leaves the previous count in
  // place when a source fails, so `overdue` can still hold a number from before
  // the outage. See displayCounts().
  const shown = displayCounts({ followupsError, freshError, overdue, newThisWeek });
  const inboxUrls = useMemo(() => new Set(inbox.map((j) => j.url)), [inbox]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 max-sm:pb-24">
      <section className="dot-bg relative overflow-hidden rounded-2xl border border-border bg-surface/40 px-7 py-10 md:px-10 md:py-12">
        <HeroGlow />
        {/* Readability scrim between the animated glow (z-0) and the copy (z-10). */}
        <div aria-hidden className="pointer-events-none absolute inset-0 z-[1] bg-surface/55 backdrop-blur-[2px] dark:bg-background/45" />
        <div className="relative z-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            <span className="text-faint">//</span>{"今日 ·"}<span className="tabular-nums">{dateLabel}</span>
          </p>
          <h1 className={`${instrumentSerif.className} mt-3 text-4xl leading-[1.05] text-landing md:text-5xl`}>
            {heroState === "loading" ? (
              <>{"正在加载你的求职待办。"}</>
            ) : heroState === "unavailable" ? (
              <>{"部分更新暂不可用。"}</>
            ) : allClear ? (
              <>{"已查看全部新结果。"}</>
            ) : showsQueue(heroState) ? (
              <>
                {shown.newThisWeek > 0 && (
                  <>
                    <span className="text-brand tabular-nums">{shown.newThisWeek}</span> 个本周新匹配
                  </>
                )}
                {shown.newThisWeek > 0 && shown.overdue > 0 && <span className="text-faint"> · </span>}
                {shown.overdue > 0 && (
                  <>
                    <span className="text-brand tabular-nums">{shown.overdue}</span> 项跟进已到期
                  </>
                )}
                {/* queue-partial with work known only from the server snapshot:
                    both loops are down but the pipeline still has decisions
                    waiting, so the queue is real while neither count is. */}
                {shown.newThisWeek === 0 && shown.overdue === 0 && <>待办事项等待你处理。</>}
              </>
            ) : (
              <>待办事项等待你处理。</>
            )}
          </h1>
          <p className="mt-4 max-w-xl text-sm text-muted">
            {heroState === "unavailable"
              ? "无法加载今日的全部更新，请重试。"
              : heroState === "queue-partial"
                ? `${missingSources}无法读取，待办可能不完整。下方显示已加载的内容。`
                : allClear
                  ? "你可以继续运行免费扫描，查找适合的职位。"
                  : followupsEnabled
                    ? "今日待办，汇总新职位与跟进事项。"
                    : "集中查看今日的求职待办。"}
          </p>
          <div className="mt-6 flex flex-wrap gap-2.5">
            <Link href="/explore" className="inline-flex items-center gap-2 rounded-full bg-brand px-5 py-2.5 text-sm font-medium text-brand-foreground transition hover:bg-brand-200 max-sm:min-h-[44px]">{"查找新职位"}<ArrowRight className="size-4" />
            </Link>
            <Link href="/pipeline" className="inline-flex items-center gap-2 rounded-full border border-border px-5 py-2.5 text-sm font-medium text-foreground transition hover:border-brand/40 hover:text-brand max-sm:min-h-[44px]">{"打开求职进展"}</Link>
          </div>
          {inBetween && <QuickEvaluate />}
        </div>
      </section>

      {dataError && !dataLoading && (
        <div role="alert" className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface/40 px-5 py-4 text-sm text-muted">
          <p>{missingSources}{"无法加载。"}</p>
          <button type="button" onClick={refetch} className="font-medium text-brand hover:underline">{"重试更新"}</button>
        </div>
      )}

      {/* A. Follow-ups due (demand loop) */}
      {followupsLoading ? (
        <FollowupsDueSectionSkeleton />
      ) : followupsError ? (
        null
      ) : followups.length > 0 ? (
        <Section icon={Bell} title="到期跟进" hint="及时跟进，让申请保持活跃">
          <div className="grid gap-2.5">
            {followups.map((f) => (
              // Refetch (not a local decrement) so the parent's followups/upcoming
              // stay in sync with the server. Logging the LAST due item must flip this
              // section over to "Upcoming" instead of leaving it empty.
              <FollowUpCard key={`${f.num}-${f.company}`} followup={f} onLogged={refetch} />
            ))}
          </div>
        </Section>
      ) : null}

      {!followupsLoading && !followupsError && upcoming.length > 0 && (
        <Section icon={Bell} title="即将到期" hint="尚未到期">
          <ul className="grid gap-2">
            {upcoming.map((item) => (
              <li key={`${item.num ?? item.company}-${item.nextFollowupDate ?? ""}`}>
                <Link
                  href={item.num != null ? `/pipeline/${item.num}` : "/followups"}
                  className="text-sm text-muted hover:text-brand"
                >
                  <span className="font-medium text-foreground">{item.company}</span>
                  {item.role ? <span> · {item.role}</span> : null}
                  {item.nextFollowupDate ? <span className="text-faint"> · {item.nextFollowupDate}</span> : null}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* B. Awaiting your decision */}
      {awaiting.length > 0 && (
        <Section icon={CircleHelp} title="等待你的决定" hint="按评分从高到低排列，选择申请或跳过">
          {recommended.length > 0 && (
            <Link
              href={`/pipeline/${recommended[0].n}`}
              className="mb-3 inline-flex items-center gap-2 rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-foreground transition hover:bg-brand-200 max-sm:min-h-[44px]"
            >
              接下来申请 · {companyPresentation(recommended[0]).label} {recommended[0].score} <ArrowRight className="size-4" />
            </Link>
          )}
          {awaitingGroups.map(([label, group]) => (
            <div key={label} className="mb-3">
              <h3 className="mb-2 text-xs font-medium text-faint">{uiLabel(label)}</h3>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {group.map((a) => (
                  <DecisionCard key={a.n} app={a} reason={reasons[a.n]} />
                ))}
              </div>
            </div>
          ))}
        </Section>
      )}

      {/* C. Fresh matches this week (supply loop) */}
      {!freshError && fresh.length > 0 && (
        <Section icon={Sparkles} title="本周新匹配" hint="免费扫描发现 · 0 Token">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {fresh.slice(0, 6).map((o) => (
              <DiscoveryCard key={o.url} offer={o} inPipeline={inboxUrls.has(o.url)} />
            ))}
          </div>
          {fresh.length > 6 && (
            <Link href="/explore?view=fresh" className="mt-3 inline-flex items-center text-sm text-muted transition hover:text-brand max-sm:min-h-[44px]">{"查看全部"}{freshCount} →
            </Link>
          )}
        </Section>
      )}

      {allClear && upcoming.length === 0 && (
        <div className="mt-8 rounded-2xl border border-border bg-surface/30 px-6 py-10 text-center">
          <Sparkles className="mx-auto size-6 text-brand" />
          <p className="mx-auto mt-3 max-w-md text-sm text-muted">{"当前没有待处理事项。运行一次"}<Link href="/explore" className="text-brand hover:underline">{"免费扫描"}</Link>{"，查找本周职位，或查看你的"}<Link href="/pipeline" className="text-brand hover:underline">{"求职进展"}</Link>.
          </p>
        </div>
      )}
    </div>
  );
}

function Section({ icon: Icon, title, hint, children }: { icon: React.ComponentType<{ className?: string }>; title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="size-4 text-brand" />
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted">{title}</h2>
        <span className="text-xs text-faint">· {hint}</span>
      </div>
      {children}
    </section>
  );
}
