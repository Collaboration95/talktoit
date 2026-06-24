// Nivo chart components — individual exports for type-first gallery
import { ResponsiveLine } from '@nivo/line'
import { ResponsiveBar } from '@nivo/bar'
import { ResponsivePie } from '@nivo/pie'
import { ResponsiveScatterPlot } from '@nivo/scatterplot'
import { ResponsiveRadialBar } from '@nivo/radial-bar'
import { ResponsiveCalendar } from '@nivo/calendar'
import data, { PALETTE, TOP_SPORTS } from '../data'

const axisFont = { fontSize: 10 }
const theme = { text: { fontSize: 10 }, axis: { ticks: { text: axisFont } }, legends: { text: axisFont }, grid: { line: { stroke: '#f0f3f7' } } }

const rings = data.activityRings
const weeklySteps = buildWeeklySteps()

export function NivoArea() {
  return (
    <ResponsiveLine
      data={[{ id: 'RHR', data: data.restingHrDaily.map(d => ({ x: d.date, y: d.value })) }]}
      margin={{ top: 12, right: 12, bottom: 36, left: 40 }}
      xScale={{ type: 'time', format: '%Y-%m-%d', precision: 'day' }}
      xFormat="time:%b %d"
      yScale={{ type: 'linear', min: 'auto', max: 'auto' }}
      axisBottom={{ format: '%b', tickValues: 'every 1 month' }}
      enablePoints={false} enableArea areaOpacity={0.15}
      colors={[PALETTE[0]]} curve="monotoneX" theme={theme} useMesh
    />
  )
}

export function NivoBar() {
  return (
    <ResponsiveBar
      data={weeklySteps as unknown as Record<string, string | number>[]}
      keys={['steps']} indexBy="week"
      margin={{ top: 12, right: 12, bottom: 36, left: 52 }}
      padding={0.25} colors={[PALETTE[0]]} enableLabel={false}
      axisBottom={{ tickValues: weeklySteps.filter((_, i) => i % 4 === 0).map(w => w.week), tickRotation: -30 }}
      axisLeft={{ format: v => `${Math.round(Number(v) / 1000)}k` }}
      theme={theme}
    />
  )
}

export function NivoStacked() {
  return (
    <ResponsiveBar
      data={data.weeklyVolumeBySport as unknown as Record<string, string | number>[]}
      keys={TOP_SPORTS} indexBy="week"
      margin={{ top: 12, right: 12, bottom: 36, left: 44 }}
      padding={0.25} colors={PALETTE} enableLabel={false}
      axisBottom={{ tickValues: [] }}
      legends={[{ dataFrom: 'keys', anchor: 'bottom', direction: 'row', translateY: 36, itemWidth: 72, itemHeight: 12, itemTextColor: '#6b7280', symbolSize: 8, symbolShape: 'square' }]}
      theme={theme}
    />
  )
}

export function NivoDonut() {
  return (
    <ResponsivePie
      data={data.sportBreakdown.map(s => ({ id: s.type, label: s.type, value: s.count }))}
      margin={{ top: 12, right: 12, bottom: 36, left: 12 }}
      innerRadius={0.55} padAngle={0.6} cornerRadius={2}
      colors={PALETTE} enableArcLinkLabels={false} arcLabelsSkipAngle={14}
      legends={[{ anchor: 'bottom', direction: 'row', translateY: 36, itemWidth: 72, itemHeight: 12, itemTextColor: '#6b7280', symbolSize: 8, symbolShape: 'square' }]}
      theme={theme}
    />
  )
}

export function NivoScatter() {
  return (
    <ResponsiveScatterPlot
      data={[{ id: 'workouts', data: data.workouts.filter(w => w.avgHr).map(w => ({ x: w.durationMin, y: w.avgHr as number })) }]}
      margin={{ top: 12, right: 12, bottom: 36, left: 48 }}
      xScale={{ type: 'linear', min: 0, max: 'auto' }}
      yScale={{ type: 'linear', min: 60, max: 180 }}
      colors={[PALETTE[2]]} nodeSize={7} theme={theme}
      axisBottom={{ legend: 'duration (min)', legendOffset: 32, legendPosition: 'middle' }}
      axisLeft={{ legend: 'avg HR (bpm)', legendOffset: -40, legendPosition: 'middle' }}
    />
  )
}

export function NivoCalendar() {
  return (
    <ResponsiveCalendar
      data={data.stepsDaily.map(d => ({ day: d.date, value: d.steps }))}
      from={data.stepsDaily[0].date}
      to={data.stepsDaily[data.stepsDaily.length - 1].date}
      emptyColor="#f0f3f7"
      colors={['#bfdbfe', '#60a5fa', '#3b82f6', '#1d4ed8']}
      margin={{ top: 24, right: 12, bottom: 8, left: 28 }}
      monthBorderColor="#ffffff" dayBorderColor="#ffffff"
      theme={theme}
    />
  )
}

export function NivoRadial() {
  const radialData = [
    { id: 'Move', data: [{ x: 'pct', y: Math.round((rings.move / rings.moveGoal) * 100) }] },
    { id: 'Exercise', data: [{ x: 'pct', y: Math.round((rings.exercise / rings.exerciseGoal) * 100) }] },
    { id: 'Stand', data: [{ x: 'pct', y: Math.round((rings.stand / rings.standGoal) * 100) }] },
  ]
  return (
    <ResponsiveRadialBar
      data={radialData} maxValue={120} valueFormat=">-.0f"
      padding={0.35} colors={[PALETTE[3], PALETTE[1], PALETTE[5]]}
      margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
      theme={theme} enableTracks
      legends={[{ anchor: 'right', direction: 'column', justify: false, translateX: 0, translateY: 0, itemWidth: 60, itemHeight: 14, itemTextColor: '#6b7280', symbolSize: 8, symbolShape: 'circle' }]}
    />
  )
}

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
