import { FormEvent, useEffect, useState } from 'react'
import {
  analyzePursuit, askTenderQuestion, getApiErrorMessage, listManagedTenders,
  type PursuitAssessment, type TenderEvent,
} from '../services/api'

type TenderEvidence = { document: string; location: string; excerpt: string }
type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
}
type TimelineEntry = {
  event: string
  event_type?: string
  value: string
  document: string
  location: string
  excerpt: string
}

type FinancialAmount = {
  value: string
  cost_type?: string
  document: string
  location: string
  excerpt: string
}

type ExtractedTenderValue = Omit<FinancialAmount, 'cost_type'>

type EconomicsSummary = {
  summary: string
  references?: { document: string; location: string }[]
}

const importantFinancialCostTypes = new Set([
  'estimated cost',
  'earnest money deposit (emd)',
  'tender value',
  'tender fee',
  'processing fee',
  'bid security',
  'performance security',
  'security deposit',
])

const importantEconomicsSummary = /\b(?:estimated\s+(?:(?:tender|project)\s+)?(?:cost|value|amount)|(?:tender|contract|project)\s+(?:value|cost|amount)|earnest money|(?:^|\W)emd(?:$|\W)|tender fee|processing fee|bid security|performance security|performance guarantee|security deposit|payment terms?|advance payment|milestone payment|gst|tax(?:es|ation)?|liquidated damages|penalt(?:y|ies)|price escalation|price adjustment|price variation)\b/i

function tenderValueHasDirectSourceSupport(item: ExtractedTenderValue) {
  const label = /\b(?:estimated\s+(?:(?:tender|project)\s+)?(?:cost|value|amount)|(?:tender|contract|project)\s+value|bid\s+value)\b/i.exec(item.excerpt)
  const amount = /[\d,]+(?:\.\d+)?/.exec(item.value)?.[0]
  if (!label || !amount) return false
  const amountIndex = item.excerpt.indexOf(amount, label.index + label[0].length)
  if (amountIndex < 0 || amountIndex - (label.index + label[0].length) > 48) return false
  const interveningText = item.excerpt.slice(label.index + label[0].length, amountIndex)
    .replace(/\b(?:is|of|in|INR|Rs\.?)\b/gi, '')
    .replace(/[₹():=,\s-]/g, '')
  return interveningText.length === 0
}

function getImportantFinancialAmounts(
  items: FinancialAmount[] = [],
  tenderValues: ExtractedTenderValue[] = [],
) {
  const importantItems = items.filter((item) =>
    item.cost_type && importantFinancialCostTypes.has(item.cost_type.trim().toLowerCase()),
  )
  const displayedValues = new Set(importantItems.map((item) => item.value.trim().toLowerCase()))
  const candidates: FinancialAmount[] = [
    ...importantItems,
    ...tenderValues
      .filter((item) =>
        !displayedValues.has(item.value.trim().toLowerCase()) &&
        tenderValueHasDirectSourceSupport(item),
      )
      .map((item) => ({ ...item, cost_type: 'Tender value' })),
  ]
  const unique = new Map<string, FinancialAmount>()
  candidates.forEach((item) => {
    const costType = item.cost_type?.trim().toLowerCase()
    if (!costType) return
    const key = `${costType}:${item.value.trim().toLowerCase()}`
    if (!unique.has(key)) unique.set(key, item)
  })
  return [...unique.values()]
}

function getImportantEconomicsSummaries(items: EconomicsSummary[] = []) {
  const unique = new Map<string, EconomicsSummary>()
  items.forEach((item) => {
    const summary = item.summary.trim()
    if (!importantEconomicsSummary.test(summary)) return
    const key = summary.toLowerCase()
    if (!unique.has(key)) unique.set(key, item)
  })
  return [...unique.values()]
}

