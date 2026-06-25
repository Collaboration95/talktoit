import type { WorkoutCardData } from '@/types/templates'

interface WorkoutCardProps {
  data: WorkoutCardData
  narrative?: string
}

/** Renders a single workout session summary card. */
export function WorkoutCard({ data, narrative }: WorkoutCardProps) {
  const distanceKm = data.distance_meters !== null ? (data.distance_meters / 1000).toFixed(2) : null

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      {narrative ? <p className="mb-4 text-gray-600">{narrative}</p> : null}
      <h2 className="text-xl font-bold text-gray-900">{data.activity_type}</h2>
      <p className="text-sm text-gray-500">{new Date(data.date).toLocaleString()}</p>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Duration" value={`${data.duration_minutes} min`} />
        {data.avg_heart_rate !== null ? (
          <Metric label="Avg HR" value={`${data.avg_heart_rate} bpm`} />
        ) : null}
        {data.max_heart_rate !== null ? (
          <Metric label="Max HR" value={`${data.max_heart_rate} bpm`} />
        ) : null}
        {distanceKm !== null ? <Metric label="Distance" value={`${distanceKm} km`} /> : null}
        {data.energy_burned_kj !== null ? (
          <Metric label="Energy" value={`${data.energy_burned_kj} kJ`} />
        ) : null}
        {data.elevation_ascent_meters !== null ? (
          <Metric label="Elevation" value={`${data.elevation_ascent_meters} m`} />
        ) : null}
      </div>
      {/* GPS guard: check key presence per SPEC §2.1 ("gps_route" in data means GPS exists) */}
      {'gps_route' in data && data.gps_route !== null ? (
        <p className="mt-3 text-xs text-gray-400">GPS route available</p>
      ) : null}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-gray-50 p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 font-semibold text-gray-900">{value}</p>
    </div>
  )
}
