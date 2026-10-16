// The portals scanner has no date window when --since is absent. Keep 0 as an
// explicit "all dates" value through the scheduled-job API's shared codec.
// The full ATS scanner requires a positive window and retains its own default.
export function scheduledSinceDays(engine, rawFilters, parsedDays) {
  const requested = rawFilters?.sinceDays !== undefined
    ? rawFilters.sinceDays : rawFilters?.since;
  if (engine === "portals" && requested === 0) return 0;
  return engine === "full" && parsedDays === 0 ? 7 : parsedDays;
}