function EvidencePoints({
  items,
  emptyMessage,
}: {
  items: TenderEvidence[]
  emptyMessage: string
}) {
  if (!items.length) return <p className="text-xs text-gray-500">{emptyMessage}</p>
  return <ul className="space-y-2">
    {items.map((item, index) => <li key={`${item.document}-${item.location}-${index}`} className="text-sm leading-5">
      <p>{item.excerpt}</p>
      <p className="mt-0.5 text-xs text-indigo-700 dark:text-indigo-300">{item.document} · {item.location}</p>
    </li>)}
  </ul>
}

function formatDocumentReferences(references: { document: string; location: string }[] = []) {
  const grouped = new Map<string, Set<string>>()
  references.forEach(({ document, location }) => {
    const locations = grouped.get(document) || new Set<string>()
    locations.add(location.replace(/^page\s+/i, 'p. '))
    grouped.set(document, locations)
  })
  return [...grouped.entries()]
    .map(([document, locations]) => `${document} — ${[...locations].join(', ')}`)
    .join('; ')
}

function importantTimelineType(event: string) {
  if (/\bpre[- ]?bid\b/i.test(event)) return 'pre_bid'
  if (/\b(?:technical|tech)\b.*\bbid\b.*\bopening\b|\bopening\b.*\b(?:technical|tech)\b.*\bbid\b/i.test(event)) return 'technical_bid_opening'
  if (/\b(?:financial|price)\b.*\bbid\b.*\bopening\b|\bopening\b.*\b(?:financial|price)\b.*\bbid\b/i.test(event)) return 'financial_bid_opening'
  if (/\b(?:download(?:ing)?|sale|availability)\b.*\b(?:tender|document|bid)\b|\b(?:tender|document|bid)\b.*\b(?:download(?:ing)?|sale|availability)\b/i.test(event)) return 'document_download'
  if (/\b(?:submission|submit|last date|deadline|closing)\b.*\b(?:tenders?|bids?|proposals?|offers?)\b|\b(?:tenders?|bids?|proposals?|offers?)\b.*\b(?:submission|submit|last date|deadline|closing)\b/i.test(event)) return 'bid_submission'
  if (/\b(?:invitation|inviting|publication of e?[- ]?nit|nit publication|issue of e?[- ]?nit)\b/i.test(event)) return 'invitation'
  return null
}

function normalizeTimelineDate(value: string) {
  const datePattern = /\b(?:(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})|(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4}))\b/i
  const match = value.match(datePattern)
  if (!match) return null
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  let year: number
  let month: number
  let day: number
  if (match[1]) {
    year = Number(match[1]); month = Number(match[2]); day = Number(match[3])
  } else if (match[4]) {
    day = Number(match[4]); month = Number(match[5]); year = Number(match[6])
    if (year < 100) year += year >= 70 ? 1900 : 2000
  } else {
    day = Number(match[7]); month = months.findIndex((name) => name.toLowerCase() === match[8].slice(0, 3).toLowerCase()) + 1; year = Number(match[9])
  }
  const date = new Date(Date.UTC(year, month - 1, day))
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null

  const timeMatch = value.slice(match.index! + match[0].length).match(/\b(\d{1,2}):(\d{2})(?::\d{2})?\s*(a\.?m\.?|p\.?m\.?)?/i)
  let timeDisplay = ''
  let timeSort = '00:00'
  if (timeMatch) {
    let hour = Number(timeMatch[1])
    const minute = Number(timeMatch[2])
    const period = timeMatch[3]?.replace(/\./g, '').toLowerCase()
    if (minute > 59 || hour > (period ? 12 : 23) || (period && hour < 1)) return null
    if (period) hour = (hour % 12) + (period === 'pm' ? 12 : 0)
    timeSort = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
    timeDisplay = period || hour >= 12 || hour === 0
      ? `${String((hour % 12) || 12).padStart(2, '0')}:${String(minute).padStart(2, '0')} ${hour >= 12 ? 'PM' : 'AM'}`
      : `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
  }
  const dateDisplay = `${String(day).padStart(2, '0')} ${months[month - 1]} ${year}`
  return {
    display: timeDisplay ? `${dateDisplay} · ${timeDisplay}` : dateDisplay,
    sortKey: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T${timeSort}`,
  }
}

