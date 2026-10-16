import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ApiClient } from '../api/client'
import { bounds, formatMinutes, routeDistance } from '../navigation/format'
import { createNavApi, NavApiError } from '../navigation/navApi'
import type { NavRoute, NavStationResponse } from '../navigation/types'
import { baseState, response } from './fixtures'

// ---- fake navigation API (the screen uses the module-level `navApi`) -----------------
const station: NavStationResponse = {
  station: {
    station_id: 'test_town', station_name: 'Test Town',
    map: { image: '/data/stations/test_town/map.png', width: 1000, height: 1000 },
    nodes: [
      { id: 'ent', name: 'Main Gate', type: 'entrance', position: [0.1, 0.1], verification: 'pending', accessible: 'unknown', status: 'open' },
      { id: 'j1', name: 'Junction 1', type: 'junction', position: [0.5, 0.1], verification: 'pending', accessible: 'unknown', status: 'open' },
      { id: 'p1', name: 'Platform 1', type: 'platform', position: [0.5, 0.9], verification: 'pending', accessible: 'unknown', status: 'open' },
      { id: 'wc', name: 'Toilet', type: 'toilet', position: [0.9, 0.9], verification: 'pending', accessible: 'unknown', status: 'open' },
    ],
    edges: [
      { id: 'e1', from: 'ent', to: 'j1', path_type: 'walkway', status: 'open', verification: 'pending', accessible: 'unknown', geometry: [[0.1, 0.1], [0.3, 0.12], [0.5, 0.1]] },
      { id: 'e2', from: 'j1', to: 'p1', path_type: 'walkway', status: 'open', verification: 'pending', accessible: 'unknown', geometry: [[0.5, 0.1], [0.5, 0.9]] },
      { id: 'e3', from: 'p1', to: 'wc', path_type: 'stairs', status: 'open', verification: 'pending', accessible: 'unknown', geometry: [[0.5, 0.9], [0.9, 0.9]] },
    ],
  },
  metadata: { data_status: 'mock', notes: [] },
}
const okRoute: NavRoute = {
  status: 'ok', station_id: 'test_town', source: 'ent', destination: 'p1', node_ids: ['ent', 'j1', 'p1'], edge_ids: ['e1', 'e2'],
  geometry: [[0.1, 0.1], [0.3, 0.12], [0.5, 0.1], [0.5, 0.9]],
  segments: [
    { edge_id: 'e1', from_node: 'ent', to_node: 'j1', geometry: [[0.1, 0.1], [0.3, 0.12], [0.5, 0.1]], verification: 'pending', accessible: 'unknown' },
    { edge_id: 'e2', from_node: 'j1', to_node: 'p1', geometry: [[0.5, 0.1], [0.5, 0.9]], verification: 'pending', accessible: 'unknown' },
  ],
  distance_m: null, estimated_distance_m: 160, distance_basis: 'estimated_from_map_scale', estimated_duration_s: 133,
  duration_assumption: 'Assumes an average walking speed of 1.2 m/s; not measured.', accessibility_confidence: 'not_applicable',
  warnings: ['2 of 2 pathway(s) are not verified on site.'],
  instructions: [
    { step: 1, text: 'Start at Main Gate and walk east to Junction 1.', node_id: 'ent', edge_id: 'e1', distance_is_estimate: true },
    { step: 2, text: 'Turn right at Junction 1 and walk south to Platform 1.', node_id: 'j1', edge_id: 'e2', distance_is_estimate: true },
    { step: 3, text: 'Arrive at Platform 1.', node_id: 'p1', edge_id: null, distance_is_estimate: false },
  ],
  reason: null, explanation: null, blocking_edge_ids: [], previous_route_blocked: false, previous_route_blocked_edge_ids: [],
  simulated_disruptions_applied: [],
  along_the_way: [{ node_id: 'wc', name: 'Toilet', type: 'toilet', on_route: false, distance_from_route_m: 12, progress: 0.9 }],
}
const noRoute: NavRoute = {
  ...okRoute, status: 'no_route', node_ids: [], edge_ids: [], geometry: [], segments: [], instructions: [], along_the_way: [],
  reason: 'accessibility_constraints', explanation: 'No step-free route: every path to Toilet uses stairs.',
}
const NO_PREFS = { avoid_stairs: false, wheelchair: false, require_verified_accessibility: false }

