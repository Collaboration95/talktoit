import { render, screen } from '@testing-library/react'
import { WorkoutCard } from '@/templates/workout-card'
import type { WorkoutCardData } from '@/types/templates'

const validData: WorkoutCardData = {
  activity_type: 'Running',
  date: '2026-06-05T07:00:00+08:00',
  duration_minutes: 45.5,
  avg_heart_rate: 148,
  max_heart_rate: 178,
  distance_meters: 8500,
  distance_unit: 'km',
  energy_burned_kj: 2500,
  elevation_ascent_meters: 45,
}

describe('WorkoutCard', () => {
  it('renders activity type', () => {
    render(<WorkoutCard data={validData} />)
    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('renders duration', () => {
    render(<WorkoutCard data={validData} />)
    expect(screen.getByText('45.5 min')).toBeInTheDocument()
  })

  it('renders distance as km', () => {
    render(<WorkoutCard data={validData} />)
    expect(screen.getByText('8.50 km')).toBeInTheDocument()
  })

  it('renders narrative when provided', () => {
    render(<WorkoutCard data={validData} narrative="Great run!" />)
    expect(screen.getByText('Great run!')).toBeInTheDocument()
  })

  it('renders with null heart rate without crashing', () => {
    render(<WorkoutCard data={{ ...validData, avg_heart_rate: null, max_heart_rate: null }} />)
    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('renders with null distance without crashing', () => {
    render(<WorkoutCard data={{ ...validData, distance_meters: null }} />)
    expect(screen.getByText('Running')).toBeInTheDocument()
  })
})