function getImportantTimeline(entries: TimelineEntry[] = []) {
  const unique = new Map<string, TimelineEntry & { sortKey: string }>()
  entries.forEach((entry) => {
    const eventType = importantTimelineType(entry.event)
    const normalizedDate = normalizeTimelineDate(entry.value)
    if (!eventType || !normalizedDate) return
    const key = `${eventType}:${normalizedDate.sortKey}`
    if (!unique.has(key)) {
      unique.set(key, { ...entry, event_type: eventType, value: normalizedDate.display, sortKey: normalizedDate.sortKey })
    }
  })
  return [...unique.values()].sort((first, second) => first.sortKey.localeCompare(second.sortKey))
}

function getTimelinePhaseName(event: string, value: string, excerpt: string) {
  const cleanLabel = (text: string) => text
    .replace(/^\s*\d+(?:[.)]\s*|\s+)/, '')
    .replace(value, '')
    .replace(/\b\d{1,2}[./-]\d{2,4}(?:[./-]\d{2,4})?\b.*$/i, '')
    .replace(/\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?.*$/i, '')
    .replace(/\s+/g, ' ')
    .replace(/[\s,;:.-]+$/, '')
    .trim()

  return cleanLabel(event) || cleanLabel(excerpt) || 'Tender activity'
}

