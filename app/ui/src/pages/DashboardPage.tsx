import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  BellRing,
  Building2,
  Check,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Database,
  LockKeyhole,
  Plus,
  Radio,
  ShieldCheck,
  Signal,
  TrendingUp,
  Workflow,
  RefreshCw,
  Monitor,
  X,
} from 'lucide-react'
import {
  addSubsidiaryTender,
  checkHealth,
  getApiErrorMessage,
  listSubsidiaries,
  listSubsidiaryTenders,
  listTenders,
  syncData,
  Subsidiary,
  TenderEvent,
  SyncResult,
} from '../services/api'

type PipelineSignal = {
  id: string
  title: string
  reference: string
  stage: string
  probability: number | null
  updated: string
  material: string
  recipient: string
  sourceType?: string
  provenance?: string
}

type SubsidiaryStage = 'Won' | 'Lost' | 'In Progress'

const EMPTY_SUBSIDIARY_FORM = {
  tender_id: '',
  project_name: '',
  stage: 'In Progress' as SubsidiaryStage,
  materials: '',
  tender_value: '',
  opening_date: '',
  closing_date: '',
}

function displayDate(value?: string | null) {
  return value ? new Date(value).toLocaleDateString() : '—'
}

function simplifyStage(stage: string) {
  const normalized = stage.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
  const simpleNames: Record<string, string> = {
    'bid submitted': 'Bid sent',
    'technical evaluation': 'Under review',
    'preferred bidder': 'Buyer prefers our bid',
  }
  return simpleNames[normalized] || stage.trim() || 'Unspecified'
}

function stageKey(stage: string) {
  return stage.trim().toLowerCase() || 'unspecified'
}

function StatusPill({ stage }: { stage: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-200 dark:bg-indigo-900/20 dark:text-indigo-300 dark:ring-indigo-800">
      {stage}
    </span>
  )
}

