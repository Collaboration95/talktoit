// Victory chart components — individual exports for type-first gallery
import {
  VictoryChart,
  VictoryLine as VLine,
  VictoryBar as VBar,
  VictoryScatter as VScatter,
  VictoryAxis,
  VictoryTheme,
  VictoryArea as VArea,
  VictoryStack,
  VictoryLegend,
  VictoryPie,
  VictoryVoronoiContainer,
} from 'victory'
import data, { PALETTE, TOP_SPORTS } from '../data'

const axisStyle = { tickLabels: { fontSize: 9, fill: '#6b7280' }, grid: { stroke: '#f0f3f7' }, axis: { stroke: '#e5e7eb' } }
const theme = VictoryTheme.clean

const weeklySteps = buildWeeklySteps()
const hrSampled = data.restingHrDaily.filter((_, i) => i % 2 === 0)
const rings = data.activityRings
const ringData = [
  { x: 'Move', y: Math.round((rings.move / rings.moveGoal) * 100) },
  { x: 'Exercise', y: Math.round((rings.exercise / rings.exerciseGoal) * 100) },
  { x: 'Stand', y: Math.round((rings.stand / rings.standGoal) * 100) },
]
const legendData = TOP_SPORTS.map((s, i) => ({
  name: s,
  symbol: { fill: PALETTE[i % PALETTE.length], type: 'square' as const },
}))

export function VictoryArea() {
  return (
    <VictoryChart theme={theme} height={250} padding={{ top: 12, right: 12, bottom: 32, left: 44 }}
      containerComponent={<VictoryVoronoiContainer />}>
      <VictoryAxis style={axisStyle} tickCount={5} tickFormat={(t: string) => t.slice(5)} />
      <VictoryAxis dependentAxis style={axisStyle} />
      <VArea
        data={hrSampled} x="date" y="value"
        style={{ data: { fill: `${PALETTE[0]}22`, stroke: PALETTE[0], strokeWidth: 2 } }}
        interpolation="monotoneX"
      />
    </VictoryChart>
  )
}

export function VictoryBar() {
  return (
    <VictoryChart theme={theme} height={250} padding={{ top: 12, right: 12, bottom: 32, left: 52 }}
      domainPadding={{ x: 6 }}>
      <VictoryAxis style={axisStyle} tickCount={5} />
      <VictoryAxis dependentAxis style={axisStyle} tickFormat={(t: number) => `${Math.round(t / 1000)}k`} />
      <VBar data={weeklySteps} x="week" y="steps"
        style={{ data: { fill: PALETTE[0] } }} barRatio={0.7} />
    </VictoryChart>
  )
}

// ★ Featured: stacked bar with proper legend labels (like Chart.js)
export function VictoryStacked() {
  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Standalone legend row */}
      <svg height={28} style={{ flexShrink: 0, overflow: 'visible' }}>
        <VictoryLegend
          standalone={false}
          width={360} height={28}
          x={4} y={6}
          data={legendData}
          orientation="horizontal"
          gutter={12}
          style={{ labels: { fontSize: 9, fill: '#6b7280' } }}
        />
      </svg>
      {/* Stacked bar chart */}
      <div style={{ flex: 1 }}>
        <VictoryChart
          theme={theme} height={220}
          padding={{ top: 8, right: 12, bottom: 32, left: 44 }}
          domainPadding={{ x: 10 }}
        >
          <VictoryAxis style={axisStyle} tickCount={6} tickFormat={(t: string) => t.slice(5)} />
          <VictoryAxis dependentAxis style={axisStyle} />
          <VictoryStack>
            {TOP_SPORTS.map((s, i) => (
              <VBar
                key={s}
                data={data.weeklyVolumeBySport.map(w => ({ x: w.week, y: (w[s] as number) || 0 }))}
                style={{ data: { fill: PALETTE[i % PALETTE.length] } }}
                barRatio={0.85}
              />
            ))}
          </VictoryStack>
        </VictoryChart>
      </div>
    </div>
  )
}

export function VictoryDonut() {
  return (
    <svg viewBox="0 0 400 260" style={{ width: '100%', height: '100%' }}>
      <VictoryPie
        standalone={false}
        width={400} height={260}
        data={data.sportBreakdown.map(s => ({ x: s.type, y: s.count }))}
        colorScale={PALETTE}
        innerRadius={70}
        labelRadius={125}
        labels={({ datum }) => (datum.y > 15 ? datum.x : '')}
        style={{ labels: { fontSize: 8, fill: '#374151' } }}
      />
    </svg>
  )
}

export function VictoryScatterChart() {
  return (
    <VictoryChart theme={theme} height={250} padding={{ top: 12, right: 16, bottom: 36, left: 44 }}>
      <VictoryAxis style={axisStyle} label="duration (min)" axisLabelComponent={<></>} />
      <VictoryAxis dependentAxis style={axisStyle} domain={[60, 180]} label="avg HR (bpm)" axisLabelComponent={<></>} />
      <VScatter
        data={data.workouts.filter(w => w.avgHr).map(w => ({ x: w.durationMin, y: w.avgHr }))}
        style={{ data: { fill: PALETTE[2], fillOpacity: 0.55 } }}
        size={4}
      />
    </VictoryChart>
  )
}

export function VictoryGauge() {
  return (
    <VictoryChart
      theme={theme} height={250}
      padding={{ top: 12, right: 16, bottom: 32, left: 80 }}
      domainPadding={{ x: 24 }} domain={{ y: [0, 120] }}
    >
      <VictoryAxis style={axisStyle} />
      <VictoryAxis dependentAxis style={axisStyle} tickFormat={(t: number) => `${t}%`} />
      <VBar
        horizontal
        data={ringData}
        style={{ data: { fill: ({ index }: { index?: number | string }) => [PALETTE[3], PALETTE[1], PALETTE[5]][Number(index ?? 0)] ?? PALETTE[0] } }}
        barRatio={0.6}
      />
    </VictoryChart>
  )
}

// unused import silence
export { VLine }

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