const fakeNav = vi.hoisted(() => ({
  base: 'http://test',
  imageUrl: (p: string) => `http://test${p}`,
  stations: vi.fn(),
  station: vi.fn(),
  adminStatus: vi.fn(),
  info: vi.fn(),
  route: vi.fn(),
  disruptions: vi.fn(),
  closeEdge: vi.fn(),
  removeDisruption: vi.fn(),
}))

vi.mock('../navigation/navApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../navigation/navApi')>()
  return { ...actual, navApi: fakeNav }
})

const { default: App } = await import('../App')

function plannerClient(needs: string[] = []): ApiClient {
  const state = { ...baseState, journey: { ...baseState.journey, passenger_needs: needs } }
  return {
    baseUrl: 'http://test',
    health: vi.fn().mockResolvedValue({ status: 'ok', api_version: '0.1.0', data_mode: 'demo', data_provider: { requested: 'demo', active: 'demo', reason: null }, ai: {} }),
    reference: vi.fn().mockResolvedValue({ places: [], classes: [], passenger_needs: [], budget_priorities: [], transfer_preferences: [], disruption_events: [], data_notice: '' }),
    createSession: vi.fn().mockResolvedValue(response(state as never, 'hi')),
  } as unknown as ApiClient
}

beforeEach(() => {
  vi.clearAllMocks()
  fakeNav.stations.mockResolvedValue([{ station_id: 'test_town', station_name: 'Test Town', node_count: 4, edge_count: 3, data_status: 'mock', city: null }])
  fakeNav.station.mockResolvedValue(station)
  fakeNav.adminStatus.mockResolvedValue({ public_disruption_simulation: true })
  fakeNav.disruptions.mockResolvedValue([])
  fakeNav.route.mockImplementation(async (_s: string, from: string, to: string) => ({ ...okRoute, source: from, destination: to }))
  fakeNav.closeEdge.mockResolvedValue({ id: 'd1', target_type: 'edge', target_id: 'e2', kind: 'pathway_closure', reason: 'x', simulated: true })
  window.location.hash = '/navigation'
})

async function openNav(needs: string[] = []) {
  const user = userEvent.setup()
  render(<App client={plannerClient(needs)} />)
  await screen.findByRole('combobox', { name: 'To' })
  return user
}

async function routeTo(user: ReturnType<typeof userEvent.setup>, id: string) {
  await user.selectOptions(screen.getByRole('combobox', { name: 'To' }), id)
  await screen.findByTestId('route-line')
}

describe('format helpers', () => {
  it('rounds durations up to whole minutes and prefers measured distances', () => {
    expect(formatMinutes(133)).toBe(2)
    expect(formatMinutes(10)).toBe(1)
    expect(formatMinutes(null)).toBeNull()
    expect(routeDistance(okRoute)).toBe(160)
    expect(routeDistance({ ...okRoute, distance_m: 150 })).toBe(150)
  })

  it('computes the bounding box of a polyline', () => {
    expect(bounds(okRoute.geometry)).toEqual({ minX: 0.1, minY: 0.1, maxX: 0.5, maxY: 0.9 })
    expect(bounds([])).toBeNull()
  })
})

describe('navApi', () => {
  it('reports backend detail messages and unreachable servers', async () => {
    const api = createNavApi('http://x', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'unknown_node', message: 'Unknown node' } }), { status: 404 })))
    await expect(api.route('s', 'a', 'b', NO_PREFS)).rejects.toMatchObject({ status: 404, message: 'Unknown node' })
    const down = createNavApi('http://x', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    await expect(down.stations()).rejects.toBeInstanceOf(NavApiError)
  })
})

