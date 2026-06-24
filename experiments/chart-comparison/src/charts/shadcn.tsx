// shadcn/ui chart components — uses recharts + shadcn ChartContainer
// Demonstrates the shadcn chart aesthetic: clean tooltips, CSS-variable-based colors, minimal chrome
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Legend,
} from 'recharts'
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, ChartLegendContent } from '@/components/ui/chart'
import type { ChartConfig } from '@/components/ui/chart'
import data, { TOP_SPORTS } from '../data'

const weeklySteps = buildWeeklySteps()
const rings = data.activityRings
const pct = (v: number, g: number) => Math.round((v / g) * 100)

// shadcn color palette (chart-1 through chart-5 from shadcn zinc theme)
const SC = ['hsl(220 70% 50%)', 'hsl(160 60% 45%)', 'hsl(30 80% 55%)', 'hsl(280 65% 60%)', 'hsl(340 75% 55%)', 'hsl(198 82% 45%)']

const hrConfig: ChartConfig = { value: { label: 'Resting HR', color: SC[0] } }
const stepsConfig: ChartConfig = { steps: { label: 'Steps', color: SC[0] } }
const stackedConfig: ChartConfig = Object.fromEntries(TOP_SPORTS.map((s, i) => [s, { label: s, color: SC[i % SC.length] }]))
const scatterConfig: ChartConfig = { workouts: { label: 'Workouts', color: SC[2] } }
const ringConfig: ChartConfig = {
  move: { label: 'Move', color: SC[3] },
  exercise: { label: 'Exercise', color: SC[1] },
  stand: { label: 'Stand', color: SC[5] },
}
const pieConfig: ChartConfig = Object.fromEntries(data.sportBreakdown.map((s, i) => [s.type, { label: s.type, color: SC[i % SC.length] }]))

const ax = { fontSize: 10, fill: '#6b7280' }
const grid = <CartesianGrid strokeDasharray="3 3" stroke="#f0f3f7" />

export function ShadcnArea() {
  return (
    <ChartContainer config={hrConfig} className="h-full w-full">
      <AreaChart data={data.restingHrDaily} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        <defs>
          <linearGradient id="sc-hr" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={SC[0]} stopOpacity={0.3} />
            <stop offset="95%" stopColor={SC[0]} stopOpacity={0} />
          </linearGradient>
        </defs>
        {grid}
        <XAxis dataKey="date" tickFormatter={d => String(d).slice(5)} tick={ax} minTickGap={40} />
        <YAxis tick={ax} domain={['dataMin - 2', 'dataMax + 2']} />
        <ChartTooltip content={<ChartTooltipContent hideLabel />} />
        <Area type="monotone" dataKey="value" name="Resting HR" stroke={SC[0]} fill="url(#sc-hr)" strokeWidth={2} dot={false} />
      </AreaChart>
    </ChartContainer>
  )
}

export function ShadcnBar() {
  return (
    <ChartContainer config={stepsConfig} className="h-full w-full">
      <BarChart data={weeklySteps} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        {grid}
        <XAxis dataKey="week" tick={ax} minTickGap={20} />
        <YAxis tick={ax} tickFormatter={v => `${Math.round(Number(v) / 1000)}k`} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="steps" name="Steps" fill={SC[0]} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartContainer>
  )
}

export function ShadcnStacked() {
  return (
    <ChartContainer config={stackedConfig} className="h-full w-full">
      <BarChart data={data.weeklyVolumeBySport} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        {grid}
        <XAxis dataKey="week" tickFormatter={w => String(w).slice(5)} tick={ax} minTickGap={20} />
        <YAxis tick={ax} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <ChartLegend content={<ChartLegendContent />} />
        {TOP_SPORTS.map((s, i) => (
          <Bar key={s} dataKey={s} name={s} stackId="v" fill={SC[i % SC.length]} radius={i === TOP_SPORTS.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
        ))}
      </BarChart>
    </ChartContainer>
  )
}

export function ShadcnDonut() {
  return (
    <ChartContainer config={pieConfig} className="h-full w-full">
      <PieChart>
        <Pie data={data.sportBreakdown} dataKey="count" nameKey="type" innerRadius={55} outerRadius={90} paddingAngle={1}>
          {data.sportBreakdown.map((s, i) => <Cell key={s.type} fill={SC[i % SC.length]} />)}
        </Pie>
        <ChartTooltip content={<ChartTooltipContent />} />
        <Legend wrapperStyle={{ fontSize: 9 }} />
      </PieChart>
    </ChartContainer>
  )
}

export function ShadcnScatter() {
  return (
    <ChartContainer config={scatterConfig} className="h-full w-full">
      <ScatterChart margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        {grid}
        <XAxis type="number" dataKey="durationMin" name="min" tick={ax} unit="m" />
        <YAxis type="number" dataKey="avgHr" name="bpm" tick={ax} domain={[60, 180]} />
        <ChartTooltip content={<ChartTooltipContent />} cursor={{ strokeDasharray: '3 3' }} />
        <Scatter data={data.workouts.filter(w => w.avgHr)} fill={SC[2]} fillOpacity={0.6} name="Workout" />
      </ScatterChart>
    </ChartContainer>
  )
}

export function ShadcnGauge() {
  const ringData = [
    { name: 'Move', value: pct(rings.move, rings.moveGoal), fill: SC[3] },
    { name: 'Exercise', value: pct(rings.exercise, rings.exerciseGoal), fill: SC[1] },
    { name: 'Stand', value: pct(rings.stand, rings.standGoal), fill: SC[5] },
  ]
  return (
    <div className="h-full w-full flex flex-col">
      {/* inline legend — recharts v3 Legend no longer accepts a custom payload prop */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 12, paddingTop: 6, fontSize: 10, color: '#6b7280', flexShrink: 0 }}>
        {ringData.map(r => (
          <span key={r.name} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: r.fill, display: 'inline-block' }} />
            {r.name} {r.value}%
          </span>
        ))}
      </div>
      <ChartContainer config={ringConfig} className="flex-1 w-full">
        <PieChart>
          {ringData.map((r, i) => (
            <Pie key={r.name} data={[{ value: r.value }, { value: Math.max(0, 100 - r.value) }]}
              dataKey="value" innerRadius={28 + i * 22} outerRadius={44 + i * 22}
              startAngle={90} endAngle={-270} paddingAngle={0}>
              <Cell fill={r.fill} />
              <Cell fill="#f1f3f6" />
            </Pie>
          ))}
          <ChartTooltip content={<ChartTooltipContent hideLabel />} />
        </PieChart>
      </ChartContainer>
    </div>
  )
}

// Standalone line chart for HRV
export function ShadcnLine() {
  const config: ChartConfig = { value: { label: 'HRV (ms)', color: SC[3] } }
  return (
    <ChartContainer config={config} className="h-full w-full">
      <LineChart data={data.hrvDaily} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        {grid}
        <XAxis dataKey="date" tickFormatter={d => String(d).slice(5)} tick={ax} minTickGap={40} />
        <YAxis tick={ax} />
        <ChartTooltip content={<ChartTooltipContent hideLabel />} />
        <Line type="monotone" dataKey="value" name="HRV" stroke={SC[3]} strokeWidth={2} dot={false} />
      </LineChart>
    </ChartContainer>
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
