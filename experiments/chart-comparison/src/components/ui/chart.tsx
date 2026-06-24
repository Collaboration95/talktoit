// Simplified shadcn/ui chart component (MIT — shadcn/ui)
import * as React from 'react'
import * as Recharts from 'recharts'
import { cn } from '@/lib/utils'

export type ChartConfig = Record<string, { label?: React.ReactNode; color?: string }>

type ChartCtx = { config: ChartConfig }
const ChartContext = React.createContext<ChartCtx | null>(null)
export function useChart() {
  const ctx = React.useContext(ChartContext)
  if (!ctx) throw new Error('useChart outside <ChartContainer>')
  return ctx
}

function ChartStyle({ id, config }: { id: string; config: ChartConfig }) {
  const entries = Object.entries(config).filter(([, v]) => v.color)
  if (!entries.length) return null
  return (
    <style dangerouslySetInnerHTML={{ __html: `[data-chart=${id}] {\n${entries.map(([k, v]) => `  --color-${k}: ${v.color};`).join('\n')}\n}` }} />
  )
}

export const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & {
    config: ChartConfig
    children: React.ComponentProps<typeof Recharts.ResponsiveContainer>['children']
  }
>(({ id, className, children, config, ...props }, ref) => {
  const uid = React.useId()
  const chartId = `chart-${id ?? uid.replace(/:/g, '')}`
  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        ref={ref}
        className={cn(
          'flex w-full h-full justify-center text-xs',
          '[&_.recharts-cartesian-axis-tick_text]:fill-[#6b7280]',
          '[&_.recharts-layer]:outline-none',
          '[&_.recharts-surface]:outline-none',
          className,
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        <Recharts.ResponsiveContainer width="100%" height="100%">
          {children}
        </Recharts.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
})
ChartContainer.displayName = 'ChartContainer'

// Tooltip — all recharts-injected props are optional so JSX element usage works
export type TooltipPayloadItem = {
  color?: string; fill?: string; stroke?: string
  name?: string; dataKey?: string
  value?: number | string
}

export type ChartTooltipContentProps = React.HTMLAttributes<HTMLDivElement> & {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string | number
  hideLabel?: boolean
  labelFormatter?: (label: string | number, payload: TooltipPayloadItem[]) => React.ReactNode
}

export const ChartTooltipContent = React.forwardRef<HTMLDivElement, ChartTooltipContentProps>(
  ({ active, payload, label, className, hideLabel, labelFormatter }, ref) => {
    if (!active || !payload?.length) return null
    return (
      <div ref={ref} className={cn('min-w-[8rem] rounded-lg border border-[#e5e7eb] bg-white px-2.5 py-2 text-[11px] shadow-xl grid gap-1', className)}>
        {!hideLabel && (
          <div className="font-medium text-[#111827]">
            {labelFormatter ? labelFormatter(label ?? '', payload) : String(label ?? '')}
          </div>
        )}
        <div className="grid gap-1">
          {payload.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full shrink-0" style={{ background: item.color ?? item.fill ?? item.stroke }} />
              <span className="text-[#6b7280]">{item.name}</span>
              <span className="ml-auto font-mono font-medium text-[#111827]">
                {typeof item.value === 'number' ? item.value.toLocaleString() : item.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    )
  }
)
ChartTooltipContent.displayName = 'ChartTooltipContent'

// Cast as any — recharts v3 made the content prop type overly strict
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const ChartTooltip = Recharts.Tooltip as any

// Legend
export type LegendPayloadItem = { value?: string | number; color?: string; type?: string }

export type ChartLegendContentProps = React.HTMLAttributes<HTMLDivElement> & {
  payload?: LegendPayloadItem[]
}

export const ChartLegendContent = React.forwardRef<HTMLDivElement, ChartLegendContentProps>(
  ({ className, payload }, ref) => {
    if (!payload?.length) return null
    return (
      <div ref={ref} className={cn('flex flex-wrap items-center justify-center gap-3 pt-2 text-[10px]', className)}>
        {payload.map((item, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className="h-2 w-2 shrink-0 rounded-[2px]" style={{ background: item.color }} />
            <span className="text-[#6b7280]">{String(item.value ?? '')}</span>
          </div>
        ))}
      </div>
    )
  }
)
ChartLegendContent.displayName = 'ChartLegendContent'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const ChartLegend = Recharts.Legend as any
