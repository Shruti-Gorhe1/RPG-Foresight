import { useEffect, useState } from 'react'
import {
  RefreshCw,
  Monitor,
  Database,
  Clock,
  AlertCircle,
  CheckCircle2,
  Play,
  StopCircle,
} from 'lucide-react'
import { getApiErrorMessage, listConnectors, syncConnector, ConnectorInfo } from '../services/api'

type ConnectorStatus = 'idle' | 'running' | 'success' | 'error'

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([])
  const [syncStatuses, setSyncStatuses] = useState<Record<string, ConnectorStatus>>({})
  const [syncResults, setSyncResults] = useState<Record<string, any>>({})
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const data = await listConnectors()
        if (active) {
          setConnectors(data.data)
          setLoadError('')
        }
      } catch (err) {
        if (active) {
          setConnectors([])
          setLoadError(getApiErrorMessage(err, 'Unable to load source connections.'))
        }
      }
    }
    load()
    return () => {
      active = false
    }
  }, [])

  const handleSyncConnector = async (connector: ConnectorInfo) => {
    setSyncStatuses((prev) => ({ ...prev, [connector.connector_id]: 'running' }))
    try {
      const res = await syncConnector(connector.connector_id)
      const errors = res.data.errors ?? []
      const deliveryFailures = res.data.routing?.deliveries_failed ?? 0
      const errorMessage =
        errors.join('; ') ||
        (deliveryFailures ? `${deliveryFailures} notification delivery attempt(s) failed` : '')
      setSyncStatuses((prev) => ({
        ...prev,
        [connector.connector_id]: res.data.status === 'completed' && !errorMessage ? 'success' : 'error',
      }))
      setSyncResults((prev) => ({
        ...prev,
        [connector.connector_id]: { ...res.data, error: errorMessage || undefined },
      }))
      // Refresh connector list
      const data = await listConnectors()
      setConnectors(data.data)
    } catch (err: any) {
      setSyncStatuses((prev) => ({ ...prev, [connector.connector_id]: 'error' }))
      setSyncResults((prev) => ({
        ...prev,
        [connector.connector_id]: {
          error: err.response?.data?.detail || 'Sync failed',
        },
      }))
    }
  }

  return (
    <div className="p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-950 dark:text-gray-50">Source Connections</h2>
          <p className="mt-1 text-sm text-gray-500">
            Connect and sync CRM and public-portal data sources.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              connectors
                .filter((connector) => connector.is_active && connector.is_enabled)
                .forEach((connector) => handleSyncConnector(connector))
            }}
            disabled={Object.values(syncStatuses).includes('running')}
            className="rounded bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {Object.values(syncStatuses).includes('running') ? (
              <span className="flex items-center gap-1">
                <RefreshCw className="animate-spin" size={14} />
                Syncing allâ€¦
              </span>
            ) : (
              <span>
                <RefreshCw size={14} />
                Sync All Connectors
              </span>
            )}
          </button>
        </div>
      </div>

      {loadError && (
        <div role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {loadError}
        </div>
      )}

      {!loadError && connectors.length === 0 && (
        <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 text-center">
          <AlertCircle size={32} className="mx-auto text-gray-400 mb-3" />
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">No connectors configured</h3>
          <p className="mt-1 text-sm text-gray-500">
            Add CRM or public-portal connectors to begin automated signal ingestion.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {connectors.map((connector) => (
          <div
            key={connector.connector_id}
            className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm"
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-bold text-gray-900 dark:text-gray-100">{connector.source_name}</h3>
                <p className="mt-0.5 text-xs text-gray-500">{connector.connector_id}</p>
                {connector.description && (
                  <p className="mt-2 text-xs text-gray-500">{connector.description}</p>
                )}
              </div>
              <div className="flex items-center gap-1">
                <span className={`h-2 w-2 rounded-full ${
                  connector.is_active ? 'bg-emerald-500' : 'bg-gray-400'
                }`} />
                <span className="text-[10px] font-medium text-gray-500 uppercase">
                  {connector.is_active ? 'active' : 'inactive'}
                </span>
              </div>
            </div>

            <div className="space-y-3 mb-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">Source type</span>
                <span className="font-medium text-gray-900 dark:text-gray-100 capitalize">{connector.source_type}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">Enabled</span>
                <span className={`font-medium ${connector.is_enabled ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {connector.is_enabled ? 'Yes' : 'No'}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">Last sync</span>
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  {connector.last_sync_at ? new Date(connector.last_sync_at).toLocaleString() : 'Never'}
                </span>
              </div>
              {connector.last_error && (
                <div className="flex items-center gap-1 text-xs text-rose-600">
                  <AlertCircle size={12} />
                  <span>{connector.last_error}</span>
                </div>
              )}
              {connector.last_run?.errors?.length ? (
                <div role="alert" className="mt-3 rounded-lg bg-rose-50 p-3 text-xs text-rose-700">
                  {connector.last_run.errors.join('; ')}
                </div>
              ) : null}
            </div>

            {connector.last_run && (
              <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Last run</h4>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">Status</span>
                  <span className={`font-medium ${
                    connector.last_run.status === 'completed'
                      ? 'text-emerald-600'
                      : connector.last_run.status === 'failed'
                        ? 'text-rose-600'
                        : 'text-amber-600'
                  }`}>
                    {connector.last_run.status}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-gray-500">Records fetched</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{connector.last_run.records_fetched}</span>
                </div>
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-gray-500">Records created</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{connector.last_run.records_created}</span>
                </div>
              </div>
            )}

            <div className="mt-4">
              <button
                onClick={() => handleSyncConnector(connector)}
                disabled={
                  !connector.is_active ||
                  !connector.is_enabled ||
                  syncStatuses[connector.connector_id] === 'running'
                }
                className="w-full rounded bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {syncStatuses[connector.connector_id] === 'running' ? (
                  <span className="flex items-center gap-1">
                    <RefreshCw className="animate-spin" size={12} />
                    Runningâ€¦
                  </span>
                ) : syncStatuses[connector.connector_id] === 'success' ? (
                  <span className="flex items-center gap-1">
                    <CheckCircle2 size={14} className="text-emerald-400" />
                    Synced
                  </span>
                ) : syncStatuses[connector.connector_id] === 'error' ? (
                  <span className="flex items-center gap-1">
                    <AlertCircle size={14} className="text-rose-400" />
                    Error
                  </span>
                ) : !connector.is_active || !connector.is_enabled ? (
                  <span className="flex items-center gap-1">
                    <StopCircle size={14} />
                    Disabled
                  </span>
                ) : (
                  <span>
                    <Play size={14} />
                    Sync
                  </span>
                )}
              </button>
            </div>
          </div>
        ))}
      </div>

      {Object.values(syncResults).some((r) => r?.error) && (
        <div className="mt-6 rounded-xl border border-rose-200 dark:border-rose-900/30 bg-rose-50 dark:bg-rose-900/20 p-4">
          <h3 className="font-semibold text-rose-900 mb-2">Sync errors</h3>
          <ul className="text-sm text-rose-800 list-disc pl-5">
            {Object.entries(syncResults).map(([cid, result]) => (
              result.error && (
                <li key={cid}>
                  <strong>{cid}:</strong> {result.error}
                </li>
              )
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
