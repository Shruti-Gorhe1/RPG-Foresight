import { useEffect, useState } from 'react'
import { Activity, Clock, Database, List } from 'lucide-react'
import { listSignalHistory, type TenderEvent } from '../services/api'

export default function SignalHistoryPage() {
  const [signals, setSignals] = useState<TenderEvent[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoading(true)
        const res = await listSignalHistory()
        if (active) setSignals(res.data)
      } catch {
        if (active) setSignals([])
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-950 dark:text-gray-50">Signal History</h2>
          <p className="mt-1 text-sm text-gray-500">
            Complete audit history of all tender signals, including source, stage changes, and routing decisions.
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Time</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Tender ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Project</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Stage</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Source</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Probability</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Provenance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-500">
                    Loading historyâ€¦
                  </td>
                </tr>
              ) : signals.length > 0 ? (
                signals.map((s) => (
                  <tr key={s.event_id} className="hover:bg-gray-50/70 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">
                      {s.ingested_at ? new Date(s.ingested_at).toLocaleString() : '-'}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{s.tender_id}</td>
                    <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300">{s.project_name}</td>
                    <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300">{s.stage}</td>
                    <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300 capitalize">{s.source_type}</td>
                    <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300">
                      {s.existing_win_probability_percent ?? 'â€”'}%
                    </td>
                    <td className="px-4 py-3 text-[10px] text-gray-400 italic">
                      {s.data_provenance}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-500">
                    No signal history yet. Sync connectors to ingest data.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
