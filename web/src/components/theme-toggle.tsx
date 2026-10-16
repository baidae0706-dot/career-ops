"use client";

import { Sun, Moon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { useTheme } from "@/components/theme-provider";

export function ThemeToggle({ className, showLabel = false }: { className?: string; showLabel?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const dark = theme === "dark";

  return (
    <Button
      variant="ghost"
      size={showLabel ? "default" : "icon"}
      type="button"
      onClick={toggleTheme}
      aria-label="深色模式"
      aria-pressed={dark}
      title={dark ? "切换浅色模式" : "切换深色模式"}
      className={cn("text-muted", showLabel && "w-full justify-start px-2 text-xs", className)}
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
      {showLabel && <span>{"深色模式"}</span>}
    </Button>
  );
}
