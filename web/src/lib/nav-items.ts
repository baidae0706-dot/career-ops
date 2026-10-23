import { LayoutDashboard, Compass, ListChecks, Send, Radar, BarChart3, FileText, Files, Settings, CalendarClock } from "lucide-react";
import type { ComponentType, SVGProps } from "react";

// Single source of truth for the app's primary destinations — shared by the
// desktop sidebar and the mobile nav so they can never drift.
export type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  chip?: string;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "今日", icon: LayoutDashboard },
  { href: "/explore", label: "探索", icon: Compass, chip: "新" },
  { href: "/scheduled-scans", label: "定时扫描", icon: CalendarClock },
  { href: "/pipeline", label: "求职进展", icon: ListChecks },
  { href: "/followups", label: "跟进", icon: Send },
  { href: "/portals", label: "招聘门户", icon: Radar },
  { href: "/analytics", label: "数据分析", icon: BarChart3 },
  { href: "/cv", label: "简历", icon: FileText },
  { href: "/documents", label: "文档", icon: Files },
  { href: "/config", label: "设置", icon: Settings },
];

export function visibleNavItems(followupsEnabled: boolean): NavItem[] {
  return followupsEnabled ? NAV_ITEMS : NAV_ITEMS.filter((item) => item.href !== "/followups");
}

export function isActivePath(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
