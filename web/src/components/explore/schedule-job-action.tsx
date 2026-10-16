"use client";

import { useState } from "react";
import { CalendarPlus } from "lucide-react";
import type { ExploreFilters } from "@/lib/explore";
import { Button } from "@/components/ui/button";
import { cadenceMinimum, createScheduledJobRequest } from "@/lib/scheduled-job-client.mjs";

type ScheduleUnit = "minutes" | "hours" | "days";

export function ScheduleJobAction({ filters }: { filters: ExploreFilters }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("定时扫描");
  const [every, setEvery] = useState(3);
  const [unit, setUnit] = useState<ScheduleUnit>("hours");
  const [state, setState] = useState("");
  const [saving, setSaving] = useState(false);
  const minimum = cadenceMinimum(unit);

  const save = async () => {
    setSaving(true);
    setState("保存中…");
    try {
      await createScheduledJobRequest({
          name,
          every: Math.max(minimum, every),
          unit,
          filters,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          startAt: new Date().toISOString(),
      });
      setState("定时扫描已创建。");
      setOpen(false);
    } catch (error) {
      setState(error instanceof Error ? error.message : "无法创建定时扫描。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" onClick={() => setOpen((value) => !value)}>
        <CalendarPlus className="size-4" />{"定时安排"}</Button>
      {open && (
        <div className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-surface p-3 text-sm">
          <label className="grid gap-1 text-xs text-muted">{"名称"}<input
              className="rounded-md border border-border bg-background px-2 py-1.5 text-foreground"
              value={name}
              maxLength={80}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="grid gap-1 text-xs text-muted">{"重复间隔"}<input
              className="w-16 rounded-md border border-border bg-background px-2 py-1.5 text-foreground"
              type="number"
              min={minimum}
              value={every}
              onChange={(event) => setEvery(Number(event.target.value))}
            />
          </label>
          <select
            aria-label="时间单位"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-foreground"
            value={unit}
            onChange={(event) => setUnit(event.target.value as ScheduleUnit)}
          >
            <option value="minutes">{"分钟"}</option>
            <option value="hours">{"小时"}</option>
            <option value="days">{"天"}</option>
          </select>
          <Button
            type="button"
            disabled={saving || !name.trim() || !Number.isFinite(every) || every < minimum}
            onClick={() => void save()}
          >
            {saving ? "保存中…" : "添加定时扫描"}
          </Button>
          {state && <span className="text-xs text-muted">{state}</span>}
        </div>
      )}
      {!open && state && <span role="status" className="text-xs text-muted">{state}</span>}
    </div>
  );
}