export default function PursuitCopilotPage() {
  const [tenders, setTenders] = useState<TenderEvent[]>([])
  const [selectedEventId, setSelectedEventId] = useState('')
  const [assessment, setAssessment] = useState<PursuitAssessment | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatQuestion, setChatQuestion] = useState('')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [chatWorking, setChatWorking] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadTenders = async () => {
    try {
      setLoading(true)
      const result = await listManagedTenders()
      setTenders(result.data)
      setSelectedEventId((current) => current || result.data[0]?.event_id || '')
      setError('')
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to load tenders.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadTenders() }, [])

  const runAnalysis = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedEventId || !files.length) return
    setWorking(true)
    setError('')
    setNotice('')
    setAssessment(null)
    setChatMessages([])
    try {
      const result = await analyzePursuit(selectedEventId, files)
      setAssessment(result.data)
      setFiles([])
      setNotice('Tender analysis is ready. Ask questions below for answers based on the uploaded document.')
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to analyze this tender.'))
    } finally {
      setWorking(false)
    }
  }

  const askQuestion = async (event: FormEvent) => {
    event.preventDefault()
    if (!assessment || !chatQuestion.trim() || chatWorking) return
    const question = chatQuestion.trim()
    const history = chatMessages.slice(-8).map(({ role, content }) => ({ role, content }))
    setChatMessages((current) => [...current, { role: 'user', content: question }])
    setChatQuestion('')
    setChatWorking(true)
    setError('')
    try {
      const result = await askTenderQuestion(assessment.assessment_id, question, history)
      setChatMessages((current) => [...current, {
        role: 'assistant',
        content: result.data.answer,
      }])
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to answer from the uploaded tender.'))
      setChatQuestion(question)
    } finally {
      setChatWorking(false)
    }
  }

  const tender = tenders.find((item) => item.event_id === selectedEventId)
  const report = assessment?.report
  const importantTimeline = getImportantTimeline(report?.documents.extracted_timeline)
  const importantFinancialAmounts = getImportantFinancialAmounts(
    report?.documents.extracted_financial_amounts,
    report?.documents.extracted_tender_values,
  )
  const importantEconomicsSummaries = getImportantEconomicsSummaries(report?.documents.economics_summaries)
  const fileInputId = 'pursuit-documents'

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold text-gray-950 dark:text-gray-50">Agentic Tender Pursuit Copilot</h2>
        <p className="mt-1 max-w-4xl text-sm text-gray-500">
          Upload a tender and ask questions about its requirements. Answers are based on the extracted tender text and do not display document references.
        </p>
      </header>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

      <section>
        <form onSubmit={runAnalysis} className="max-w-4xl space-y-4 rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
          <div>
            <label htmlFor="pursuit-tender" className="block text-sm font-semibold">Select a tender</label>
            <select id="pursuit-tender" required disabled={working || chatWorking} value={selectedEventId} onChange={(event) => {
              setSelectedEventId(event.target.value)
              setAssessment(null)
              setChatMessages([])
              setFiles([])
              setError('')
              setNotice('')
            }} className="mt-1 w-full rounded-lg border border-gray-300 bg-white p-2.5 text-sm dark:bg-gray-900">
              <option value="">Choose a tender…</option>
              {tenders.map((item) => <option key={item.event_id} value={item.event_id}>{item.tender_id} — {item.project_name}</option>)}
            </select>
            {tender && <p className="mt-2 text-xs text-gray-500">{tender.stage} · {tender.material_categories.join(', ') || 'No materials'} · {tender.region || 'No region'}</p>}
          </div>
          <div>
            <label htmlFor={fileInputId} className="block text-sm font-semibold">Tender documents</label>
            <p className="mt-1 text-xs text-gray-500">Upload PDF, DOCX, or UTF-8 TXT. Up to 10 files, 10 MB each / 20 MB total. Searchable text only; scanned PDFs need OCR.</p>
            <input id={fileInputId} type="file" required disabled={working || chatWorking} multiple accept=".pdf,.docx,.txt" onChange={(event) => setFiles(Array.from(event.target.files || []))} className="mt-2 block w-full text-sm" />
            {files.length > 0 && <ul className="mt-2 space-y-1 text-xs text-gray-600">{files.map((file) => <li key={`${file.name}-${file.size}`}>{file.name} · {(file.size / (1024 * 1024)).toFixed(2)} MB</li>)}</ul>}
          </div>
          <button disabled={loading || working || !selectedEventId || !files.length} className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
            {working ? 'Analyzing tender…' : 'Analyze tender'}
          </button>
          <p className="text-xs text-gray-500">Uploaded document text is retained with this review so questions can be answered later. Original files are not retained. Reviews can take several minutes with a local model; scanned PDFs require OCR before upload.</p>
        </form>

      </section>

      {assessment && report && <div className="space-y-5">
        <section className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
          <h3 className="font-semibold">Ask questions about this tender</h3>
          <p className="mt-1 text-sm text-gray-500">Ask about eligibility, pre-qualification, submissions, deadlines, costs, or any other clause. If the uploaded text does not support an answer, the assistant will say so.</p>
          <div aria-live="polite" className="mt-4 max-h-[32rem] space-y-4 overflow-y-auto">
            {chatMessages.map((message, index) => <article key={`${message.role}-${index}`} className={`rounded-lg p-3 ${message.role === 'user' ? 'ml-8 bg-indigo-50 dark:bg-indigo-950/40' : 'mr-8 bg-gray-50 dark:bg-gray-900/60'}`}>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{message.role === 'user' ? 'You' : 'Tender Copilot'}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6">{message.content}</p>
            </article>)}
            {chatWorking && <p role="status" className="text-sm text-gray-500">Searching the tender and preparing an answer…</p>}
            {!chatMessages.length && <p className="rounded-lg bg-gray-50 p-3 text-sm text-gray-500 dark:bg-gray-900/60">Example: “What are the pre-qualification criteria?”</p>}
          </div>
          <form onSubmit={askQuestion} className="mt-4 flex flex-col gap-2 sm:flex-row">
            <label className="sr-only" htmlFor="tender-question">Your question</label>
            <input id="tender-question" required maxLength={1000} value={chatQuestion} onChange={(event) => setChatQuestion(event.target.value)} placeholder="Ask a question about the uploaded tender…" className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:bg-gray-900" />
            <button disabled={chatWorking || !chatQuestion.trim()} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{chatWorking ? 'Answering…' : 'Ask'}</button>
          </form>
        </section>

        <section className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
          <h3 className="font-semibold">Tender timeline</h3>
          {importantTimeline.length > 0
            ? <div className="mt-4 overflow-x-auto pb-3">
              <ol aria-label="Tender milestones in chronological order" className="flex min-w-full snap-x snap-mandatory items-stretch">
                {importantTimeline.map((item, index, timeline) => <li
                  key={`${item.document}-${item.location}-${item.value}-${index}`}
                  className="relative flex min-w-[min(70vw,16rem)] flex-1 basis-0 snap-start flex-col px-2 first:pl-0 last:pr-0 sm:min-w-0"
                >
                  {index < timeline.length - 1 && <span aria-hidden="true" className="absolute left-8 right-0 top-4 h-0.5 bg-indigo-100 dark:bg-indigo-900" />}
                  <div className="relative z-10 flex items-center gap-2">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-indigo-500 bg-white text-xs font-bold text-indigo-700 dark:bg-gray-800 dark:text-indigo-300">{index + 1}</span>
                    <span className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">Phase {index + 1}</span>
                  </div>
                  <div className="mt-3 min-h-36 flex-1 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900/50">
                    <p className="break-words text-sm font-semibold leading-5 text-gray-900 dark:text-gray-100">{getTimelinePhaseName(item.event, item.value, item.excerpt)}</p>
                    <p className="mt-2 break-words text-sm font-bold text-indigo-700 dark:text-indigo-300">{item.value}</p>
                    <p className="mt-3 break-all text-xs text-gray-500">{item.document} · {item.location}</p>
                  </div>
                </li>)}
              </ol>
            </div>
            : <p className="mt-3 text-sm text-gray-500">No tender-activity dates were found in the uploaded document text.</p>}
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
            <h3 className="font-semibold">Tender economics</h3>
            {importantFinancialAmounts.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-medium text-gray-500">Key tender costs and securities</p>
                <ul className="mt-2 space-y-3 text-sm">
                  {importantFinancialAmounts.map((item, index) => (
                    <li key={`${item.document}-${item.location}-${item.value}-${index}`}>
                      {item.cost_type && <p className="text-xs font-medium text-gray-500">{item.cost_type}</p>}
                      <span className="font-semibold">{item.value}</span>
                      <p className="mt-0.5 text-xs text-gray-500">{item.document} · {item.location}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {importantEconomicsSummaries.length > 0
              ? <ul className="mt-3 list-inside list-disc space-y-2 text-sm">
                {importantEconomicsSummaries.map((item, index) => <li key={`${item.summary}-${index}`}>
                  {item.summary}
                  {item.references?.length ? <p className="ml-5 mt-0.5 text-xs text-gray-500">Source: {formatDocumentReferences(item.references)}</p> : null}
                </li>)}
              </ul>
              : <p className="mt-3 text-sm text-gray-500">No key financial terms could be summarized from the uploaded document text.</p>}
          </div>
        </section>

        <section className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
          <h3 className="font-semibold">Suggested next steps</h3>
          {report.recommendation.next_steps.length > 0
            ? <ol className="mt-3 space-y-3">{report.recommendation.next_steps.map((step, index) => {
            return <li key={`${step.task}-${index}`} className="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
              <div className="flex items-start gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">{index + 1}</span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{step.task}</p>
                  {step.description && <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{step.description}</p>}
                  {step.references?.length ? <p className="mt-1 text-xs text-gray-500">Reference: {formatDocumentReferences(step.references)}</p> : null}
                </div>
              </div>
            </li>
          })}</ol>
            : <p className="mt-3 text-sm text-gray-500">The document review did not identify specific evidence-based actions.</p>}
        </section>

      </div>}

    </div>
  )
}
