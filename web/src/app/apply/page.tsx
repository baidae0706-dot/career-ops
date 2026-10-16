import { Send } from "lucide-react";
import { ApplyView } from "@/components/apply-view";
import { ApplyBackdropMount } from "@/components/apply/apply-backdrop-mount";

export const dynamic = "force-dynamic";

export default function ApplyPage() {
  return (
    <div className="relative min-h-screen">
      {/* full-viewport blurred form wallpaper (behind everything) */}
      <ApplyBackdropMount />
      <div className="relative z-10 mx-auto max-w-3xl px-6 py-8">
        <div className="flex items-center gap-3">
          <Send className="size-6 text-brand" />
          <h1 className="font-display text-2xl tracking-tight text-landing">{"申请"}</h1>
        </div>
        <p className="mt-1.5 max-w-xl text-sm text-muted">{"career-ops 在你的电脑上读取真实申请表，并在这里用清晰易懂的方式展示，根据简历预填内容。你核对每项答案后，它会填写真实表单，再由你亲自提交。它不会代你提交。"}</p>
        <div className="mt-6">
          <ApplyView />
        </div>
      </div>
    </div>
  );
}