export default function DashboardPage() {
  const [apiReachable, setApiReachable] = useState<boolean | null>(null)
  const [signals, setSignals] = useState<PipelineSignal[]>([])
  const [filter, setFilter] = useState('All stages')
  const [syncStatus, setSyncStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle')
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null)
  const [subsidiaries, setSubsidiaries] = useState<Subsidiary[]>([])
  const [subsidiaryMenuOpen, setSubsidiaryMenuOpen] = useState(false)
  const [selectedSubsidiary, setSelectedSubsidiary] = useState<Subsidiary | null>(null)
  const [subsidiaryTenders, setSubsidiaryTenders] = useState<TenderEvent[]>([])
  const [subsidiaryLoading, setSubsidiaryLoading] = useState(false)
  const [subsidiaryError, setSubsidiaryError] = useState('')
  const [showAddDetails, setShowAddDetails] = useState(false)
  const [detailsForm, setDetailsForm] = useState(EMPTY_SUBSIDIARY_FORM)
  const [detailsSaving, setDetailsSaving] = useState(false)
  const subsidiaryRequestId = useRef(0)
  const pipelineSectionRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let active = true
    checkHealth()
      .then(() => {
        if (active) setApiReachable(true)
      })
      .catch(() => {
        if (active) setApiReachable(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const load = async () => {
    try {
      const res = await listTenders()
      const data = res.data ?? []
      if (active) {
        setSignals(
          data.map((item: TenderEvent) => ({
              id: item.id,
              title: item.project_name || 'Untitled',
              reference: item.tender_id,
              stage: item.stage,
              probability: item.existing_win_probability_percent,
              updated: item.source_updated_at || item.ingested_at || '',
              material: (item.material_categories ?? []).join(' Â· ') || 'No materials listed',
              recipient: 'Pending',
              sourceType: item.source_type,
              provenance: item.data_provenance,
            }))
          )
        }
      } catch {
        if (active) setSignals([])
      }
    }
    load()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    listSubsidiaries()
      .then(({ data }) => {
        if (active) setSubsidiaries(data)
      })
      .catch((err) => {
        if (active) setSubsidiaryError(getApiErrorMessage(err, 'Unable to load subsidiaries.'))
      })
    return () => {
      active = false
    }
  }, [])

  const loadSubsidiaryTenders = async (subsidiaryId: string) => {
    const requestId = ++subsidiaryRequestId.current
    setSubsidiaryLoading(true)
    setSubsidiaryError('')
    try {
      const { data } = await listSubsidiaryTenders(subsidiaryId)
      if (requestId === subsidiaryRequestId.current) setSubsidiaryTenders(data)
    } catch (err) {
      if (requestId === subsidiaryRequestId.current) {
        setSubsidiaryError(getApiErrorMessage(err, 'Unable to load subsidiary tenders.'))
      }
    } finally {
      if (requestId === subsidiaryRequestId.current) setSubsidiaryLoading(false)
    }
  }

  const openSubsidiary = (subsidiary: Subsidiary) => {
    setSelectedSubsidiary(subsidiary)
    setSubsidiaryMenuOpen(false)
    setSubsidiaryTenders([])
    void loadSubsidiaryTenders(subsidiary.id)
  }

  const handleSync = async () => {
    setSyncStatus('running')
    try {
      const res = await syncData()
      setSyncResult(res.data)
      setSyncStatus(
        res.data.status === 'completed' && res.data.errors.length === 0 ? 'success' : 'error',
      )
      // Refresh signals after sync
      const tendersRes = await listTenders()
      const data = tendersRes.data ?? []
      setSignals(
        data.map((item: TenderEvent) => ({
          id: item.id,
          title: item.project_name || 'Untitled',
          reference: item.tender_id,
          stage: item.stage,
          probability: item.existing_win_probability_percent,
          updated: item.source_updated_at || item.ingested_at || '',
          material: (item.material_categories ?? []).join(' Â· ') || 'No materials listed',
          recipient: 'Pending',
          sourceType: item.source_type,
          provenance: item.data_provenance,
        }))
      )
      if (selectedSubsidiary) {
        await loadSubsidiaryTenders(selectedSubsidiary.id)
      }
    } catch (err: any) {
      setSyncStatus('error')
      setSyncResult({ status: 'error', steps: 0, connectors_run: 0, connector_ids: [], total_fetched: 0, total_normalized: 0, total_created: 0, errors: [err.response?.data?.detail || 'Sync failed'], connector_results: {} })
    }
  }

  const saveSubsidiaryDetails = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!selectedSubsidiary) return
    setDetailsSaving(true)
    setSubsidiaryError('')
    try {
      const materials = detailsForm.materials.split(',').map((item) => item.trim()).filter(Boolean)
      await addSubsidiaryTender(selectedSubsidiary.id, {
        tender_id: detailsForm.tender_id.trim(),
        project_name: detailsForm.project_name.trim(),
        stage: detailsForm.stage,
        material_categories: materials.length ? materials : ['General'],
        tender_value: detailsForm.tender_value === '' ? null : Number(detailsForm.tender_value),
        currency: 'INR',
        opening_at: detailsForm.opening_date ? new Date(`${detailsForm.opening_date}T00:00:00`).toISOString() : null,
        closing_at: detailsForm.closing_date ? new Date(`${detailsForm.closing_date}T00:00:00`).toISOString() : null,
      })
      setDetailsForm(EMPTY_SUBSIDIARY_FORM)
      setShowAddDetails(false)
      await loadSubsidiaryTenders(selectedSubsidiary.id)
    } catch (err) {
      setSubsidiaryError(getApiErrorMessage(err, 'Unable to save tender details.'))
    } finally {
      setDetailsSaving(false)
    }
  }

  const stageCounts = useMemo(() => {
    const counts = new Map<string, { label: string; count: number }>()
    for (const signal of signals) {
      const key = stageKey(signal.stage)
      const current = counts.get(key)
      counts.set(key, {
        label: simplifyStage(signal.stage),
        count: (current?.count || 0) + 1,
      })
    }
    return [...counts.entries()]
      .map(([key, value]) => ({ key, ...value }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
  }, [signals])
  const visibleSignals = useMemo(
    () => signals.filter((signal) => filter === 'All stages' || stageKey(signal.stage) === filter),
    [signals, filter],
  )
  const showStageTenders = (stage: string | null) => {
    setFilter(stage === null ? 'All stages' : stageKey(stage))
    pipelineSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  const selectedStageLabel = stageCounts.find(({ key }) => key === filter)?.label

  return (
    <div className="mx-auto max-w-[1440px] space-y-6 pb-10">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">
            <Signal size={14} />
            Agentic signal workspace
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-gray-950 dark:text-gray-50 sm:text-3xl">Pipeline overview</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-500">
            Automated tender signal ingestion from CRM connectors and public portals.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <button
              type="button"
              onClick={() => setSubsidiaryMenuOpen((open) => !open)}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 shadow-sm transition hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              aria-expanded={subsidiaryMenuOpen}
            >
              <Building2 size={15} />
              Subsidiaries
              <span aria-hidden="true">▾</span>
            </button>
            {subsidiaryMenuOpen && (
              <div className="absolute right-0 z-30 mt-2 w-48 rounded-xl border border-gray-200 bg-white p-1 shadow-lg dark:border-gray-700 dark:bg-gray-800">
                {subsidiaries.map((subsidiary) => (
                  <button
                    key={subsidiary.id}
                    type="button"
                    onClick={() => openSubsidiary(subsidiary)}
                    className="block w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-gray-700 hover:bg-indigo-50 dark:text-gray-100 dark:hover:bg-gray-700"
                  >
                    {subsidiary.name}
                  </button>
                ))}
                {subsidiaryError && <p role="alert" className="p-2 text-xs text-rose-700">{subsidiaryError}</p>}
                {!subsidiaries.length && !subsidiaryError && <p className="p-2 text-xs text-gray-500">Loading subsidiaries…</p>}
              </div>
            )}
          </div>
          <button
            onClick={handleSync}
            disabled={syncStatus === 'running'}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50"
          >
            {syncStatus === 'running' ? (
              <span className="flex items-center gap-1">
                <RefreshCw className="animate-spin" size={14} />
                Syncingâ€¦
              </span>
            ) : (
              <span>
                <RefreshCw size={14} />
                Sync Signals
              </span>
            )}
          </button>
        </div>
      </section>

      {selectedSubsidiary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="subsidiary-dialog-title"
            className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl dark:bg-gray-800 sm:p-6"
          >
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 pb-4 dark:border-gray-700">
              <div>
                <h3 id="subsidiary-dialog-title" className="text-xl font-bold text-gray-950 dark:text-gray-50">{selectedSubsidiary.name} tenders</h3>
                <p className="mt-1 text-xs text-gray-500">Synthetic iTrack-style demo feed; not live CRM data.</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => { setDetailsForm(EMPTY_SUBSIDIARY_FORM); setShowAddDetails(true) }}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
                >
                  <Plus size={15} /> Add details
                </button>
                <button
                  type="button"
                  aria-label="Close subsidiary tenders"
                  onClick={() => setSelectedSubsidiary(null)}
                  className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {subsidiaryError && <p role="alert" className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{subsidiaryError}</p>}
            {subsidiaryLoading ? (
              <p className="py-12 text-center text-sm text-gray-500">Loading tender records…</p>
            ) : subsidiaryTenders.length ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[700px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="border-b p-3">Tender</th>
                      <th className="border-b p-3">Status</th>
                      <th className="border-b p-3">Opening date</th>
                      <th className="border-b p-3">Closing date</th>
                      <th className="border-b p-3 text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {subsidiaryTenders.map((tender) => (
                      <tr key={tender.event_id} className="border-b border-gray-100 last:border-0 dark:border-gray-700">
                        <td className="p-3">
                          <p className="font-semibold text-gray-900 dark:text-gray-100">{tender.project_name}</p>
                          <p className="mt-1 font-mono text-xs text-gray-500">{tender.tender_id}</p>
                        </td>
                        <td className="p-3">
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                            tender.stage === 'Won' ? 'bg-emerald-100 text-emerald-800' :
                              tender.stage === 'Lost' ? 'bg-rose-100 text-rose-800' :
                                'bg-amber-100 text-amber-800'
                          }`}>{simplifyStage(tender.stage)}</span>
                        </td>
                        <td className="p-3 text-gray-600 dark:text-gray-300">{displayDate(tender.opening_at)}</td>
                        <td className="p-3 text-gray-600 dark:text-gray-300">{displayDate(tender.closing_at)}</td>
                        <td className="p-3 text-right text-gray-700 dark:text-gray-200">
                          {tender.tender_value == null ? '—' : `${tender.currency || 'INR'} ${tender.tender_value.toLocaleString('en-IN')}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : !subsidiaryError && (
              <p className="py-12 text-center text-sm text-gray-500">No tender records found. Use Sync Signals to fetch connector data.</p>
            )}
          </section>

          {showAddDetails && (
            <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
              <form onSubmit={saveSubsidiaryDetails} className="max-h-[90vh] w-full max-w-xl space-y-4 overflow-y-auto rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-800">
                <h3 className="text-lg font-bold text-gray-950 dark:text-gray-50">Add {selectedSubsidiary.name} tender details</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-sm">Tender reference
                    <input required maxLength={64} className="mt-1 w-full rounded-lg border p-2 dark:bg-gray-900" value={detailsForm.tender_id} onChange={(event) => setDetailsForm({ ...detailsForm, tender_id: event.target.value })} />
                  </label>
                  <label className="text-sm">Tender / project name
                    <input required maxLength={128} className="mt-1 w-full rounded-lg border p-2 dark:bg-gray-900" value={detailsForm.project_name} onChange={(event) => setDetailsForm({ ...detailsForm, project_name: event.target.value })} />
                  </label>
                  <label className="text-sm">Status
                    <select className="mt-1 w-full rounded-lg border p-2 dark:bg-gray-900" value={detailsForm.stage} onChange={(event) => setDetailsForm({ ...detailsForm, stage: event.target.value as SubsidiaryStage })}>
                      {(['Won', 'Lost', 'In Progress'] as SubsidiaryStage[]).map((stage) => <option key={stage}>{stage}</option>)}
                    </select>
                  </label>
                  <label className="text-sm">Materials (comma separated)
                    <input className="mt-1 w-full rounded-lg border p-2 dark:bg-gray-900" value={detailsForm.materials} onChange={(event) => setDetailsForm({ ...detailsForm, materials: event.target.value })} />
                  </label>
                  <label className="text-sm">Tender value (INR)
                    <input type="number" min="0" className="mt-1 w-full rounded-lg border p-2 dark:bg-gray-900" value={detailsForm.tender_value} onChange={(event) => setDetailsForm({ ...detailsForm, tender_value: event.target.value })} />
                  </label>
                  <label className="text-sm">Opening date
                    <input type="date" className="mt-1 w-full rounded-lg border p-2 dark:bg-gray-900" value={detailsForm.opening_date} onChange={(event) => setDetailsForm({ ...detailsForm, opening_date: event.target.value })} />
                  </label>
                  <label className="text-sm">Closing date
                    <input type="date" className="mt-1 w-full rounded-lg border p-2 dark:bg-gray-900" value={detailsForm.closing_date} onChange={(event) => setDetailsForm({ ...detailsForm, closing_date: event.target.value })} />
                  </label>
                </div>
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setShowAddDetails(false)} className="rounded-lg border px-4 py-2 text-sm">Cancel</button>
                  <button disabled={detailsSaving} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{detailsSaving ? 'Saving…' : 'Save details'}</button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}

      {syncStatus === 'success' && syncResult && (
        <section className="flex items-start gap-3 rounded-2xl border border-emerald-200 dark:border-emerald-900/30 bg-emerald-50 dark:bg-emerald-900/20 px-4 py-3.5">
          <div className="mt-0.5 rounded-lg bg-emerald-100 p-2 text-emerald-700"><CheckCircle2 size={17} /></div>
          <div>
            <p className="text-sm font-semibold text-emerald-950 dark:text-emerald-100">Sync complete</p>
            <p className="mt-0.5 text-xs leading-5 text-emerald-800 dark:text-emerald-200">
              {syncResult.total_created} new tender events from {syncResult.connectors_run} connector(s);
              {' '}{syncResult.routing?.deliveries_sent ?? 0} notifications sent
            </p>
          </div>
        </section>
      )}

      {syncStatus === 'error' && syncResult && (
        <section className="flex items-start gap-3 rounded-2xl border border-rose-200 dark:border-rose-900/30 bg-rose-50 dark:bg-rose-900/20 px-4 py-3.5">
          <div className="mt-0.5 rounded-lg bg-rose-100 p-2 text-rose-700"><BellRing size={17} /></div>
          <div>
            <p className="text-sm font-semibold text-rose-950 dark:text-rose-100">Sync encountered errors</p>
            <p className="mt-0.5 text-xs leading-5 text-rose-800">
              {syncResult.errors.join('; ')}
            </p>
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3 rounded-2xl border border-amber-200 dark:border-amber-900/30 bg-amber-50 dark:bg-amber-900/20 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-amber-100 p-2 text-amber-700"><CircleHelp size={17} /></div>
          <div>
            <p className="text-sm font-semibold text-amber-950 dark:text-amber-100">Live data from connectors</p>
            <p className="mt-0.5 text-xs leading-5 text-amber-800">
              Signals shown below are fetched from enabled CRM/public-portal connectors. Use the Sync Signals button to refresh.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 text-xs font-medium">
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 dark:border-amber-900/30 bg-white/70 dark:bg-gray-800/70 px-2.5 py-1.5 text-amber-900">
            <Monitor size={13} /> Source: {apiReachable ? 'connected' : 'not connected'}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 dark:border-amber-900/30 bg-white/70 dark:bg-gray-800/70 px-2.5 py-1.5 text-amber-900">
            <BellRing size={13} /> Email alerts: matching rules only
          </span>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <button
          type="button"
          aria-pressed={filter === 'All stages'}
          onClick={() => showStageTenders(null)}
          className={`rounded-2xl border bg-white p-5 text-left shadow-sm transition hover:border-indigo-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:bg-gray-800 ${
            filter === 'All stages' ? 'border-indigo-400 ring-1 ring-indigo-200 dark:border-indigo-500' : 'border-gray-200 dark:border-gray-700'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-500">Total tenders</span>
            <div className="rounded-xl bg-indigo-50 p-2.5 text-indigo-600"><Database size={18} /></div>
          </div>
          <div className="mt-4 flex items-end justify-between">
            <span className="text-3xl font-bold tracking-tight text-gray-950 dark:text-gray-50">{signals.length}</span>
            <span className="text-xs text-gray-400">from all sources</span>
          </div>
        </button>
        {stageCounts.map(({ key, label, count }) => (
          <button
          key={key}
            type="button"
            aria-pressed={filter === key}
            onClick={() => showStageTenders(key)}
            className={`rounded-2xl border bg-white p-5 text-left shadow-sm transition hover:border-indigo-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:bg-gray-800 ${
              filter === key ? 'border-indigo-400 ring-1 ring-indigo-200 dark:border-indigo-500' : 'border-gray-200 dark:border-gray-700'
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="truncate text-sm font-medium text-gray-500" title={label}>{label}</span>
              <div className="rounded-xl bg-indigo-50 p-2.5 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-300"><Activity size={18} /></div>
            </div>
            <div className="mt-4 flex items-end justify-between">
              <span className="text-3xl font-bold tracking-tight text-gray-950 dark:text-gray-50">{count}</span>
              <span className="text-xs text-gray-400">tenders</span>
            </div>
          </button>
        ))}
      </section>

      <section ref={pipelineSectionRef} className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.8fr)_minmax(300px,0.9fr)]">
        <div className="overflow-hidden rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm">
          <div className="flex flex-col gap-4 border-b border-gray-100 dark:border-gray-700 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="font-bold text-gray-900 dark:text-gray-100">
                {filter === 'All stages' ? 'Pipeline signals' : `${selectedStageLabel || filter} tenders`}
              </h3>
              <p className="mt-1 text-xs text-gray-500">
                Showing {visibleSignals.length} of {signals.length} tenders
              </p>
            </div>
            <div className="flex flex-wrap gap-1 rounded-xl bg-gray-100 dark:bg-gray-800 p-1" aria-label="Filter signals">
              {['All stages', ...stageCounts.map(({ key }) => key)].map((item) => {
                const label = item === 'All stages'
                  ? item
                  : stageCounts.find(({ key }) => key === item)?.label || item
                return (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={filter === item}
                    onClick={() => setFilter(item)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${filter === item ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 hover:text-gray-800 dark:text-gray-200'}`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="divide-y divide-gray-100">
            {visibleSignals.map((signal) => (
              <article key={signal.id} className="p-5 transition hover:bg-gray-50/70 dark:hover:bg-gray-700/50">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100">{signal.title}</h4>
                      <StatusPill stage={simplifyStage(signal.stage)} />
                    </div>
                    <p className="mt-1.5 font-mono text-[11px] text-gray-400">{signal.reference}</p>
                    <p className="mt-3 text-xs text-gray-500">{signal.material}</p>
                    {signal.provenance && (
                      <p className="mt-2 text-[10px] text-gray-400 italic">{signal.provenance}</p>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4 lg:min-w-[430px]">
                    <div>
                      <p className="text-[11px] text-gray-400">Current stage</p>
                      <p className="mt-1 font-medium text-gray-700 dark:text-gray-300">{simplifyStage(signal.stage)}</p>
                    </div>
                    <div>
                      <p className="text-[11px] text-gray-400">Win probability</p>
                      <p className="mt-1 font-semibold text-gray-800 dark:text-gray-200">
                        {signal.probability == null ? 'Not enough data' : `${signal.probability}%`}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] text-gray-400">Source</p>
                      <p className="mt-1 font-medium text-gray-700 dark:text-gray-300 capitalize">{signal.sourceType}</p>
                    </div>
                    <div>
                      <p className="text-[11px] text-gray-400">Source update</p>
                      <p className="mt-1 inline-flex items-center gap-1 font-medium text-gray-700 dark:text-gray-300"><Clock3 size={12} /> {signal.updated}</p>
                    </div>
                  </div>
                </div>
              </article>
            ))}
            {visibleSignals.length === 0 && (
              <div className="p-10 text-center text-sm text-gray-500">
                No signals yet. Click "Sync Signals" to fetch data from connected sources.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-gray-900 dark:text-gray-100">Signal flow</h3>
                <p className="mt-1 text-xs text-gray-500">Automated ingestion â†’ evaluation â†’ routing</p>
              </div>
              <div className="rounded-xl bg-indigo-50 p-2.5 text-indigo-600"><Workflow size={18} /></div>
            </div>
            <ol className="mt-5 space-y-0">
              <li className="flex gap-3 pb-5">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700"><Check size={14} /></span>
                <div>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Connector fetch</p>
                  <p className="mt-0.5 text-xs text-gray-500">CRM and public-portal connectors pull tender data</p>
                </div>
              </li>
              <li className="flex gap-3 pb-5">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700"><Check size={14} /></span>
                <div>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Normalize + deduplicate</p>
                  <p className="mt-0.5 text-xs text-gray-500">Records mapped to shared schema, duplicates removed</p>
                </div>
              </li>
              <li className="flex gap-3 pb-5">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700"><Clock3 size={14} /></span>
                <div>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Policy evaluation</p>
                  <p className="mt-0.5 text-xs text-gray-500">Rules and subsidiary routes applied</p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500"><LockKeyhole size={14} /></span>
                <div>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Delivery held</p>
                  <p className="mt-0.5 text-xs text-gray-500">Notification adapter not yet implemented</p>
                </div>
              </li>
            </ol>
          </div>

          <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className={`rounded-xl p-2.5 ${apiReachable ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600' : apiReachable === false ? 'bg-rose-50 dark:bg-rose-900/20 text-rose-600' : 'bg-gray-100 dark:bg-gray-800 text-gray-500'}`}>
                {apiReachable ? <CheckCircle2 size={18} /> : <Radio size={18} />}
              </div>
              <div>
                <h3 className="font-bold text-gray-900 dark:text-gray-100">Application API</h3>
                <p className="mt-0.5 text-xs text-gray-500">
                  {apiReachable === null ? 'Checking connectionâ€¦' : apiReachable ? 'Reachable' : 'Not reachable'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
