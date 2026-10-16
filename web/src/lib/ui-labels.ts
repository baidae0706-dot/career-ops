// Display labels only. Keep canonical values in controls, URLs and writes unchanged.
const LABELS: Record<string, string> = {
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
  return LABELS[value.toUpperCase()] ?? value;
}
