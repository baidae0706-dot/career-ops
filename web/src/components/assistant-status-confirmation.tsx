"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { uiLabel } from "@/lib/ui-labels";

export type StatusConfirmationPart = {
  type: "confirm";
  cid: string;
  summary: string;
  statusChange: { n: string; status: string };
  state: "pending" | "saving" | "failed" | "unconfirmed" | "done" | "cancelled";
  message?: string;
  retryable?: boolean;
};

export function StatusConfirmationCard({ part, onConfirm }: {
  part: StatusConfirmationPart;
  onConfirm: (cid: string, accept: boolean) => void;
}) {
  const id = useId();
  const result = useRef<HTMLDivElement>(null);
  const decision = useRef<HTMLButtonElement | null>(null);
  const previousState = useRef(part.state);
  const [announcement, setAnnouncement] = useState("");
  const saving = part.state === "saving";
  const message = saving ? "正在保存状态变更…" : part.state === "done" ? "状态已保存。"
    : part.state === "cancelled" ? "已取消" : part.message ?? "";
  const canDecide = part.state === "pending" || saving || (part.state === "failed" && part.retryable);

  useLayoutEffect(() => {
    if (previousState.current === part.state) return;
    previousState.current = part.state;
    if (part.state === "pending") return;
    if (part.state === "saving") {
      setAnnouncement(`${part.summary} 正在保存状态变更。`);
      return;
    }
    const button = decision.current;
    decision.current = null;
    if (button && (document.activeElement === button || document.activeElement === document.body)) {
      // The result receives focus only as continuation from its own decision.
      // Do not also announce it through the live region.
      setAnnouncement("");
      result.current?.focus();
    } else {
      setAnnouncement(part.state === "cancelled" ? "" : `${part.summary} ${message}`);
    }
  }, [part.state, part.summary, message]);

  function decide(button: HTMLButtonElement, accept: boolean) {
    if (saving) return;
    decision.current = document.activeElement === button ? button : null;
    onConfirm(part.cid, accept);
  }

  return (
    <>
      <div role="group" aria-labelledby={`${id}-summary`} data-assistant-confirmation={part.state} tabIndex={-1} className="rounded-xl border border-brand/40 bg-brand-soft p-2.5 focus-visible:outline-2 focus-visible:outline-brand">
        <div id={`${id}-summary`} className="text-xs font-medium text-foreground">{part.summary}</div>
        <p className="mt-1 text-xs text-muted">申请编号{part.statusChange.n} → {uiLabel(part.statusChange.status)}</p>
        {message && (
          <div ref={result} tabIndex={-1} aria-labelledby={`${id}-summary ${id}-result`} className="mt-1 rounded text-xs text-faint focus-visible:outline-2 focus-visible:outline-brand">
            <span id={`${id}-result`}>{message}</span>
          </div>
        )}
        {canDecide && <div className="mt-2 flex gap-2">
          <button type="button" aria-disabled={saving || undefined} aria-label={`${part.state === "failed" ? "重试" : "确认"}: ${part.summary}`} onClick={(e) => decide(e.currentTarget, true)} className="rounded-full bg-brand px-3 py-1 text-xs font-medium text-brand-foreground aria-disabled:opacity-50">
            {saving ? "正在保存…" : part.state === "failed" ? "重试" : "确认"}
          </button>
          <button type="button" aria-disabled={saving || undefined} aria-label={`取消：${part.summary}`} onClick={(e) => decide(e.currentTarget, false)} className="rounded-full border border-border px-3 py-1 text-xs text-muted aria-disabled:opacity-50">取消</button>
        </div>}
        {(part.state === "failed" || part.state === "unconfirmed") && <Link href="/pipeline?tab=ALL" aria-label={`在跟踪表中核对：${part.summary}`} className="mt-2 inline-block text-xs text-brand-text underline">检查当前跟踪状态</Link>}
      </div>
      <span role="status" aria-label={`状态变更反馈：${part.summary}`} aria-live="polite" aria-atomic="true" className="sr-only">{announcement}</span>
    </>
  );
}
