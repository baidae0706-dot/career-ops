// Display labels only. Keep canonical values in controls, URLs and writes unchanged.
const LABELS: Record<string, string> = {
  COVERED: "已覆盖", THIN: "覆盖较弱",
  "MENTIONED MORE THAN ONCE": "出现多次",
  "MENTIONED ONCE — CONSIDER REINFORCING": "仅出现一次，可以补充真实证据",
  "NOT FOUND IN THE CV": "简历中未找到",
  "NO AI CLI IS SET UP. CHOOSE ONE IN CONFIG, OR EDIT THE WORDING BY HAND.": "尚未配置 AI CLI，请在配置页中选择，或手动编辑表述。",
  "THIS AI CLI CANNOT BE LIMITED TO READ-ONLY ACCESS, SO THE REWRITE DID NOT RUN. CHOOSE CLAUDE, CODEX OR GROK IN CONFIG, OR EDIT THE WORDING BY HAND.": "无法将此 AI CLI 限制为只读访问，因此未执行改写。请在配置页中选择 Claude、Codex 或 Grok，或手动编辑表述。",
  "THE AI CLI COULD NOT BE STARTED WITH READ-ONLY ACCESS, SO NOTHING RAN.": "无法以只读权限启动 AI CLI，未执行任何任务。",
  "THE AI CLI DID NOT FINISH. CHECK THAT IT IS SIGNED IN, THEN TRY AGAIN.": "AI CLI 未完成，请确认已登录后再重试。",
  "THE AI CLI REPLIED WITHOUT A USABLE BULLET. TRY A DIFFERENT INSTRUCTION.": "AI CLI 没有返回可用要点，请换一种改写要求。",
  "FORMAL": "正式",
  "DIRECT": "直接",
  "CONVERSATIONAL": "自然交流",
  "MIRROR THE JD": "贴近职位描述",
  "SHORTER": "更简洁",
  "LEAD WITH THE RESULT": "先写成果",
  "PLAINER WORDING": "更直白的表述",
  "USE A JOB KEYWORD ONLY IF IT IS TRUE": "仅添加符合事实的职位关键词",
  "MISSING": "未覆盖",
  "PRESENT": "已覆盖",
  "NOT IN YOUR CV": "简历中尚未体现",
  "CRITICAL": "关键",
  "HIGH": "高优先级",
  "MEDIUM": "中优先级",
  "LOW": "低优先级",
  FRESH: "最新", INBOX: "待评估", ALL: "全部", EVALUATED: "已评估", APPLIED: "已申请",
  RESPONDED: "已回复", ASSESSMENT: "测评", INTERVIEW: "面试", INTERVIEWED: "已面试", OFFER: "录用意向", OFFERS: "录用意向",
  HIRED: "已入职", REJECTED: "被拒", DISCARDED: "已放弃", SKIP: "跳过",
  OVERDUE: "已逾期", URGENT: "紧急", WAITING: "等待中", COLD: "冷线索",
  TRACKER: "记录", COMPANY: "公司", ROLE: "岗位", SCORE: "评分", STATUS: "状态", DATE: "日期",
  EMAIL: "邮件", PHONE: "电话", OTHER: "其他", ACTIVE: "启用中", PAUSED: "已暂停",
  MINUTES: "分钟", HOURS: "小时", DAYS: "天", STRONG: "高", POSSIBLE: "可能", OK: "一般", WEAK: "低",
  LIVE: "有效", BROKEN: "损坏", UNKNOWN: "未知", TRACKED: "已记录", SUBMITTED: "已提交",
  SCREENING: "初筛", "STILL EVALUATED": "已评估待决定", "COMPANY ENGAGED": "公司已互动",
  "DISCARDED (NO APPLICATION RECORDED)": "已放弃（未申请）", "REJECTED (NO INTERVIEW)": "被拒（未面试）",
  "REJECTED AFTER INTERVIEW": "面试后被拒", "DISCARDED AFTER INTERVIEW": "面试后放弃",
  "RESPONSE RATE": "回复率", "INTERVIEW RATE": "面试率", "OFFER RATE": "录用意向率",
  "QUALITY THRESHOLD": "质量阈值", "ARCHETYPE MIX": "职位类型分布", "WORK MODE": "工作模式",
  "COMPANY SIZE": "公司规模", "BY ATS VENDOR": "按 ATS 服务商", RECOMMENDED: "推荐",
  APPLY: "建议申请", CONSIDER: "可以考虑", "RESEARCH FIRST": "先做调研",
  "FOLLOW-UPS": "跟进", "NEW MATCHES": "新匹配", "FOLLOW-UPS AND NEW MATCHES": "跟进与新匹配",
  "STARTING…": "正在启动…", "DONE": "已完成", "FAILED TO START": "启动失败",
  "CONNECTION ERROR": "连接错误", "INTERRUPTED (PAGE RELOADED)": "已中断（页面已刷新）",
  "NO CLI CONFIGURED — OPEN CONFIG AND CLICK SAVE CONFIG": "尚未配置 CLI，请打开“设置”并点击“保存设置”",
  "SIGN YOUR CLI IN FROM CONFIG, THEN RE-RUN.": "请在“设置”中登录你的 CLI，然后重新运行。",
  "LOST CONNECTION TO THE LOCAL SERVER — RE-RUN.": "与本地服务器的连接已断开，请重新运行。",
  "THE RUN WAS INTERRUPTED — RE-RUN IT.": "任务已中断，请重新运行。",
  "NOT SCORED YET": "尚未评分", "CHECK THE POSTING FIRST": "先核实职位信息",
  "BELOW THE APPLY LINE": "低于申请推荐线", "NO SCORE": "尚无评分",
};

