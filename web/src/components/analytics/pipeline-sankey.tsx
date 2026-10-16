import { uiLabel } from "@/lib/ui-labels";
import { buildPipelineSankey, layoutSankey } from "@/lib/pipeline-sankey.mjs";
import { cn } from "@/lib/cn";

const TONE_NODE: Record<string, string> = {
  success: "fill-emerald-500",
  danger: "fill-red-400",
  info: "fill-sky-500",
  warn: "fill-amber-400",
  muted: "fill-zinc-400 dark:fill-zinc-500",
  neutral: "fill-brand",
};

const TONE_LINK: Record<string, string> = {
  success: "fill-emerald-500/30",
  danger: "fill-red-400/30",
  info: "fill-sky-500/30",
  warn: "fill-amber-400/30",
  muted: "fill-zinc-400/30",
  neutral: "fill-brand/30",
};

type AppRow = { n: string; status: string };
type LogRow = { num: number; from: string; to: string };

export function PipelineSankey({
  applications,
  statusLog,
}: {
  applications: AppRow[];
  statusLog: LogRow[];
}) {
  if (applications.length === 0) return null;

  const graph = buildPipelineSankey(applications, statusLog);
  const layout = layoutSankey(graph, { width: 920, height: 440, padding: { top: 24, right: 188, bottom: 24, left: 100 } });
  const toneById = new Map(layout.nodes.map((n) => [n.id, n.tone]));
  const labelById = new Map(graph.nodes.map((n) => [n.id, uiLabel(n.label)]));
  const firstRank = Math.min(...layout.nodes.map((n) => n.rank));
  const lastRank = Math.max(...layout.nodes.map((n) => n.rank));

  return (
    <section id="pipeline-sankey" className="mt-10 scroll-mt-8" aria-labelledby="sankey-heading">
      <h2 id="sankey-heading" className="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{"求职进展桑基图"}</h2>
      <p className="mt-2 max-w-2xl text-sm text-muted">{"当前跟踪记录快照。状态历史会保留面试后的拒绝路径；后续被拒不会抹去曾进入的阶段。"}</p>

      <div className="mt-4 overflow-x-auto rounded-xl border border-border bg-surface/50 p-3">
        <svg
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          className="h-auto w-full min-w-[720px]"
          role="img"
          aria-labelledby="sankey-title sankey-desc"
        >
          <title id="sankey-title">{"求职进展桑基图"}</title>
          <desc id="sankey-desc">
            {graph.total}{"个职位从已记录流向已提交、等待回复、公司互动及最终结果。"}</desc>

          {layout.links.map((link) => {
            const tone = toneById.get(link.source) ?? "neutral";
            const sourceLabel = labelById.get(link.source) ?? link.source;
            const targetLabel = labelById.get(link.target) ?? link.target;
            return (
              <g key={`${link.source}-${link.target}`}>
                <title>{`${link.value} 个职位：${sourceLabel} → ${targetLabel}`}</title>
                <path d={link.d} className={cn(TONE_LINK[tone] ?? TONE_LINK.neutral, "outline-none")} />
              </g>
            );
          })}

          {layout.nodes.map((node) => {
            const short = node.height < 28;
            const labelOnRight =
              node.rank === lastRank || (node.rank !== firstRank && !(node.rank === 1 && short));
            const lx = labelOnRight ? node.x + node.width + 10 : node.x - 10;
            const anchor = labelOnRight ? "start" : "end";
            return (
              <g key={node.id}>
                <title>{`${uiLabel(node.label)}: ${node.value}`}</title>
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={Math.max(node.height, 2)}
                  rx={3}
                  className={TONE_NODE[node.tone] ?? TONE_NODE.neutral}
                />
                <text
                  x={lx}
                  y={node.y + node.height / 2}
                  textAnchor={anchor}
                  dominantBaseline="middle"
                  className="fill-foreground text-[11px] font-medium"
                  stroke="var(--bg)"
                  strokeWidth={4}
                  paintOrder="stroke"
                >
                  {uiLabel(node.label)}
                  <tspan className="fill-muted font-normal" stroke="var(--bg)" strokeWidth={4} paintOrder="stroke">
                    {`  ${node.value}`}
                  </tspan>
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="sr-only">
        <table>
          <caption>求职进展流向</caption>
          <thead>
            <tr>
              <th>起点</th>
              <th>终点</th>
              <th>职位数</th>
            </tr>
          </thead>
          <tbody>
            {graph.links.map((link) => (
              <tr key={`${link.source}-${link.target}`}>
                <td>{labelById.get(link.source) ?? link.source}</td>
                <td>{labelById.get(link.target) ?? link.target}</td>
                <td>{link.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
