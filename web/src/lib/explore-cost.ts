// The cost-honesty taxonomy — a single source for the FREE vs $ boundary that the
// Explorer teaches by repetition. Discovery (finding roles) is structurally free:
// it calls no LLM. Only evaluation (scoring a role against your CV) spends tokens,
// and only when the user chooses it. The framing is always local-first: "your key,
// your AI, your machine."

export type CostClass = "free" | "free-network" | "spend" | "free-gemini";

export const COST_META: Record<CostClass, { label: string; tip: string }> = {
  "free-network": {
    label: "免费",
    tip: "通过 HTTP 扫描公开 ATS 网络，不调用 AI、不消耗 Token。只有你选择加入职位时才会写入记录。",
  },
  free: {
    label: "免费",
    tip: "不消耗 Token，只读写本地文件。",
  },
  spend: {
    label: "消耗 Token",
    tip: "使用你自己的 AI 执行正式 A–F 评估。你选择评估职位时才会消耗 Token。",
  },
  "free-gemini": {
    label: "免费 · Gemini",
    tip: "使用 Google Gemini 免费额度评估，无 Token 费用。",
  },
};