export function uiLabel(value: string): string {
  const label = LABELS[value.toUpperCase()];
  if (label) return label;
  return value
    .replace(/^The rewrite was discarded because it adds claims this bullet does not support:/, "已舍弃改写，因为它新增了原要点无法支持的陈述：")
    .replace(/ cannot be permission-restricted — this agent runs with its default access$/, " 无法施加权限限制，将使用默认访问权限运行")
    .replace(/ is only partly restricted: this worker has to open urls it is handed, which its sandbox only allows alongside write access — its writes are confined to the project folder, not blocked$/, " 仅受部分权限限制：此任务需要打开收到的链接，而沙箱仅在允许写入时支持此操作；写入范围限制在项目目录内，并未完全禁止写入");
}

// Translate only the displayed outcome; retain the official source state/message
// in the API and restored discovery snapshot.
export function employerOutcomeLabel(message: string): string {
  return message
    .replace(/^Failed — /, "扫描失败 — ")
    .replace(/^Partial \/ incomplete — (\d+) matches\./, "扫描未完成 — 找到 $1 个匹配职位。")
    .replace(/^Completed — (\d+) matches from /, "扫描完成 — 找到 $1 个匹配职位，来自 ")
    .replace(/^No matches for this scan — /, "本次扫描没有匹配职位 — ")
    .replace(/source response exceeded size limit/g, "来源响应超过大小限制")
    .replace(/source returned no readable result/g, "来源没有返回可读取的结果")
    .replace(/source request failed or returned invalid data/g, "来源请求失败或返回了无效数据")
    .replace(/source request failed or timed out/g, "来源请求失败或超时")
    .replace(/source stopped before reporting all postings/g, "来源未返回全部职位便已停止")
    .replace(/source could not start/g, "来源无法启动")
    .replace(/source timed out/g, "来源超时")
    .replace(/source stopped early/g, "来源提前停止")
    .replace(/source failed/g, "来源失败")
    .replace(/scan interrupted/g, "扫描已中断")
    .replace(/page cap \((\d+) pages\) limits coverage/g, "达到 $1 页上限，覆盖范围受限")
    .replace(/source-data problem: (\d+) records missing company, title or posting identity/g, "来源数据有问题：$1 条记录缺少公司、职位名称或职位标识");
}
