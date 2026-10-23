"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { PageFrame } from "@/components/page-frame";
import { MarkPdfReadyButton } from "@/components/mark-pdf-ready-button";
import { saveStatus } from "@/lib/pipeline-status.mjs";

type CopyItem = { label: string; text: string };
type PdfFile = { relativePath: string; downloadHref: string } | null;
type Tip = { portal: string; tip: string };

const PILL =
  "inline-flex items-center justify-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs font-medium text-muted transition-colors hover:border-brand/40 hover:text-brand max-sm:min-h-[44px] disabled:cursor-not-allowed disabled:opacity-60";

export function ApplyChecklist({
  company,
  role,
  backHref,
  reportHref,
  postingUrl,
  resume,
  cover,
  answers,
  work,
  education,
  cvMissing,
  tips,
  trackerNum,
  reportNum,
  status,
  pdfReady,
}: {
  company: string;
  role: string;
  backHref: string;
  reportHref: string;
  postingUrl: string;
  resume: PdfFile;
  cover: PdfFile;
  answers: CopyItem[];
  work: CopyItem[];
  education: string;
  cvMissing: boolean;
  tips: Tip[];
  trackerNum: string | null;
  reportNum: number | null;
  status: string;
  pdfReady: boolean;
}) {
  return (
    <PageFrame className="max-w-3xl">
      <Link href={backHref} className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-brand">
        <ArrowLeft className="size-4" /> 求职进展
      </Link>
      <header className="mt-5">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-faint">投递清单</p>
        <h1 className="mt-2 font-display text-3xl tracking-tight text-landing">{company}</h1>
        {role && <p className="mt-1 text-muted">{role}</p>}
        <Link href={reportHref} className="mt-3 inline-flex text-sm text-brand hover:underline">
          返回报告
        </Link>
      </header>

      <Section title={"职位原文"}>
        {postingUrl ? (
          <div className="flex flex-wrap items-center gap-2">
            <a href={postingUrl} target="_blank" rel="noreferrer" className={PILL}>
              打开 <ExternalLink className="size-3.5" />
            </a>
            <CopyButton text={postingUrl} label={"复制链接"} />
            <span className="min-w-0 break-all font-mono text-xs text-faint">{postingUrl}</span>
          </div>
        ) : (
          <Empty>这条申请没有职位链接。</Empty>
        )}
      </Section>

      <Section title={"简历与求职信"}>
        <PdfRow label={"简历"} file={resume} empty="这份报告的 PDF 索引中没有简历。" />
        <PdfRow label={"求职信"} file={cover} empty="这份报告的 PDF 索引中没有求职信。" />
      </Section>

      <Section title={"申请问答"}>
        {answers.length > 0 ? (
          <div className="grid gap-3">
            {answers.map((item) => (
              <CopyField key={`${item.label}:${item.text}`} item={item} />
            ))}
          </div>
        ) : (
          <Empty>这份报告尚未保存申请问答。</Empty>
        )}
      </Section>

      <Section title={"工作经历"}>
        {cvMissing ? (
          <Empty>工作区中没有 cv.md。</Empty>
        ) : work.length > 0 ? (
          <div className="grid gap-3">
            {work.map((item) => (
              <CopyField key={`${item.label}:${item.text}`} item={item} />
            ))}
          </div>
        ) : (
          <Empty>cv.md 中没有工作经历。</Empty>
        )}
      </Section>

      <Section title={"教育经历"}>
        {cvMissing ? (
          <Empty>工作区中没有 cv.md。</Empty>
        ) : education ? (
          <CopyField item={{ label: "教育经历", text: education }} />
        ) : (
          <Empty>cv.md 中没有教育经历。</Empty>
        )}
      </Section>

      <Section title={"招聘网站提示"}>
        <table className="w-full text-sm">
          <caption className="sr-only">招聘网站提示</caption>
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="py-2 pr-4 font-medium">招聘网站</th>
              <th className="py-2 font-medium">提示</th>
            </tr>
          </thead>
          <tbody>
            {tips.map((tip) => (
              <tr key={tip.portal} className="border-t border-border">
                <td className="py-2 pr-4 align-top font-medium">{tip.portal}</td>
                <td className="py-2 text-muted">{tip.tip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title={"提交之后"}>
        <div className="flex flex-wrap items-start gap-2">
          <AppliedButton trackerNum={trackerNum} status={status} />
          <SeedButton trackerNum={trackerNum} />
          <MarkPdfReadyButton reportNum={reportNum} ready={pdfReady} />
        </div>
        {!trackerNum && <p className="mt-2 text-xs text-faint">标记已投递和创建跟进记录需要先有求职跟踪条目。</p>}
      </Section>
    </PageFrame>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

function CopyField({ item }: { item: CopyItem }) {
  return (
    <div className="rounded-xl border border-border bg-surface/30 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{item.label}</p>
        <CopyButton text={item.text} label={"复制"} />
      </div>
      <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-muted">{item.text}</pre>
    </div>
  );
}

function PdfRow({ label, file, empty }: { label: string; file: PdfFile; empty: string }) {
  if (!file) return <p className="mb-2 text-sm text-muted">{label}: {empty}</p>;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium">{label}</span>
      <a href={file.downloadHref} target="_blank" rel="noreferrer" className={PILL}>
        下载
      </a>
      <CopyButton text={file.relativePath} label={"复制路径"} />
      <span className="font-mono text-xs text-faint">{file.relativePath}</span>
    </div>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <button
      type="button"
      className={PILL}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setState("copied");
        } catch {
          setState("failed");
        }
        window.setTimeout(() => setState("idle"), 1500);
      }}
    >
      {state === "copied" ? "已复制" : state === "failed" ? "复制失败" : label}
    </button>
  );
}

function AppliedButton({ trackerNum, status }: { trackerNum: string | null; status: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const applied = status.trim().toLowerCase() === "applied";

  async function markApplied() {
    if (!trackerNum || busy || applied) return;
    setBusy(true);
    setError("");
    try {
      await saveStatus(trackerNum, status, "Applied");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法将这条申请标记为已投递。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button type="button" className={PILL} disabled={!trackerNum || busy || applied} onClick={markApplied}>
        {busy ? "正在保存…" : "标记已投递"}
      </button>
      {error && <span className="max-w-xs text-xs text-red-500">{error}</span>}
    </span>
  );
}

function SeedButton({ trackerNum }: { trackerNum: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  async function seed() {
    if (!trackerNum || busy) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const res = await fetch("/api/followups/seed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ n: trackerNum }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setError(typeof body?.error === "string" ? body.error : "无法创建跟进记录。");
        return;
      }
      setNote(body?.seeded !== false ? "已创建跟进记录。" : body?.reason === "disabled" ? "个人配置中已关闭跟进提醒，未创建跟进记录。" : "跟进记录已存在。");
      router.refresh();
    } catch {
      setError("无法创建跟进记录。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button type="button" className={PILL} disabled={!trackerNum || busy} onClick={seed}>
        {busy ? "正在保存…" : "创建跟进记录"}
      </button>
      {note && <span className="text-xs text-muted">{note}</span>}
      {error && <span className="max-w-xs text-xs text-red-500">{error}</span>}
    </span>
  );
}
