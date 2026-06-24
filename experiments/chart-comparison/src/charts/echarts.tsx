// Apache ECharts chart components — individual exports for type-first gallery
import ReactECharts from 'echarts-for-react'
import data, { PALETTE, TOP_SPORTS } from '../data'

const base = { width: '100%', height: '100%' }
const grid = { left: 48, right: 16, top: 20, bottom: 28 }
const axisLabel = { fontSize: 10 }
const rings = data.activityRings
const pct = (v: number, g: number) => Math.round((v / g) * 100)

export function EChartsArea() {
  return (
    <ReactECharts style={base} notMerge option={{
      color: [PALETTE[0]],
      grid,
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: data.restingHrDaily.map(d => d.date), axisLabel: { ...axisLabel, interval: 28 }, boundaryGap: false },
      yAxis: { type: 'value', scale: true, axisLabel },
      series: [{ type: 'line', data: data.restingHrDaily.map(d => d.value), smooth: true, showSymbol: false, areaStyle: { opacity: 0.18 } }],
    }} />
  )
}

export function EChartsBar() {
  const weekly = buildWeeklySteps()
  return (
    <ReactECharts style={base} notMerge option={{
      color: [PALETTE[0]],
      grid,
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: weekly.map(w => w.week), axisLabel: { ...axisLabel, interval: 3 } },
      yAxis: { type: 'value', axisLabel },
      series: [{ type: 'bar', data: weekly.map(w => w.steps), barMaxWidth: 20 }],
    }} />
  )
}

export function EChartsStacked() {
  return (
    <ReactECharts style={base} notMerge option={{
      color: PALETTE,
      grid: { ...grid, top: 36 },
      tooltip: { trigger: 'axis' },
      legend: { textStyle: { fontSize: 9 }, top: 4 },
      xAxis: { type: 'category', data: data.weeklyVolumeBySport.map(w => w.week.slice(5)), axisLabel: { ...axisLabel, interval: 4 } },
      yAxis: { type: 'value', axisLabel },
      series: TOP_SPORTS.map(s => ({
        name: s, type: 'bar' as const, stack: 'v',
        data: data.weeklyVolumeBySport.map(w => w[s] as number),
      })),
    }} />
  )
}

export function EChartsDonut() {
  return (
    <ReactECharts style={base} notMerge option={{
      color: PALETTE,
      tooltip: { trigger: 'item' },
      legend: { textStyle: { fontSize: 9 }, type: 'scroll', bottom: 0 },
      series: [{
        type: 'pie', radius: ['42%', '70%'], center: ['50%', '46%'],
        label: { fontSize: 9 },
        data: data.sportBreakdown.map(s => ({ name: s.type, value: s.count })),
      }],
    }} />
  )
}

export function EChartsScatter() {
  return (
    <ReactECharts style={base} notMerge option={{
      color: [PALETTE[2]],
      grid,
      tooltip: { trigger: 'item', formatter: (p: { data: [number, number] }) => `${p.data[0]}min · ${p.data[1]}bpm` },
      xAxis: { type: 'value', name: 'min', nameTextStyle: { fontSize: 9 }, axisLabel },
      yAxis: { type: 'value', name: 'bpm', min: 60, max: 180, axisLabel },
      series: [{
        type: 'scatter', symbolSize: 7, itemStyle: { opacity: 0.6 },
        data: data.workouts.filter(w => w.avgHr).map(w => [w.durationMin, w.avgHr]),
      }],
    }} />
  )
}

export function EChartsCalendar() {
  // The draggable visualMap slider is the headline feature of this chart
  const range = [data.stepsDaily[0].date, data.stepsDaily[data.stepsDaily.length - 1].date]
  return (
    <ReactECharts style={base} notMerge option={{
      tooltip: { position: 'top', formatter: (p: { data: [string, number] }) => `${p.data[0]}: ${p.data[1].toLocaleString()} steps` },
      visualMap: {
        min: 0, max: 20000,
        calculable: true,   // ← enables the draggable range slider
        orient: 'horizontal', left: 'center', bottom: 4,
        inRange: { color: ['#dbeafe', '#2563eb'] },
        textStyle: { fontSize: 9 },
      },
      calendar: {
        top: 32, left: 32, right: 12,
        cellSize: ['auto', 13],
        range: [range[0].slice(0, 7), range[1].slice(0, 7)],
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        dayLabel: { fontSize: 8 },
        monthLabel: { fontSize: 9 },
        yearLabel: { show: false },
      },
      series: [{
        type: 'heatmap', coordinateSystem: 'calendar',
        data: data.stepsDaily.map(d => [d.date, d.steps]),
      }],
    }} />
  )
}

export function EChartsGauge() {
  return (
    <ReactECharts style={base} notMerge option={{
      series: [{
        type: 'gauge', startAngle: 90, endAngle: -270, radius: '82%',
        pointer: { show: false },
        progress: { show: true, overlap: false, roundCap: true, clip: false, itemStyle: { borderWidth: 0 } },
        axisLine: { lineStyle: { width: 16 } },
        splitLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false },
        data: [
          { value: pct(rings.move, rings.moveGoal), name: 'Move', itemStyle: { color: PALETTE[3] }, title: { offsetCenter: ['0%', '-28%'] }, detail: { offsetCenter: ['0%', '-14%'] } },
          { value: pct(rings.exercise, rings.exerciseGoal), name: 'Exercise', itemStyle: { color: PALETTE[1] }, title: { offsetCenter: ['0%', '2%'] }, detail: { offsetCenter: ['0%', '16%'] } },
          { value: pct(rings.stand, rings.standGoal), name: 'Stand', itemStyle: { color: PALETTE[5] }, title: { offsetCenter: ['0%', '32%'] }, detail: { offsetCenter: ['0%', '46%'] } },
        ],
        title: { fontSize: 10 },
        detail: { fontSize: 10, formatter: '{value}%', color: 'inherit' },
      }],
    }} />
  )
}

// shared util
function buildWeeklySteps() {
  const m = new Map<string, number>()
  data.stepsDaily.forEach(d => {
    const dt = new Date(d.date)
    const mon = new Date(dt)
    mon.setDate(dt.getDate() - ((dt.getDay() + 6) % 7))
    const key = mon.toISOString().slice(5, 10)
    m.set(key, (m.get(key) ?? 0) + d.steps)
  })
  return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([week, steps]) => ({ week, steps }))
}
