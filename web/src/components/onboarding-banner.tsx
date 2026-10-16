"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles, X, Settings } from "lucide-react";

type Doctor = { available: boolean; onboardingNeeded: boolean; missing: string[]; warnings: string[] };

function hasCli(): boolean {
  try {
    return !!JSON.parse(localStorage.getItem("career-ops:config") || "{}").cliId;
  } catch {
    return false;
  }
}

const LABELS: Record<string, string> = {
  "cv.md": "你的简历",
  "config/profile.yml": "求职资料：目标岗位、薪酬、地点",
  "modes/_profile.md": "个性化设置",
  "portals.yml": "要扫描的公司",
};

// Detect (via the core's doctor.mjs) whether setup is incomplete, and offer to
// finish it CONVERSATIONALLY — the assistant asks in plain language and writes
// the canonical files (no YAML to edit). This is the #1 adoption barrier.
export function OnboardingBanner() {
  const [d, setD] = useState<Doctor | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [cli, setCli] = useState(true); // assume until read (avoid CTA flash)

  useEffect(() => {
    setCli(hasCli());
    fetch("/api/doctor")
      .then((r) => r.json())
      .then(setD)
      .catch(() => {});
  }, []);

  if (dismissed || !d || !d.onboardingNeeded) return null;
  const items = d.missing.map((m) => LABELS[m] ?? m);
  const promptLabels: Record<string, string> = {
    "cv.md": "your CV",
    "config/profile.yml": "your profile — target roles, comp, location",
    "modes/_profile.md": "your personalization",
    "portals.yml": "the companies to scan",
  };
  const kickoff =
    `Help me finish setting up career-ops. I still need to add ${d.missing.map((m) => promptLabels[m] ?? m).join(", ")} — walk me through just those, conversationally, and write the files for me. Don't ask me for anything that's already set up (for example, don't ask for my CV if it's already saved).`;

  return (
    <div className="dot-bg relative mb-6 overflow-hidden rounded-2xl border border-brand/30 bg-gradient-to-br from-brand/10 via-surface/40 to-transparent p-5">
      <button
        onClick={() => setDismissed(true)}
        className="absolute right-3 top-3 text-faint transition-colors hover:text-foreground"
        aria-label="关闭提示"
      >
        <X className="size-4" />
      </button>
      <h2 className="font-display text-xl text-landing">{"完成你的初始设置"}</h2>
      <p className="mt-1.5 max-w-xl text-sm text-muted">{"career-ops 了解你之后效果更好。还需要"}{items.join(", ")}.{" "}
        <span className="text-foreground">{"无需编辑 YAML"}</span>{"，用自然语言回答，助手会帮你写入文件。"}</p>
      {cli ? (
        <button
          onClick={() => window.dispatchEvent(new CustomEvent("co-assistant", { detail: { message: kickoff } }))}
          className="mt-4 inline-flex items-center gap-2 rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-foreground transition-colors hover:bg-brand-200"
        >
          <Sparkles className="size-4" />{"让助手带我设置"}</button>
      ) : (
        // The assistant needs a CLI to run — without one the kickoff would silently
        // drop. Send them to connect one first.
        <Link
          href="/config"
          className="mt-4 inline-flex items-center gap-2 rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-foreground transition-colors hover:bg-brand-200"
        >
          <Settings className="size-4" />{"连接你的 AI CLI 以开始使用"}</Link>
      )}
    </div>
  );
}
