import { readMachineSummary, scoreLevers } from "@/lib/machine-summary.mjs";

type Item = { text: string; tag?: string };

function ItemList({ title, hint, items, dot }: { title: string; hint: string; items: Item[]; dot: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-foreground">{title}</p>
      <p className="text-xs text-faint">{hint}</p>
      <ul className="mt-2 space-y-1.5">
        {items.map((item) => (
          <li key={item.text} className="flex items-start gap-2 text-sm text-foreground">
            <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${dot}`} />
            <span className="min-w-0 flex-1">{item.text}</span>
            {item.tag && <span className="shrink-0 text-[11px] uppercase tracking-wide text-faint">{item.tag}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

const plain = (text: string): Item => ({ text });

export function ScoreLevers({ report }: { report: string }) {
  const summary = readMachineSummary(report);
  if (!summary) return null;
  const { holding, close, verify, strengths } = scoreLevers(summary);
  if (holding.length + close.length + verify.length + strengths.length === 0) return null;
  return (
    <section data-testid="score-levers" className="mt-4 rounded-2xl border border-border bg-surface/30 px-5 py-4">
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-faint">哪些因素会改变评分</p>
      <div className="mt-3 grid gap-5 sm:grid-cols-2">
        <ItemList
          title={"扣分因素"}
          hint={"你的简历尚未提供证据的关键要求和阻碍。"}
          items={holding.map((l) => ({ text: l.text, tag: l.importance ?? "blocker" }))}
          dot="bg-red-500"
        />
        <ItemList
          title={"接近达标"}
          hint={"已部分覆盖，更清楚的简历证据可能提高评分。"}
          items={close.map((l) => ({ text: l.text, tag: l.importance ?? undefined }))}
          dot="bg-amber-500"
        />
        <ItemList title={"加分因素"} hint={"你与这个职位最匹配的方面。"} items={strengths.map(plain)} dot="bg-emerald-500" />
        <ItemList title={"采信前请核对"} hint={"评分背后尚未明确的问题。"} items={verify.map(plain)} dot="bg-sky-500" />
      </div>
    </section>
  );
}
