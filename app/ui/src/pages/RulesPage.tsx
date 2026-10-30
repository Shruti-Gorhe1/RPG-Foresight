import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { createRule, deleteRule, getApiErrorMessage, listRecipients, listRules, previewRule, setRuleEnabled, type RecipientAddress } from '../services/api'

export default function RulesPage() {
  const [rules, setRules] = useState<any[]>([])
  const [recipients, setRecipients] = useState<RecipientAddress[]>([])
  const [loading, setLoading] = useState(true)
  const [showRuleForm, setShowRuleForm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [previews, setPreviews] = useState<Record<string, { evaluated: number; matches: number; excluded: number; exclusion_reasons: Record<string, number>; samples: { event_id: string; tender_id: string; project_name: string; match: boolean; reason: string }[] }>>({})
  const [previewing, setPreviewing] = useState('')
  const [updatingRule, setUpdatingRule] = useState('')
  const [deletingRule, setDeletingRule] = useState('')
  const [ruleForm, setRuleForm] = useState({
    rule_id: '', name: '', description: '', enabled: false, trigger_stages: '',
    min_win_probability_percent: '' as number | '', purpose: 'Tender notification', channel: 'email', selected_recipient_email: '', selected_recipient_emails: [] as string[],
    regions: '', tender_currency: '', minimum_tender_value: '', maximum_tender_value: '',
    minimum_days_to_close: '', maximum_days_to_close: '',
    max_event_age_seconds: 86400, max_probability_age_seconds: 604800,
    material_categories: '',
    routes: [{ subsidiary_entity_id: '', material_categories: [] as string[] }]
  })

  const load = async () => {
    try {
      setLoading(true)
      const [rulesRes, recipientsRes] = await Promise.all([listRules(), listRecipients()])
      setRules(rulesRes.data || [])
      setRecipients(recipientsRes.data || [])
      setError('')
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to load routing rules.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const submitRule = async (e: any) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const payload: any = { ...ruleForm }
      if (typeof payload.trigger_stages === 'string') {
        payload.trigger_stages = payload.trigger_stages.split(',').map((s:string)=>s.trim()).filter(Boolean)
      }
      payload.selected_recipient_emails = ruleForm.selected_recipient_emails
      payload.selected_recipient_email = ruleForm.selected_recipient_emails[0]
      payload.regions = ruleForm.regions.split(',').map((s) => s.trim()).filter(Boolean)
      payload.min_win_probability_percent = ruleForm.min_win_probability_percent === '' ? null : Number(ruleForm.min_win_probability_percent)
      const materialCategories = ruleForm.material_categories.split(',').map((category) => category.trim()).filter(Boolean)
      if (materialCategories.length === 0) {
        setError('Enter at least one material category.')
        return
      }
      payload.routes = ruleForm.routes.map((route) => ({ ...route, material_categories: materialCategories }))
      payload.minimum_tender_value = ruleForm.minimum_tender_value === '' ? null : Number(ruleForm.minimum_tender_value)
      payload.maximum_tender_value = ruleForm.maximum_tender_value === '' ? null : Number(ruleForm.maximum_tender_value)
      payload.minimum_days_to_close = ruleForm.minimum_days_to_close === '' ? null : Number(ruleForm.minimum_days_to_close)
      payload.maximum_days_to_close = ruleForm.maximum_days_to_close === '' ? null : Number(ruleForm.maximum_days_to_close)
      await createRule(payload)
      setShowRuleForm(false)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to create routing rule.'))
    } finally {
      setSubmitting(false)
    }
  }

  const runPreview = async (ruleId: string) => {
    setPreviewing(ruleId)
    setError('')
    try {
      const result = await previewRule(ruleId)
      setPreviews({ ...previews, [ruleId]: result.data })
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to preview this rule.'))
    } finally {
      setPreviewing('')
    }
  }

  const toggleRule = async (ruleId: string, enabled: boolean) => {
    setUpdatingRule(ruleId)
    setError('')
    try {
      await setRuleEnabled(ruleId, enabled)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to update rule status.'))
    } finally {
      setUpdatingRule('')
    }
  }

  const removeRule = async (ruleId: string, ruleName: string) => {
    if (!window.confirm(`Permanently delete routing rule "${ruleName}" (${ruleId})? Future tenders will no longer be evaluated by this rule. Existing delivery and audit history will remain.`)) {
      return
    }
    setDeletingRule(ruleId)
    setError('')
    try {
      await deleteRule(ruleId)
      setRules((current) => current.filter((rule) => rule.rule_id !== ruleId))
      setPreviews((current) => {
        const { [ruleId]: _removed, ...remaining } = current
        return remaining
      })
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to delete this rule.'))
    } finally {
      setDeletingRule('')
    }
  }

  return (
    <div className='p-6'>
      <div className='flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between mb-6'>
        <div>
          <h2 className='text-2xl font-bold'>Rules</h2>
          <p className='text-sm text-gray-500'>Configure match criteria, preview recent tenders, then enable the rule.</p>
        </div>
        <button onClick={()=>{
          setRuleForm({
            rule_id: '', name: '', description: '', enabled: false, trigger_stages: '',
            min_win_probability_percent: '',             purpose: 'Tender notification', channel: 'email', selected_recipient_email: '', selected_recipient_emails: [],
            regions: '', tender_currency: '', minimum_tender_value: '', maximum_tender_value: '',
            minimum_days_to_close: '', maximum_days_to_close: '',
            max_event_age_seconds: 86400, max_probability_age_seconds: 604800,
            material_categories: '', routes: [{ subsidiary_entity_id: '', material_categories: [] }],
          })
          setError('')
          setShowRuleForm(true)
        }} className='rounded bg-indigo-600 px-4 py-2 text-sm text-white'>
          <Plus size={14} className='mr-1 inline' /> Add Rule
        </button>
      </div>

      {showRuleForm && (
        <div className='fixed inset-0 bg-black/50 flex items-center justify-center z-50'>
          <form onSubmit={submitRule} className='bg-white p-6 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto space-y-3'>
            <h3 className='font-bold'>Create Routing Rule</h3>
            <input className='w-full border p-2 rounded' placeholder='Rule ID' value={ruleForm.rule_id} onChange={e=>setRuleForm({...ruleForm, rule_id:e.target.value})} required />
            <input className='w-full border p-2 rounded' placeholder='Name' value={ruleForm.name} onChange={e=>setRuleForm({...ruleForm, name:e.target.value})} required />
            <input className='w-full border p-2 rounded' placeholder='Trigger stages (comma separated)' value={ruleForm.trigger_stages} onChange={e=>setRuleForm({...ruleForm, trigger_stages:e.target.value})} required />
            <label className='block text-sm font-medium text-gray-700'>
              Material categories for this receiver (comma separated)
              <input className='mt-1 w-full border p-2 rounded' placeholder='Enter actual material categories' value={ruleForm.material_categories} onChange={e=>setRuleForm({...ruleForm, material_categories:e.target.value})} required />
            </label>
            <label className='block text-sm font-medium text-gray-700'>
              Minimum win probability (%) (optional)
              <input
                className='mt-1 w-full border p-2 rounded'
                type='number'
                min={0}
                max={100}
                step={1}
                value={ruleForm.min_win_probability_percent}
                onChange={e=>setRuleForm({...ruleForm, min_win_probability_percent:e.target.value === '' ? '' : Number(e.target.value)})}
              />
              <span className='mt-1 block text-xs font-normal text-gray-500'>
                A tender must have a probability at or above this value, updated within the rule’s allowed age.
              </span>
            </label>
            <label className='block text-sm font-medium text-gray-700'>
              Maximum tender event age (hours)
              <input
                className='mt-1 w-full border p-2 rounded'
                type='number'
                min={1}
                value={Math.floor(ruleForm.max_event_age_seconds / 3600)}
                onChange={e=>setRuleForm({...ruleForm, max_event_age_seconds:Number(e.target.value) * 3600})}
                required
              />
              <span className='mt-1 block text-xs font-normal text-gray-500'>
                Older tenders are excluded. Keep this short for live alerts; use a longer window only for historical/demo data.
              </span>
            </label>
            <input className='w-full border p-2 rounded' placeholder='Channel' value={ruleForm.channel} onChange={e=>setRuleForm({...ruleForm, channel:e.target.value})} required readOnly />
            <label className='block text-sm font-medium text-gray-700'>
              Send matching signals to
              <select
                className='mt-1 w-full border p-2 rounded'
                multiple
                size={Math.min(recipients.length || 2, 5)}
                value={ruleForm.selected_recipient_emails}
                onChange={e=>setRuleForm({...ruleForm, selected_recipient_emails:Array.from(e.target.selectedOptions, option => option.value)})}
                required
              >
                {recipients.map((recipient) => (
                  <option key={recipient.id} value={recipient.email}>
                    {recipient.display_name ? `${recipient.display_name} <${recipient.email}>` : recipient.email}
                  </option>
                ))}
              </select>
            </label>
            {recipients.length === 0 && (
              <p className='text-sm text-amber-700'>Add an email address on the Recipients page before creating this rule.</p>
            )}
            <label className='block text-sm font-medium text-gray-700'>
              Regions (comma separated; leave blank for any region)
              <input className='mt-1 w-full border p-2 rounded' value={ruleForm.regions} onChange={e=>setRuleForm({...ruleForm, regions:e.target.value})} />
            </label>
            <div className='grid grid-cols-2 gap-2'>
              <label className='text-sm text-gray-700'>Value currency
                <input className='mt-1 w-full border p-2 rounded uppercase' maxLength={8} placeholder='INR' value={ruleForm.tender_currency} onChange={e=>setRuleForm({...ruleForm, tender_currency:e.target.value.toUpperCase()})} />
              </label>
              <label className='text-sm text-gray-700'>Minimum tender value
                <input className='mt-1 w-full border p-2 rounded' type='number' min={0} value={ruleForm.minimum_tender_value} onChange={e=>setRuleForm({...ruleForm, minimum_tender_value:e.target.value})} />
              </label>
              <label className='text-sm text-gray-700'>Maximum tender value
                <input className='mt-1 w-full border p-2 rounded' type='number' min={0} value={ruleForm.maximum_tender_value} onChange={e=>setRuleForm({...ruleForm, maximum_tender_value:e.target.value})} />
              </label>
              <label className='text-sm text-gray-700'>Minimum days until closing
                <input className='mt-1 w-full border p-2 rounded' type='number' min={0} value={ruleForm.minimum_days_to_close} onChange={e=>setRuleForm({...ruleForm, minimum_days_to_close:e.target.value})} />
              </label>
              <label className='text-sm text-gray-700'>Maximum days until closing
                <input className='mt-1 w-full border p-2 rounded' type='number' min={0} value={ruleForm.maximum_days_to_close} onChange={e=>setRuleForm({...ruleForm, maximum_days_to_close:e.target.value})} />
              </label>
            </div>
            <p className='text-xs text-gray-500'>New rules are saved as drafts. Preview recent tenders before enabling to avoid unexpected email volume.</p>
            {error && <p role='alert' className='text-sm text-red-700'>{error}</p>}
            <div className='flex gap-2'>
              <button type='submit' disabled={submitting || recipients.length === 0} className='bg-indigo-600 text-white px-4 py-2 rounded disabled:opacity-50'>{submitting ? 'Creating…' : 'Create'}</button>
              <button type='button' onClick={()=>{setShowRuleForm(false); setError('')}} className='border px-4 py-2 rounded'>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {error && !showRuleForm && <p role='alert' className='mb-4 text-sm text-red-700'>{error}</p>}

      <div className='rounded border bg-white'>
        <div className='p-4 font-bold'>Routing Rules</div>
        <table className='w-full text-sm'>
          <thead><tr className='bg-gray-50'><th className='text-left p-2'>Rule ID</th><th className='text-left p-2'>Trigger / filters</th><th className='text-left p-2'>Probability</th><th className='text-left p-2'>Recipients</th><th className='text-left p-2'>Status / preview / actions</th></tr></thead>
          <tbody>
            {rules.map(r => (<tr key={r.rule_id} className='border-t align-top'>
              <td className='p-2 font-mono text-xs'>{r.rule_id}</td>
              <td className='p-2'><div>{(r.trigger_stages||[]).join(', ')}</div><div className='text-xs text-gray-500'>{(r.regions||[]).join(', ') || 'Any region'} · {r.minimum_tender_value != null || r.maximum_tender_value != null ? `${r.tender_currency || ''} ${r.minimum_tender_value ?? '0'}–${r.maximum_tender_value ?? '∞'}` : 'Any value'} · {r.minimum_days_to_close ?? 0}–{r.maximum_days_to_close ?? '∞'} days</div></td>
              <td className='p-2'>{r.min_win_probability_percent == null ? 'No minimum' : `≥ ${r.min_win_probability_percent}%`}</td>
              <td className='p-2'>{(r.selected_recipient_emails || [r.selected_recipient_email]).filter(Boolean).join(', ') || 'Not selected'}</td>
              <td className='p-2'><div className='flex flex-wrap items-center gap-2'>
                <span>{r.enabled ? 'Active' : 'Draft'}</span>
                <button disabled={previewing === r.rule_id} onClick={() => void runPreview(r.rule_id)} className='rounded border px-2 py-1 text-xs disabled:opacity-50'>{previewing === r.rule_id ? 'Previewing…' : 'Preview matches'}</button>
                {r.enabled
                  ? <button disabled={updatingRule === r.rule_id} onClick={() => void toggleRule(r.rule_id, false)} className='rounded border px-2 py-1 text-xs'>Disable</button>
                  : <button disabled={!r.previewed_at || updatingRule === r.rule_id} onClick={() => void toggleRule(r.rule_id, true)} className='rounded bg-emerald-600 px-2 py-1 text-xs text-white disabled:opacity-50'>Enable</button>}
                <button
                  type='button'
                  aria-label={`Delete rule ${r.rule_id}`}
                  disabled={deletingRule !== '' || updatingRule === r.rule_id || previewing === r.rule_id}
                  onClick={() => void removeRule(r.rule_id, r.name)}
                  className='inline-flex items-center gap-1 rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50'
                >
                  <Trash2 size={12} /> {deletingRule === r.rule_id ? 'Deleting…' : 'Delete'}
                </button>
              </div>
                {previews[r.rule_id] && <div className='mt-1 text-xs text-gray-500'>
                  <p>{previews[r.rule_id].matches} matched / {previews[r.rule_id].evaluated} evaluated · {previews[r.rule_id].excluded} excluded</p>
                  {Object.entries(previews[r.rule_id].exclusion_reasons).map(([reason, count]) => <p key={reason}>{reason.replace(/_/g, ' ')}: {count}</p>)}
                  <details className='mt-1'>
                    <summary className='cursor-pointer'>Tender-by-tender explanation</summary>
                    {previews[r.rule_id].samples.slice(0, 10).map((sample) => <p key={sample.event_id}>{sample.tender_id} · {sample.match ? 'matched' : sample.reason.replace(/_/g, ' ')}</p>)}
                  </details>
                </div>}
              </td>
            </tr>))}
            {loading && <tr><td colSpan={5} className='p-4 text-center text-gray-500'>Loading rules…</td></tr>}
            {!loading && rules.length===0 && <tr><td colSpan={5} className='p-4 text-center text-gray-500'>No rules</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
