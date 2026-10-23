"use client";

export default function ApplyError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <p className="text-sm text-red-600">无法加载这份投递清单。</p>
      <p className="mt-2 text-sm text-zinc-600">{error.message || "无法读取报告或相关文件。"}</p>
      <button
        type="button"
        className="mt-4 rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
        onClick={() => reset()}
      >
        重试
      </button>
    </div>
  );
}
