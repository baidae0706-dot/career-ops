"use client";

import { instrumentSerif } from "@/lib/fonts";
import { HeroGlow } from "@/components/hero-glow";
import { CvIngest } from "@/components/cv/cv-ingest";
import { OnboardingProgress } from "@/components/home/onboarding-progress";

// The first-run takeover: when cv.md is missing, the CV-upload hero IS the home.
// One input, value-coming framing (not a form), the same product chrome (HeroGlow
// + dot-bg) so it feels like the app, not a gate. The whole aha (CV → free matches
// → first score) flows from here.
export function FirstRunHome() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 md:py-16">
      <section className="dot-bg relative overflow-hidden rounded-2xl border border-border bg-surface/40 px-7 py-10 md:px-10 md:py-12">
        <HeroGlow />
        {/* Readability scrim between the animated glow (z-0) and the copy (z-10):
            the glow still reads at the edges, but text always sits on a surface that
            clears WCAG AA contrast instead of washing out over a bright corner. */}
        <div aria-hidden className="pointer-events-none absolute inset-0 z-[1] bg-surface/55 backdrop-blur-[2px] dark:bg-background/45" />
        <div className="relative z-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            <span className="text-faint">//</span>{"本机优先 · 你的电脑"}</p>
          <h1 className={`${instrumentSerif.className} mt-3 text-4xl leading-[1.05] text-landing md:text-5xl`}>{"上传简历，60 秒了解谁在招聘。"}</h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted">{"无需账户。粘贴文字或上传 .md / .txt 即可开始。读取 PDF 需先在"}{" "}
            <a href="/config" className="text-foreground underline-offset-2 hover:underline">{"设置"}</a>{" "}{"中连接 AI CLI。市场扫描"}<span className="text-foreground">{"免费"}</span>{"。仅在你选择评估职位时消耗 Token。"}</p>
          <div className="mt-7">
            <CvIngest />
          </div>
        </div>
      </section>
      {/* What comes after the CV, visible from the first second: the same checklist
          that keeps growing on Today once the CV is in. */}
      <div className="mt-6">
        <OnboardingProgress compact />
      </div>
    </div>
  );
}
