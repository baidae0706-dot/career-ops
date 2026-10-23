import Link from "next/link";
import { Suspense } from "react";
import { FollowupsView } from "@/components/followups/followups-view";
import { readFollowupsEnabled } from "@/lib/followups-server";

export const dynamic = "force-dynamic"; // cadence is computed fresh per request

export default function FollowupsPage() {
  if (!readFollowupsEnabled()) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="font-display text-2xl tracking-tight text-landing">跟进提醒已关闭</h1>
        <p className="mt-2 text-sm text-muted">
          可在此重新开启：{" "}
          <Link href="/config" className="font-medium text-brand hover:underline">配置</Link>，或设置{" "}
          <span className="font-mono">follow_ups.enabled: true</span> in <span className="font-mono">config/profile.yml</span>.
        </p>
      </div>
    );
  }
  return (
    <Suspense>
      <FollowupsView />
    </Suspense>
  );
}
