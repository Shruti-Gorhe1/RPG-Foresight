import { FormEvent, useEffect, useState } from 'react'
import {
  createTender, exportTenderReport, feedbackSuggestions, getApiErrorMessage,
  getTenderFeedback, importTenders, listFollowUps, listManagedTenders,
  previewTenderImport, reportSummary, saveFollowUp, saveTenderFeedback,
  updateTender, type TenderEvent, type TenderFollowUp, type TenderInput,
} from '../services/api'

const FIELDS = [
  { key: 'tender_id', label: 'Tender ID', required: true },
  { key: 'project_name', label: 'Project name', required: true },
  { key: 'stage', label: 'Stage', required: true },
  { key: 'material_categories', label: 'Materials', required: true },
  { key: 'event_id', label: 'Event ID', required: false },
  { key: 'region', label: 'Region', required: false },
  { key: 'tender_value', label: 'Tender value', required: false },
  { key: 'currency', label: 'Currency', required: false },
  { key: 'opening_at', label: 'Opening date', required: false },
  { key: 'closing_at', label: 'Closing date', required: false },
] as const

const blankForm = {
  tender_id: '', project_name: '', stage: '', materials: '',
  region: '', tender_value: '', currency: '', opening_at: '', closing_at: '',
}

function localDateTime(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export default function TenderOperationsPage() {
  const [tenders, setTenders] = useState<TenderEvent[]>([])
  const [followUps, setFollowUps] = useState<TenderFollowUp[]>([])
  const [summary, setSummary] = useState<Record<string, unknown>>({})
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [regionFilter, setRegionFilter] = useState('')
  const [materialFilter, setMaterialFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [currencyFilter, setCurrencyFilter] = useState('')
  const [probabilityFilter, setProbabilityFilter] = useState('')
  const [closingBeforeFilter, setClosingBeforeFilter] = useState('')
  const [minimumValueFilter, setMinimumValueFilter] = useState('')
  const [maximumValueFilter, setMaximumValueFilter] = useState('')
  const [form, setForm] = useState(blankForm)
  const [editingEventId, setEditingEventId] = useState<string | null>(null)
  const [showTenderForm, setShowTenderForm] = useState(false)
  const [selectedFeedback, setSelectedFeedback] = useState<TenderEvent | null>(null)
  const [feedbackChoice, setFeedbackChoice] = useState('Relevant')
  const [feedbackReason, setFeedbackReason] = useState('')
  const [selectedFollowUp, setSelectedFollowUp] = useState<TenderEvent | null>(null)
  const [followUpForm, setFollowUpForm] = useState({ assigned_to: '', status: 'New', notes: '', follow_up_at: '' })
  const [followUpSaving, setFollowUpSaving] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [importHeaders, setImportHeaders] = useState<string[]>([])
  const [importPreview, setImportPreview] = useState<Record<string, unknown>[]>([])
  const [fieldMapping, setFieldMapping] = useState<Record<string, string>>({})
  const [importRejections, setImportRejections] = useState<{ row: number; reason: string }[]>([])
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      setLoading(true)
      const params: Record<string, string> = {}
      if (search.trim()) params.search = search.trim()
      if (stageFilter) params.stage = stageFilter
      if (regionFilter.trim()) params.region = regionFilter.trim()
      if (materialFilter.trim()) params.material = materialFilter.trim()
      if (sourceFilter) params.source_type = sourceFilter
      if (currencyFilter.trim()) params.currency = currencyFilter.trim()
      if (probabilityFilter !== '') params.probability_min = probabilityFilter
      if (closingBeforeFilter) params.closing_before = `${closingBeforeFilter}T23:59:59Z`
      if (minimumValueFilter !== '') params.minimum_value = minimumValueFilter
      if (maximumValueFilter !== '') params.maximum_value = maximumValueFilter
      const [tenderResult, followUpResult, summaryResult, suggestionResult] = await Promise.all([
        listManagedTenders(params), listFollowUps(), reportSummary(params), feedbackSuggestions(),
      ])
      setTenders(tenderResult.data)
      setFollowUps(followUpResult.data)
      setSummary(summaryResult.data)
      setSuggestions(suggestionResult.data.recommendations)
      setError('')
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to load tender operations.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [search, stageFilter, regionFilter, materialFilter, sourceFilter, currencyFilter, probabilityFilter, closingBeforeFilter, minimumValueFilter, maximumValueFilter])

  const toPayload = (): TenderInput => ({
    tender_id: form.tender_id.trim(),
    project_name: form.project_name.trim(),
    stage: form.stage.trim(),
    material_categories: form.materials.split(',').map((item) => item.trim()).filter(Boolean),
    region: form.region.trim() || null,
    tender_value: form.tender_value === '' ? null : Number(form.tender_value),
    currency: form.currency.trim().toUpperCase() || null,
    opening_at: form.opening_at ? new Date(form.opening_at).toISOString() : null,
    closing_at: form.closing_at ? new Date(form.closing_at).toISOString() : null,
  })

  const saveTender = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const payload = toPayload()
      if (!payload.material_categories.length) throw new Error('Enter at least one material category.')
      if (editingEventId) await updateTender(editingEventId, payload)
      else await createTender(payload)
      setShowTenderForm(false)
      setEditingEventId(null)
      setForm(blankForm)
      setNotice(editingEventId ? 'Tender updated.' : 'Tender added.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to save the tender.'))
    } finally {
      setBusy(false)
    }
  }

  const editTender = (tender: TenderEvent) => {
    setEditingEventId(tender.event_id)
    setForm({
      tender_id: tender.tender_id, project_name: tender.project_name, stage: tender.stage,
      materials: (tender.material_categories || []).join(', '),
      region: tender.region || '', tender_value: tender.tender_value == null ? '' : String(tender.tender_value),
      currency: tender.currency || '', opening_at: localDateTime(tender.opening_at),
      closing_at: localDateTime(tender.closing_at),
    })
    setShowTenderForm(true)
  }

  const openFeedback = async (tender: TenderEvent) => {
    setSelectedFeedback(tender)
    setFeedbackChoice('Relevant')
    setFeedbackReason('')
    try {
      const result = await getTenderFeedback(tender.event_id)
      setFeedbackChoice(result.data.feedback || 'Relevant')
      setFeedbackReason(result.data.reason || '')
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to load signal feedback.'))
    }
  }

  const submitFeedback = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedFeedback) return
    try {
      await saveTenderFeedback(selectedFeedback.event_id, feedbackChoice, feedbackReason)
      setSelectedFeedback(null)
      setNotice('Signal feedback saved. Suggestions are informational and do not alter rules.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to save signal feedback.'))
    }
  }

  const openFollowUp = async (tender: TenderEvent) => {
    setSelectedFollowUp(tender)
    setError('')
    setFollowUpSaving(false)
    const existing = followUps.find((item) => item.event_id === tender.event_id)
    setFollowUpForm({
      assigned_to: existing?.assigned_to || '', status: existing?.status || 'New',
      notes: existing?.notes || '', follow_up_at: localDateTime(existing?.follow_up_at),
    })
  }

  const submitFollowUp = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedFollowUp || followUpSaving) return
    setFollowUpSaving(true)
    setError('')
    setNotice('')
    try {
      await saveFollowUp(selectedFollowUp.event_id, {
        assigned_to: followUpForm.assigned_to.trim() || null,
        status: followUpForm.status,
        notes: followUpForm.notes,
        follow_up_at: followUpForm.follow_up_at ? new Date(followUpForm.follow_up_at).toISOString() : null,
      })
      setSelectedFollowUp(null)
      setNotice('Follow-up saved.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to save follow-up.'))
    } finally {
      setFollowUpSaving(false)
    }
  }

  const previewUpload = async () => {
    if (!uploadFile) return
    setBusy(true)
    setError('')
    try {
      const result = await previewTenderImport(uploadFile)
      setImportHeaders(result.data.headers)
      setImportPreview(result.data.preview)
      const normalizedHeaders = result.data.headers.map((header) => header.toLowerCase().replace(/[^a-z0-9]/g, ''))
      const guesses: Record<string, string> = {}
      FIELDS.forEach((field) => {
        const exact = normalizedHeaders.indexOf(field.key.replace(/[^a-z0-9]/g, '').toLowerCase())
        const aliases: Record<string, string[]> = {
          tender_id: ['tenderid', 'tenderref', 'reference', 'id'],
          project_name: ['project', 'projecttitle', 'name'],
          stage: ['status', 'tenderstage'],
          material_categories: ['materials', 'material', 'categories'],
          existing_win_probability_percent: ['probability', 'winprobability'],
          closing_at: ['closingdate', 'deadline', 'duedate'],
          opening_at: ['openingdate', 'tenderopeningdate'],
        }
        const aliasIndex = (aliases[field.key] || []).map((alias) => normalizedHeaders.indexOf(alias)).find((index) => index >= 0)
        const index = exact >= 0 ? exact : aliasIndex
        if (index !== undefined && index >= 0) guesses[field.key] = result.data.headers[index]
      })
      setFieldMapping(guesses)
      setNotice(`Preview ready. ${result.data.row_count} rows found.`)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to preview this file.'))
    } finally {
      setBusy(false)
    }
  }

  const submitImport = async () => {
    if (!uploadFile) return
    setBusy(true)
    setError('')
    try {
      const result = await importTenders(uploadFile, Object.fromEntries(
        Object.entries(fieldMapping).filter(([, column]) => column),
      ))
      setImportRejections(result.data.rejected_rows)
      setNotice(`Imported ${result.data.imported} tender(s); ${result.data.rejected_count} row(s) rejected.`)
      setImportPreview([])
      setImportHeaders([])
      setUploadFile(null)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to import tenders.'))
    } finally {
      setBusy(false)
    }
  }

  const downloadReport = async () => {
    try {
      const response = await exportTenderReport({
        ...(search.trim() ? { search: search.trim() } : {}),
        ...(stageFilter ? { stage: stageFilter } : {}),
        ...(regionFilter.trim() ? { region: regionFilter.trim() } : {}),
        ...(materialFilter.trim() ? { material: materialFilter.trim() } : {}),
        ...(sourceFilter ? { source_type: sourceFilter } : {}),
        ...(currencyFilter.trim() ? { currency: currencyFilter.trim() } : {}),
        ...(probabilityFilter !== '' ? { probability_min: Number(probabilityFilter) } : {}),
        ...(closingBeforeFilter ? { closing_before: `${closingBeforeFilter}T23:59:59Z` } : {}),
        ...(minimumValueFilter !== '' ? { minimum_value: Number(minimumValueFilter) } : {}),
        ...(maximumValueFilter !== '' ? { maximum_value: Number(maximumValueFilter) } : {}),
      })
      const href = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = href
      link.download = 'tender-report.csv'
      link.click()
      URL.revokeObjectURL(href)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to export the report.'))
    }
  }

  const stages = summary.by_stage as Record<string, number> | undefined
  const dueCount = followUps.filter((item) => item.is_due).length
  const renderBreakdown = (title: string, key: string) => {
    const values = summary[key] as Record<string, number> | undefined
    return <div key={key} className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-2 space-y-1 text-sm text-gray-600 dark:text-gray-300">
        {Object.entries(values || {}).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, count]) => <li key={label} className="flex justify-between gap-4"><span className="truncate">{label}</span><span className="font-semibold">{count}</span></li>)}
        {!Object.keys(values || {}).length && <li className="text-gray-400">No data yet</li>}
      </ul>
    </div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-gray-950 dark:text-gray-50">Tender Operations</h2>
          <p className="mt-1 text-sm text-gray-500">Import and maintain tenders, provide signal feedback, and coordinate follow-up.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setEditingEventId(null); setForm(blankForm); setShowTenderForm(true) }} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">Add tender</button>
          <button onClick={() => void downloadReport()} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200">Export CSV</button>
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ['Tenders', Number(summary.total_tenders || 0)],
          ['Closing within 30 days', Number(summary.closing_within_30_days || 0)],
          ['Due follow-ups', dueCount],
          ['Stages represented', Object.keys(stages || {}).length],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</p>
            <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
          </div>
        ))}
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100">Upload tenders</h3>
        <p className="mt-1 text-sm text-gray-500">CSV or Excel (.xlsx); up to 10 MB and 2,000 rows. Preview and map columns before importing.</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(event) => { setUploadFile(event.target.files?.[0] || null); setImportHeaders([]); setImportPreview([]); setImportRejections([]) }} />
          <button disabled={!uploadFile || busy} onClick={() => void previewUpload()} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50">{busy ? 'Working…' : 'Preview file'}</button>
        </div>
        {importHeaders.length > 0 && (
          <div className="mt-4 space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {FIELDS.map((field) => (
                <label key={field.key} className="text-xs font-semibold text-gray-600 dark:text-gray-300">
                  {field.label}{field.required ? ' *' : ''}
                  <select className="mt-1 block w-full rounded border border-gray-300 bg-white p-2 text-sm dark:bg-gray-900" value={fieldMapping[field.key] || ''} onChange={(event) => setFieldMapping({ ...fieldMapping, [field.key]: event.target.value })}>
                    <option value="">Not mapped</option>
                    {importHeaders.map((header) => <option key={header} value={header}>{header}</option>)}
                  </select>
                </label>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs"><thead><tr>{importHeaders.map((header) => <th key={header} className="border-b p-2">{header}</th>)}</tr></thead>
                <tbody>{importPreview.map((row, index) => <tr key={index}>{importHeaders.map((header) => <td key={header} className="border-b p-2">{String(row[header] ?? '')}</td>)}</tr>)}</tbody>
              </table>
            </div>
            <button disabled={busy || FIELDS.filter((field) => field.required).some((field) => !fieldMapping[field.key])} onClick={() => void submitImport()} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Import rows</button>
          </div>
        )}
        {importRejections.length > 0 && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-semibold">Rejected rows</p>
          <ul className="mt-1 list-inside list-disc">{importRejections.map((item) => <li key={item.row}>Row {item.row}: {item.reason}</li>)}</ul>
        </div>}
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">Tender register</h3>
          <div className="flex flex-wrap gap-2">
            <input aria-label="Search tenders" placeholder="Search tender or project" className="rounded border px-3 py-2 text-sm" value={search} onChange={(event) => setSearch(event.target.value)} />
            <input aria-label="Filter by stage" placeholder="Stage" className="w-32 rounded border px-3 py-2 text-sm" value={stageFilter} onChange={(event) => setStageFilter(event.target.value)} />
            <input aria-label="Filter by region" placeholder="Region" className="w-32 rounded border px-3 py-2 text-sm" value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)} />
            <input aria-label="Filter by material" placeholder="Material" className="w-32 rounded border px-3 py-2 text-sm" value={materialFilter} onChange={(event) => setMaterialFilter(event.target.value)} />
            <select aria-label="Filter by source" className="rounded border px-3 py-2 text-sm" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="">Any source</option><option value="manual">Manual</option><option value="file_import">File import</option><option value="crm">CRM</option><option value="public_portal">Public portal</option></select>
            <input aria-label="Minimum estimated win probability" type="number" min={0} max={100} placeholder="Min estimate %" className="w-36 rounded border px-3 py-2 text-sm" value={probabilityFilter} onChange={(event) => setProbabilityFilter(event.target.value)} />
            <label className="flex items-center gap-1 text-xs text-gray-500">Closing by<input aria-label="Closing date before" type="date" className="rounded border px-2 py-2 text-sm" value={closingBeforeFilter} onChange={(event) => setClosingBeforeFilter(event.target.value)} /></label>
            <input aria-label="Tender currency" maxLength={8} placeholder="Currency" className="w-24 rounded border px-3 py-2 text-sm uppercase" value={currencyFilter} onChange={(event) => setCurrencyFilter(event.target.value.toUpperCase())} />
            <input aria-label="Minimum tender value" type="number" min={0} placeholder="Value from" className="w-32 rounded border px-3 py-2 text-sm" value={minimumValueFilter} onChange={(event) => setMinimumValueFilter(event.target.value)} />
            <input aria-label="Maximum tender value" type="number" min={0} placeholder="Value to" className="w-32 rounded border px-3 py-2 text-sm" value={maximumValueFilter} onChange={(event) => setMaximumValueFilter(event.target.value)} />
          </div>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead><tr className="border-b bg-gray-50 text-xs text-gray-500 dark:bg-gray-900">{['Tender / project', 'Stage', 'Materials', 'Region / value', 'Estimated win probability', 'Opening', 'Closing', 'Actions'].map((item) => <th key={item} className="p-2">{item}</th>)}</tr></thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {tenders.slice(0, 100).map((tender) => {
                const followUp = followUps.find((item) => item.event_id === tender.event_id)
                return <tr key={tender.event_id} className="align-top">
                  <td className="p-2"><div className="font-medium">{tender.project_name}</div><div className="text-xs text-gray-500">{tender.tender_id}</div></td>
                  <td className="p-2">{tender.stage}</td>
                  <td className="p-2">{tender.material_categories.join(', ')}</td>
                  <td className="p-2">{tender.region || '—'}<div className="text-xs text-gray-500">{tender.tender_value == null ? '—' : `${tender.currency || ''} ${tender.tender_value}`}</div></td>
                  <td className="p-2">{tender.existing_win_probability_percent == null
                    ? <span title="Requires at least 10 labeled tenders at this stage, including both wins and losses, within this tenant and demo/non-demo data class.">Unavailable</span>
                    : `${tender.existing_win_probability_percent}%`}</td>
                  <td className="p-2">{tender.opening_at ? new Date(tender.opening_at).toLocaleDateString() : '—'}</td>
                  <td className="p-2">{tender.closing_at ? new Date(tender.closing_at).toLocaleDateString() : '—'}</td>
                  <td className="p-2"><div className="flex flex-wrap gap-1">
                    <button onClick={() => editTender(tender)} className="rounded border px-2 py-1 text-xs">Edit</button>
                    <button onClick={() => void openFeedback(tender)} className="rounded border px-2 py-1 text-xs">Feedback</button>
                    <button onClick={() => void openFollowUp(tender)} className={`rounded border px-2 py-1 text-xs ${followUp?.is_due ? 'border-amber-500 text-amber-700' : ''}`}>{followUp?.is_due ? 'Follow-up due' : 'Follow-up'}</button>
                  </div></td>
                </tr>
              })}
              {!loading && tenders.length === 0 && <tr><td colSpan={8} className="p-6 text-center text-gray-500">No tenders match the current filters.</td></tr>}
              {loading && <tr><td colSpan={8} className="p-6 text-center text-gray-500">Loading tenders…</td></tr>}
            </tbody>
          </table>
        </div>
        {tenders.length > 100 && <p className="mt-2 text-xs text-gray-500">Showing 100 of {tenders.length} results. Narrow the filters to see other tenders.</p>}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <h3 className="font-semibold">Follow-up reminders</h3>
          <p className="mt-1 text-xs text-gray-500">Due and scheduled reminders appear here; a reminder is flagged overdue when its date has passed.</p>
          <div className="mt-3 space-y-2">
            {followUps.filter((item) => item.follow_up_at).slice(0, 10).map((item) => (
              <div key={item.event_id} className={`rounded-lg border p-3 text-sm ${item.is_due ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/20' : 'border-gray-100 dark:border-gray-700'}`}>
                <div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{item.project_name}</span><span className={item.is_due ? 'font-semibold text-amber-700' : 'text-gray-500'}>{item.is_due ? 'Overdue' : new Date(item.follow_up_at!).toLocaleString()}</span></div>
                <p className="mt-1 text-xs text-gray-500">{item.status} · {item.assigned_to || 'Unassigned'}{item.notes ? ` · ${item.notes}` : ''}</p>
              </div>
            ))}
            {!followUps.some((item) => item.follow_up_at) && <p className="text-sm text-gray-500">No follow-up reminders scheduled.</p>}
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <h3 className="font-semibold">Tender deadlines</h3>
          <p className="mt-1 text-xs text-gray-500">Upcoming deadlines from the currently filtered tender register.</p>
          <div className="mt-3 space-y-2">
            {tenders.filter((item) => item.closing_at).sort((a, b) => new Date(a.closing_at!).getTime() - new Date(b.closing_at!).getTime()).slice(0, 8).map((item) => {
              const overdue = new Date(item.closing_at!).getTime() < Date.now()
              return <div key={item.event_id} className="flex justify-between gap-3 rounded-lg border border-gray-100 p-3 text-sm dark:border-gray-700">
                <span className="min-w-0 truncate">{item.project_name} <span className="text-xs text-gray-500">({item.tender_id})</span></span>
                <span className={`shrink-0 text-xs ${overdue ? 'font-semibold text-rose-600' : 'text-gray-500'}`}>{overdue ? 'Closed · ' : ''}{new Date(item.closing_at!).toLocaleDateString()}</span>
              </div>
            })}
            {!tenders.some((item) => item.closing_at) && <p className="text-sm text-gray-500">No tender closing dates are available.</p>}
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        {renderBreakdown('By stage', 'by_stage')}
        {renderBreakdown('By material', 'by_material')}
        {renderBreakdown('By source', 'by_source')}
        {renderBreakdown('By win probability', 'by_probability')}
        {renderBreakdown('By closing deadline', 'by_deadline')}
        {renderBreakdown('By region', 'by_region')}
        {renderBreakdown('By recipient delivery count', 'by_recipient')}
      </section>
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <h3 className="font-semibold">Feedback-based recommendations</h3>
          <p className="mt-1 text-xs text-gray-500">Suggestions are review prompts only; your routing rules are never changed automatically.</p>
          {suggestions.length ? <ul className="mt-2 list-inside list-disc space-y-1 text-sm">{suggestions.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="mt-2 text-sm text-gray-500">Submit signal feedback to generate suggestions.</p>}
        </div>
      </section>

      {showTenderForm && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <form onSubmit={saveTender} className="max-h-[90vh] w-full max-w-xl space-y-3 overflow-y-auto rounded-xl bg-white p-6 dark:bg-gray-800">
          <h3 className="text-lg font-bold">{editingEventId ? 'Edit tender' : 'Add tender manually'}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {([
              ['tender_id', 'Tender ID'], ['project_name', 'Project name'], ['stage', 'Stage'],
              ['materials', 'Materials (comma separated)'],
              ['region', 'Region'], ['tender_value', 'Tender value'], ['currency', 'Currency'],
            ] as const).map(([key, label]) => <label key={key} className="text-sm">{label}
              <input required={['tender_id', 'project_name', 'stage', 'materials'].includes(key)} type={key === 'tender_value' ? 'number' : 'text'} min={key === 'tender_value' ? 0 : undefined} className="mt-1 w-full rounded border p-2 dark:bg-gray-900" value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
            </label>)}
            <label className="text-sm">Opening date
              <input type="datetime-local" className="mt-1 w-full rounded border p-2 dark:bg-gray-900" value={form.opening_at} onChange={(event) => setForm({ ...form, opening_at: event.target.value })} />
            </label>
            <label className="text-sm">Closing date
              <input type="datetime-local" className="mt-1 w-full rounded border p-2 dark:bg-gray-900" value={form.closing_at} onChange={(event) => setForm({ ...form, closing_at: event.target.value })} />
            </label>
          </div>
          <div className="flex gap-2"><button disabled={busy} className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-50">{busy ? 'Saving…' : 'Save tender'}</button><button type="button" onClick={() => setShowTenderForm(false)} className="rounded border px-4 py-2">Cancel</button></div>
        </form>
      </div>}

      {selectedFeedback && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <form onSubmit={submitFeedback} className="w-full max-w-md space-y-3 rounded-xl bg-white p-6 dark:bg-gray-800">
          <h3 className="font-bold">Signal feedback: {selectedFeedback.tender_id}</h3>
          <select className="w-full rounded border p-2 dark:bg-gray-900" value={feedbackChoice} onChange={(event) => setFeedbackChoice(event.target.value)}>{['Relevant', 'Not relevant', 'Already known'].map((value) => <option key={value}>{value}</option>)}</select>
          <textarea maxLength={1000} className="w-full rounded border p-2 dark:bg-gray-900" placeholder="Reason (optional)" value={feedbackReason} onChange={(event) => setFeedbackReason(event.target.value)} />
          <div className="flex gap-2"><button className="rounded bg-indigo-600 px-4 py-2 text-white">Save feedback</button><button type="button" onClick={() => setSelectedFeedback(null)} className="rounded border px-4 py-2">Cancel</button></div>
        </form>
      </div>}

      {selectedFollowUp && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <form onSubmit={submitFollowUp} className="w-full max-w-md space-y-3 rounded-xl bg-white p-6 dark:bg-gray-800">
          <h3 className="font-bold">Follow-up: {selectedFollowUp.tender_id}</h3>
          <input type="email" className="w-full rounded border p-2 dark:bg-gray-900" placeholder="Assignee email (optional)" value={followUpForm.assigned_to} onChange={(event) => setFollowUpForm({ ...followUpForm, assigned_to: event.target.value })} />
          <select className="w-full rounded border p-2 dark:bg-gray-900" value={followUpForm.status} onChange={(event) => setFollowUpForm({ ...followUpForm, status: event.target.value })}>{['New', 'Reviewing', 'Bid / No bid', 'Closed'].map((value) => <option key={value}>{value}</option>)}</select>
          <label className="block text-sm">Reminder date and time<input type="datetime-local" className="mt-1 w-full rounded border p-2 dark:bg-gray-900" value={followUpForm.follow_up_at} onChange={(event) => setFollowUpForm({ ...followUpForm, follow_up_at: event.target.value })} /></label>
          <textarea maxLength={10000} className="w-full rounded border p-2 dark:bg-gray-900" placeholder="Notes" value={followUpForm.notes} onChange={(event) => setFollowUpForm({ ...followUpForm, notes: event.target.value })} />
          {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          <div className="flex gap-2"><button type="submit" disabled={followUpSaving} className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-50">{followUpSaving ? 'Saving…' : 'Save follow-up'}</button><button type="button" disabled={followUpSaving} onClick={() => setSelectedFollowUp(null)} className="rounded border px-4 py-2 disabled:opacity-50">Cancel</button></div>
        </form>
      </div>}
    </div>
  )
}
