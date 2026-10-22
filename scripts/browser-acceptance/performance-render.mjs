// Private, source-neutral observation of rendered panels. No application hooks,
// data mutation, ECharts imports or source-specific timing delays are installed.
export async function capturePreviousCanvases(page) {
  await page.evaluate(() => {
    window.__ttiPreviousCanvases = new WeakSet(
      document.querySelectorAll("canvas"),
    );
  });
}

export async function waitForRenderedPanels(
  page,
  phase,
  { scope = {}, granularity = "week" } = {},
) {
  const bodies = await phase.bodies();
  // Only derived structural counts and readiness flags cross into the page.
  // Actual body values stay in the private ledger/Playwright response objects.
  const expected = Object.entries(bodies).map(([endpoint, body]) => ({
    endpoint,
    empty:
      endpoint === "summary"
        ? body.days.length === 0
        : endpoint === "capabilities"
          ? body.capabilities.length === 0
          : false,
    stages_message: endpoint === "sleep_stages" ? body.message : null,
    stage_names:
      endpoint === "sleep_stages" && body.stage_data_available
        ? Object.keys(body.stages_hours)
        : [],
    rows: endpoint === "workouts" ? body.workouts.length : 0,
    chart:
      endpoint === "volume"
        ? body.series.length > 0
        : ["steps", "heart", "sleep"].includes(endpoint)
          ? body.series.some((p) => p.value !== null)
          : false,
    caps:
      endpoint === "capabilities"
        ? body.capabilities.map(
            (c) =>
              `${c.name.replaceAll("_", " ")} ${(c.state ?? (c.present ? "available" : "unavailable")) === "available" ? "✓" : (c.state ?? "unavailable").replaceAll("_", " ")}`,
          )
        : [],
  }));
  await page.waitForFunction(
    ({ expected, scope, granularity }) => {
      const titles = {
        summary: "Activity Rings",
        workouts: "Recent Workouts",
        volume: "Training Volume",
        steps: "Daily Steps",
        heart: "Resting Heart Rate",
        sleep: "Sleep Interval Coverage",
        sleep_stages: "Measured Sleep Stages",
        capabilities: "Data Sources",
      };
      const sections = [...document.querySelectorAll("section")];
      if (
        !sections.length ||
        document.querySelector('[data-testid="tab-loading"]')
      )
        return false;
      if (
        document.body.textContent.includes("Could not load") ||
        document.body.textContent.includes("Chart could not be loaded")
      )
        return false;
      for (const item of expected) {
        if (item.endpoint === "status") {
          if (!document.querySelector('[aria-label="Imported data coverage"]'))
            return false;
          continue;
        }
        const section = sections.find((s) =>
          s.querySelector("h2")?.textContent.startsWith(titles[item.endpoint]),
        );
        if (
          !section ||
          section.querySelector('[data-testid^="panel-loading-"]') ||
          section.textContent.includes("Loading chart…")
        )
          return false;
        if (item.chart) {
          const canvases = [...section.querySelectorAll("canvas")];
          if (
            !canvases.length ||
            canvases.some(
              (c) =>
                window.__ttiPreviousCanvases?.has(c) ||
                c.width <= 0 ||
                c.height <= 0 ||
                c.getBoundingClientRect().width <= 0 ||
                c.getBoundingClientRect().height <= 0,
            )
          )
            return false;
        } else if (
          ["steps", "heart", "sleep", "volume"].includes(item.endpoint) &&
          !section.textContent.includes("No data")
        )
          return false;
        if (
          item.endpoint === "workouts" &&
          (section.querySelectorAll("tbody tr").length !== item.rows ||
            (!item.rows &&
              !section.textContent.includes("No workouts match this scope")))
        )
          return false;
        if (item.empty && !section.textContent.includes("No data"))
          return false;
        if (
          item.endpoint === "summary" &&
          !item.empty &&
          !section.querySelector("canvas")
        )
          return false;
        if (
          item.endpoint === "sleep_stages" &&
          (!section.textContent.includes(item.stages_message) ||
            !item.stage_names.every((name) =>
              [...section.querySelectorAll("dt")].some(
                (dt) => dt.textContent === name,
              ),
            ))
        )
          return false;
        if (
          item.endpoint === "capabilities" &&
          !item.caps.every((text) => section.textContent.includes(text))
        )
          return false;
        if (
          item.endpoint === "volume" &&
          !section
            .querySelector(`button[aria-pressed="true"]`)
            ?.textContent.toLowerCase()
            .includes(granularity)
        )
          return false;
      }
      if (
        scope.start &&
        (!location.search.includes(scope.start) ||
          !location.search.includes(scope.end))
      )
        return false;
      return true;
    },
    { expected, scope, granularity },
  );
}
