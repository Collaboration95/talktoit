import { useEffect, useMemo, useState } from 'react'
import { fetchWorkoutDetail } from '@/api/dashboard'
import type { WorkoutDetail as WorkoutDetailType } from '@/api/dashboard'
import ReactECharts from 'echarts-for-react'
import {
  formatDateTime,
  formatDistanceKm,
  formatDurationMinutes,
  formatMetricValue,
  formatNumber,
} from '@/lib/format'

interface WorkoutDetailProps {
  workoutId: number
  fingerprint?: string
  onBack: () => void
}

/** Renders full detail for a single workout, including GPS map and metadata (R1-01). */
export function WorkoutDetail({ workoutId, fingerprint, onBack }: WorkoutDetailProps) {
  const [data, setData] = useState<WorkoutDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchWorkoutDetail(workoutId, fingerprint)
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load workout')
      })
      .finally(() => setLoading(false))
  }, [fingerprint, workoutId])

  // Memoized above the loading/error early-returns (hooks must run every render).
  const gpsRoute = data?.gps_route
  const gpsOption = useMemo(() => {
    if (!gpsRoute || gpsRoute.coordinates.length === 0) return null
    const longitudes = gpsRoute.coordinates.map(([longitude]) => longitude)
    const latitudes = gpsRoute.coordinates.map(([, latitude]) => latitude)
    const longitudeRange = Math.max(...longitudes) - Math.min(...longitudes) || 0.001
    const latitudeRange = Math.max(...latitudes) - Math.min(...latitudes) || 0.001
    const longitudePadding = longitudeRange * 0.08
    const latitudePadding = latitudeRange * 0.08
    return {
      tooltip: { trigger: 'item' },
      xAxis: {
        type: 'value',
        name: 'Longitude',
        min: Math.min(...longitudes) - longitudePadding,
        max: Math.max(...longitudes) + longitudePadding,
        axisLabel: { fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: 'Latitude',
        min: Math.min(...latitudes) - latitudePadding,
        max: Math.max(...latitudes) + latitudePadding,
        axisLabel: { fontSize: 10 },
      },
      series: [
        {
          type: 'line',
          data: gpsRoute.coordinates,
          showSymbol: false,
          lineStyle: { width: 3, color: '#2563eb' },
          markPoint: {
            data: [
              { name: 'Start', coord: gpsRoute.coordinates[0], symbol: 'circle' },
              {
                name: 'End',
                coord: gpsRoute.coordinates[gpsRoute.coordinates.length - 1],
                symbol: 'pin',
              },
            ],
          },
        },
      ],
    }
  }, [gpsRoute])

  function downloadRoute() {
    if (!data?.gps_route) return
    const blob = new Blob([JSON.stringify(data.gps_route, null, 2)], {
      type: 'application/geo+json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `workout-${data.id}-route.geojson`
    link.click()
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500" data-testid="loading">
        Loading workout…
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4">
        <p className="text-sm font-medium text-red-700">Error</p>
        <p className="mt-1 text-sm text-red-600">{error ?? 'Workout not found'}</p>
        <button onClick={onBack} className="mt-3 text-sm text-blue-600 hover:underline">
          ← Back to list
        </button>
      </div>
    )
  }

  const distanceKm = formatDistanceKm(data.distance_meters)

  const detailMetrics: { label: string; value: string | null }[] = [
    {
      label: 'Duration',
      value: formatDurationMinutes(data.duration_minutes),
    },
    { label: 'Avg HR', value: formatMetricValue(data.avg_heart_rate, 'bpm') },
    { label: 'Max HR', value: formatMetricValue(data.max_heart_rate, 'bpm') },
    { label: 'Distance', value: distanceKm },
    {
      label: 'Energy',
      value: formatMetricValue(data.energy_burned_kj, 'kJ'),
    },
    {
      label: 'Elevation',
      value: formatMetricValue(data.elevation_ascent_meters, 'm'),
    },
  ]

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <button onClick={onBack} className="mb-4 text-sm text-blue-600 hover:underline">
        ← Back to list
      </button>

      <h2 className="text-xl font-bold text-gray-900">{data.activity_type}</h2>
      <p className="text-sm text-gray-500">
        {formatDateTime(data.date)} · via {data.source_name}
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {detailMetrics.map(
          (m) =>
            m.value !== null && (
              <div key={m.label} className="rounded-lg bg-gray-50 p-3">
                <p className="text-xs text-gray-500">{m.label}</p>
                <p className="mt-1 font-semibold tabular-nums text-gray-900">{m.value}</p>
              </div>
            ),
        )}
      </div>

      {/* Ordered route line plus explicit start/end evidence markers. */}
      {gpsOption !== null ? (
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-gray-500">GPS Route</p>
            <button
              type="button"
              onClick={downloadRoute}
              className="text-xs font-medium text-blue-600 hover:underline"
            >
              Download GeoJSON
            </button>
          </div>
          {data.route_summary ? (
            <div className="mb-2 grid grid-cols-2 gap-2 text-xs text-gray-600 sm:grid-cols-3">
              <RouteFact
                label="Route points"
                value={formatNumber(data.route_summary.point_count)}
              />
              <RouteFact
                label="Approx. route"
                value={formatDistanceKm(data.route_summary.distance_meters)}
              />
              <RouteFact
                label="Bounds"
                value={`${formatNumber(data.route_summary.bounds.max_latitude - data.route_summary.bounds.min_latitude, 3)}° latitude`}
              />
            </div>
          ) : null}
          <ReactECharts option={gpsOption} style={{ height: 250 }} />
        </div>
      ) : null}

      {/* Metadata table */}
      {data.metadata.length > 0 ? (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium text-gray-500">Metadata</p>
          <table className="w-full text-sm">
            <tbody>
              {data.metadata.map((m) => (
                <tr key={m.key} className="border-b last:border-0">
                  <td className="py-1 pr-4 font-medium text-gray-600">{m.key}</td>
                  <td className="py-1 text-gray-700">{m.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

function RouteFact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded bg-gray-50 px-2 py-1.5">
      <span className="block text-gray-400">{label}</span>
      <span className="font-medium text-gray-700">{value ?? '—'}</span>
    </div>
  )
}