describe('Station Navigation screen', () => {
  it('lists real places (no junctions), routes as soon as a destination is chosen and draws the stored polyline', async () => {
    const user = await openNav()
    expect(screen.getByRole('heading', { name: 'Station Navigation' })).toBeInTheDocument()
    const to = screen.getByRole('combobox', { name: 'To' })
    expect(within(to).queryByText('Junction 1')).not.toBeInTheDocument()
    expect(screen.getByText('Choose a destination to draw the route on the floor plan.')).toBeInTheDocument()
    expect(fakeNav.route).not.toHaveBeenCalled()
    await routeTo(user, 'p1')
    expect(fakeNav.route).toHaveBeenCalledWith('test_town', 'ent', 'p1', NO_PREFS, [])
    expect(screen.getByTestId('route-line').getAttribute('points')).toBe('100,100 300,120 500,100 500,900')
    expect(screen.getByTestId('source-pin')).toBeInTheDocument()
    expect(screen.getByTestId('destination-pin')).toBeInTheDocument()
    const summary = screen.getByLabelText('Route summary')
    expect(summary).toHaveTextContent('2 min')
    expect(summary).toHaveTextContent('160 m')
    expect(summary).toHaveTextContent('Shortest route')
    expect(summary).toHaveTextContent('(estimate)')
    expect(summary).toHaveTextContent('Assumes an average walking speed of 1.2 m/s')
    expect(screen.getByText(/not yet verified on site/)).toBeInTheDocument()
  })

  it('recalculates when either endpoint changes and when the endpoints are swapped', async () => {
    const user = await openNav()
    await routeTo(user, 'p1')
    await user.selectOptions(screen.getByRole('combobox', { name: 'To' }), 'wc')
    await waitFor(() => expect(fakeNav.route).toHaveBeenLastCalledWith('test_town', 'ent', 'wc', NO_PREFS, []))
    await user.click(screen.getByRole('button', { name: 'Swap start and destination' }))
    await waitFor(() => expect(fakeNav.route).toHaveBeenLastCalledWith('test_town', 'wc', 'ent', NO_PREFS, []))
    expect(screen.getByRole('combobox', { name: 'From' })).toHaveValue('wc')
    expect(screen.getByRole('combobox', { name: 'To' })).toHaveValue('ent')
    expect(screen.getByLabelText('Route summary')).toHaveTextContent('Toilet → Main Gate')
  })

  it('flags identical endpoints as invalid input instead of calling the engine', async () => {
    const user = await openNav()
    await routeTo(user, 'p1')
    fakeNav.route.mockClear()
    await user.selectOptions(screen.getByRole('combobox', { name: 'From' }), 'p1')
    expect(await screen.findAllByText(/Start and destination are the same place/)).not.toHaveLength(0)
    expect(screen.queryByTestId('route-line')).not.toBeInTheDocument()
    expect(fakeNav.route).not.toHaveBeenCalled()
  })

  it('pre-selects wheelchair routing when the passenger asked for a wheelchair', async () => {
    const user = await openNav(['wheelchair'])
    await waitFor(() => expect(screen.getByRole('button', { name: /Wheelchair Friendly/ })).toHaveAttribute('aria-pressed', 'true'))
    await routeTo(user, 'p1')
    expect(fakeNav.route.mock.calls[fakeNav.route.mock.calls.length - 1][3]).toMatchObject({ wheelchair: true, avoid_stairs: true })
    expect(screen.getByLabelText('Route summary')).toHaveTextContent('Shortest route for your preferences')
  })

  it('toggling an accessibility preference recalculates with the new constraints', async () => {
    const user = await openNav()
    await routeTo(user, 'p1')
    await user.click(screen.getByRole('button', { name: /Avoid Stairs/ }))
    await waitFor(() => expect(fakeNav.route).toHaveBeenLastCalledWith('test_town', 'ent', 'p1', { ...NO_PREFS, avoid_stairs: true }, []))
    await user.click(screen.getByRole('button', { name: /Verified Pathways Only/ }))
    await waitFor(() => expect(fakeNav.route).toHaveBeenLastCalledWith('test_town', 'ent', 'p1', { ...NO_PREFS, avoid_stairs: true, require_verified_accessibility: true }, []))
  })

  it('keeps the Map and Step-by-Step views on the same route', async () => {
    const user = await openNav()
    await routeTo(user, 'p1')
    await user.click(screen.getByRole('tab', { name: 'Step-by-Step' }))
    const steps = within(screen.getByRole('list', { name: 'Step-by-Step' })).getAllByRole('listitem')
    expect(steps.map((s) => s.textContent)).toEqual([
      '1Start at Main Gate and walk east to Junction 1.',
      '2Turn right at Junction 1 and walk south to Platform 1.',
      '3Arrive at Platform 1.',
    ])
    expect(screen.queryByTestId('route-line')).not.toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Map View' }))
    expect(screen.getByTestId('route-line').getAttribute('points')).toBe('100,100 300,120 500,100 500,900')
    expect(fakeNav.route).toHaveBeenCalledTimes(1)
  })

  it('steps through the instructions in order and can exit navigation', async () => {
    const user = await openNav()
    await routeTo(user, 'p1')
    expect(screen.queryByTestId('current-step-marker')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Start Navigation/ }))
    expect(screen.getByRole('status')).toHaveTextContent('Step 1 of 3')
    expect(screen.getByRole('status')).toHaveTextContent('Start at Main Gate')
    expect(screen.getByRole('status')).toHaveTextContent('not your real location')
    expect(screen.getByTestId('current-step-marker')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Next step/ }))
    expect(screen.getByRole('status')).toHaveTextContent('Step 2 of 3')
    await user.click(screen.getByRole('tab', { name: 'Step-by-Step' }))
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Turn right at Junction 1')
    await user.click(screen.getByRole('button', { name: /Previous/ }))
    expect(screen.getByRole('status')).toHaveTextContent('Step 1 of 3')
    await user.click(screen.getByRole('button', { name: /Next step/ }))
    await user.click(screen.getByRole('button', { name: /Next step/ }))
    expect(screen.getByRole('status')).toHaveTextContent('Step 3 of 3')
    await user.click(screen.getByRole('button', { name: /Finish/ }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Start Navigation/ })).toBeInTheDocument()
  })

  it('zoom controls change the map scale within bounds', async () => {
    const user = await openNav()
    const map = screen.getByTestId('station-map')
    expect(map).toHaveAttribute('data-zoom', '1.6')
    await user.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(map).toHaveAttribute('data-zoom', '2.4')
    await user.click(screen.getByRole('button', { name: 'Zoom out' }))
    await user.click(screen.getByRole('button', { name: 'Zoom out' }))
    expect(map).toHaveAttribute('data-zoom', '1')
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeDisabled()
    expect(screen.getByRole('img', { name: /North is up/ })).toBeInTheDocument()
  })

  it('a simulated closure reroutes with the previous edges and explains it once', async () => {
    const user = await openNav()
    await routeTo(user, 'p1')
    fakeNav.route.mockResolvedValueOnce({ ...okRoute, previous_route_blocked: true,
      warnings: ['SIMULATED DISRUPTION: your previous route is blocked at e2. Showing an alternative route.'] })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Simulate a closure' }), 'e2')
    await user.click(screen.getByRole('button', { name: /Close pathway/ }))
    expect(fakeNav.closeEdge).toHaveBeenCalledWith('test_town', 'e2')
    await waitFor(() => expect(fakeNav.route).toHaveBeenLastCalledWith('test_town', 'ent', 'p1', NO_PREFS, ['e1', 'e2']))
    expect(await screen.findAllByText(/previous route is blocked/)).toHaveLength(1)
    expect(screen.getByText(/Simulated closures active: 1/)).toBeInTheDocument()
    expect(screen.getByTestId('closed-edge')).toBeInTheDocument()
  })

  it('explains an unreachable destination and offers to relax the active preference', async () => {
    const user = await openNav()
    await user.click(screen.getByRole('button', { name: /Avoid Stairs/ }))
    fakeNav.route.mockResolvedValueOnce(noRoute)
    await user.selectOptions(screen.getByRole('combobox', { name: 'To' }), 'wc')
    expect(await screen.findByText('No step-free route: every path to Toilet uses stairs.')).toBeInTheDocument()
    expect(screen.queryByTestId('route-line')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Choose a destination|Calculating/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '✕ Avoid Stairs' }))
    await waitFor(() => expect(fakeNav.route).toHaveBeenLastCalledWith('test_town', 'ent', 'wc', NO_PREFS, []))
    expect(await screen.findByTestId('route-line')).toBeInTheDocument()
  })

  it('reports an unreachable navigation backend', async () => {
    fakeNav.stations.mockRejectedValue(new NavApiError(0, 'Cannot reach the RailSaathi server for station navigation.'))
    render(<App client={plannerClient()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the RailSaathi server')
  })
})
