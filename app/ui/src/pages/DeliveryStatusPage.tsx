import { FormEvent, Fragment, useEffect, useState } from 'react'
import { BellRing, CheckCircle2, Clock, AlertCircle, List, Mail, Phone, Users } from 'lucide-react'
import { deliveryAttempts, deliveryStats, getApiErrorMessage, getEmailConfiguration, listDeliveries, retryDelivery, sendTestEmail, type DeliveryStats, type NotificationDelivery } from '../services/api'

export default function DeliveryStatusPage() {
  const [stats, setStats] = useState<DeliveryStats>({
    total: 0,
    pending: 0,
    sent: 0,
    delivered: 0,
    failed: 0,
    suppressed: 0,
  })
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([])
  const [loading, setLoading] = useState(true)
  const [emailConfig, setEmailConfig] = useState<{ provider: string; configured: boolean; sender: string | null } | null>(null)
  const [testRecipient, setTestRecipient] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionNotice, setActionNotice] = useState('')
  const [working, setWorking] = useState(false)
  const [expandedDelivery, setExpandedDelivery] = useState<number | null>(null)
  const [attempts, setAttempts] = useState<Record<number, any[]>>({})

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoading(true)
        const [statsRes, deliveriesRes, configRes] = await Promise.all([deliveryStats(), listDeliveries(), getEmailConfiguration()])
        if (active) {
          setStats(statsRes.data)
          setDeliveries(deliveriesRes.data)
          setEmailConfig(configRes.data)
        }
      } catch {
        if (active) {
          setDeliveries([])
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [])

  const sendTest = async (event: FormEvent) => {
    event.preventDefault()
    setWorking(true)
    setActionError('')
    setActionNotice('')
    try {
      await sendTestEmail(testRecipient)
      setActionNotice(`Test email accepted for ${testRecipient}.`)
    } catch (err) {
      setActionError(getApiErrorMessage(err, 'Test email failed.'))
    } finally {
      setWorking(false)
    }
  }

  const retry = async (deliveryId: number) => {
    setWorking(true)
    setActionError('')
    setActionNotice('')
    try {
      const result = await retryDelivery(deliveryId)
      setActionNotice(result.data.status === 'sent' ? 'Retry sent successfully.' : `Retry failed: ${result.data.error_message || result.data.status}`)
      const [statsRes, deliveriesRes] = await Promise.all([deliveryStats(), listDeliveries()])
      setStats(statsRes.data)
      setDeliveries(deliveriesRes.data)
    } catch (err) {
      setActionError(getApiErrorMessage(err, 'Unable to retry delivery.'))
    } finally {
      setWorking(false)
    }
  }

  const toggleAttempts = async (deliveryId: number) => {
    if (expandedDelivery === deliveryId) {
      setExpandedDelivery(null)
      return
    }
    setExpandedDelivery(deliveryId)
    if (attempts[deliveryId]) return
    try {
      const result = await deliveryAttempts(deliveryId)
      setAttempts({ ...attempts, [deliveryId]: result.data })
    } catch (err) {
      setActionError(getApiErrorMessage(err, 'Unable to load delivery attempt history.'))
    }
  }

  return (
    <div className="p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-950 dark:text-gray-50">Delivery Status</h2>
          <p className="mt-1 text-sm text-gray-500">
            Notification delivery status for tender signals sent to recipients configured in routing rules.
          </p>
        </div>

        <section className="mb-6 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Email configuration</h3>
              <p className="mt-1 text-sm text-gray-500">
                Provider: {emailConfig?.provider || 'loading'} · Sender: {emailConfig?.sender || 'not configured'}
              </p>
            </div>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${emailConfig?.configured ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
              {emailConfig?.configured ? 'Credentials configured' : 'Not configured'}
            </span>
          </div>
          <p className="mt-2 text-xs text-gray-500">Configuration does not confirm sender-domain verification. A test message checks provider acceptance and displays any provider rejection.</p>
          <form onSubmit={sendTest} className="mt-3 flex flex-wrap gap-2">
            <input aria-label="Test email recipient" type="email" required placeholder="you@company.com" className="min-w-64 rounded border px-3 py-2 text-sm dark:bg-gray-900" value={testRecipient} onChange={(event) => setTestRecipient(event.target.value)} />
            <button disabled={working || !emailConfig?.configured} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{working ? 'Sending…' : 'Send test email'}</button>
          </form>
          {actionError && <p role="alert" className="mt-2 text-sm text-rose-700">{actionError}</p>}
          {actionNotice && <p role="status" className="mt-2 text-sm text-emerald-700">{actionNotice}</p>}
        </section>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
        <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">Total signals</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total}</p>
            </div>
            <List size={20} className="text-gray-300" />
          </div>
        </div>
        <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">Pending</p>
              <p className="text-2xl font-bold text-amber-600">{stats.pending}</p>
            </div>
            <Clock size={20} className="text-amber-300" />
          </div>
        </div>
        <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">Sent</p>
              <p className="text-2xl font-bold text-emerald-600">{stats.sent}</p>
            </div>
            <CheckCircle2 size={20} className="text-emerald-300" />
          </div>
        </div>
        <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">Failed</p>
              <p className="text-2xl font-bold text-rose-600">{stats.failed}</p>
            </div>
            <AlertCircle size={20} className="text-rose-300" />
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm">
        <div className="border-b border-gray-100 dark:border-gray-700 p-4">
          <h3 className="font-bold text-gray-900 dark:text-gray-100">Delivery queue</h3>
          <p className="mt-1 text-sm text-gray-500">
            Notifications sent to configured recipients. Status reflects the last delivery attempt.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Tender ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Project</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Recipient</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Channel</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Sent time (device local)</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Failure details</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-sm text-gray-500">
                    Loading deliveriesâ€¦
                  </td>
                </tr>
              ) : deliveries.length > 0 ? (
                deliveries.map((d) => {
                  const statusStyles: Record<string, string> = {
                    pending: 'bg-amber-100 text-amber-700',
                    sent: 'bg-emerald-100 text-emerald-700',
                    delivered: 'bg-emerald-100 text-emerald-700',
                    failed: 'bg-rose-100 text-rose-700',
                    suppressed: 'bg-gray-100 dark:bg-gray-800 text-gray-600',
                  }
                  const statusIcons: Record<string, any> = {
                    pending: Clock,
                    sent: CheckCircle2,
                    delivered: CheckCircle2,
                    failed: AlertCircle,
                    suppressed: Mail,
                  }
                  const Icon = statusIcons[d.status] ?? Clock
                  return (
                    <Fragment key={d.id}>
                    <tr className="hover:bg-gray-50/70 dark:hover:bg-gray-700/50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-400">{d.event_id}</td>
                      <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300">
                        {(d.payload as any)?.project_name ?? '-'}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300">{d.recipient_user_id}</td>
                      <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300 capitalize">{d.channel}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${statusStyles[d.status] ?? 'bg-gray-100 dark:bg-gray-800 text-gray-600'}`}>
                          <Icon size={10} />
                          {d.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300">
                        {d.sent_at ? new Date(d.sent_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-xs text-rose-700 dark:text-rose-300">
                        {d.status === 'failed' ? (d.error_message || 'No error detail recorded') : '-'}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        <div className="flex gap-2">
                          {d.status === 'failed' && <button disabled={working} onClick={() => void retry(d.id)} className="rounded border px-2 py-1 disabled:opacity-50">Retry</button>}
                          <button onClick={() => void toggleAttempts(d.id)} className="rounded border px-2 py-1">{expandedDelivery === d.id ? 'Hide attempts' : 'Attempts'}</button>
                        </div>
                      </td>
                    </tr>
                    {expandedDelivery === d.id && <tr><td colSpan={8} className="bg-gray-50 px-4 py-3 dark:bg-gray-900">
                      <p className="mb-2 text-xs font-semibold">Attempt history</p>
                      {(attempts[d.id] || []).length ? <ul className="space-y-1 text-xs">{attempts[d.id].map((attempt) => <li key={attempt.id}>{attempt.created_at ? new Date(attempt.created_at).toLocaleString() : 'Unknown time'} · {attempt.status}{attempt.error_message ? ` · ${attempt.error_message}` : ''}</li>)}</ul> : <p className="text-xs text-gray-500">No persisted attempts yet for this delivery.</p>}
                    </td></tr>}
                    </Fragment>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-sm text-gray-500">
                    No deliveries yet. Sync signals to route and deliver tender events.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {stats.sent === 0 && stats.total === 0 && (
          <div className="mt-6 rounded-xl border border-amber-100 bg-amber-50 dark:bg-amber-900/20 p-4">
            <div className="flex items-start gap-2">
              <BellRing size={16} className="mt-0.5 text-amber-600" />
              <div>
                <p className="text-sm font-semibold text-amber-900">No deliveries yet</p>
                <p className="mt-0.5 text-xs text-amber-800">
                  Deliveries are created automatically after syncing when a tender event matches an enabled routing
                  rule with a configured address-book recipient.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
