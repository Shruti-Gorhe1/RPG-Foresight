import { useEffect, useState, type FormEvent } from 'react'
import { Pencil, Plus, Trash2, X } from 'lucide-react'
import { createRecipient, deleteRecipient, getApiErrorMessage, listRecipients, type RecipientAddress, updateRecipient } from '../services/api'

export default function RecipientsPage() {
  const [recipients, setRecipients] = useState<RecipientAddress[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<RecipientAddress | null>(null)
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      setLoading(true)
      const response = await listRecipients()
      setRecipients(response.data || [])
      setError('')
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to load recipients.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const openNew = () => {
    setEditing(null)
    setEmail('')
    setDisplayName('')
    setError('')
    setShowForm(true)
  }

  const openEdit = (recipient: RecipientAddress) => {
    setEditing(recipient)
    setEmail(recipient.email)
    setDisplayName(recipient.display_name || '')
    setError('')
    setShowForm(true)
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = { email: email.trim(), display_name: displayName.trim() || undefined }
      if (editing) await updateRecipient(editing.id, payload)
      else await createRecipient(payload)
      setShowForm(false)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to save recipient.'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async (recipient: RecipientAddress) => {
    if (!window.confirm(`Remove ${recipient.email} from the address book? It will also be removed from routing rules.`)) return
    setDeletingId(recipient.id)
    setError('')
    try {
      await deleteRecipient(recipient.id)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to remove recipient.'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className='p-6'>
      <div className='mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between'>
        <div>
          <h2 className='text-2xl font-bold'>Recipients</h2>
          <p className='text-sm text-gray-500'>Email address book for routing rules.</p>
        </div>
        <button onClick={openNew} className='rounded bg-indigo-600 px-4 py-2 text-sm text-white'>
          <Plus size={14} className='mr-1 inline' /> Add Email
        </button>
      </div>

      {showForm && (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4'>
          <form onSubmit={save} className='w-full max-w-md space-y-3 rounded-lg bg-white p-6'>
            <h3 className='font-bold'>{editing ? 'Edit Recipient' : 'Add Recipient Email'}</h3>
            <label className='block text-sm font-medium'>
              Name (optional)
              <input className='mt-1 w-full rounded border p-2' maxLength={128} value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            </label>
            <label className='block text-sm font-medium'>
              Email address
              <input autoFocus className='mt-1 w-full rounded border p-2' type='email' maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            {error && <p role='alert' className='text-sm text-red-700'>{error}</p>}
            <div className='flex gap-2'>
              <button type='submit' disabled={saving} className='rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-50'>
                {saving ? 'Saving…' : editing ? 'Save' : 'Add Email'}
              </button>
              <button type='button' onClick={() => { setShowForm(false); setError('') }} className='inline-flex items-center gap-1 rounded border px-4 py-2'>
                <X size={14} /> Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {error && !showForm && <p role='alert' className='mb-4 text-sm text-red-700'>{error}</p>}

      <div className='rounded border bg-white'>
        <div className='p-4 font-bold'>Email Address Book</div>
        <table className='w-full text-sm'>
          <thead><tr className='bg-gray-50'><th className='p-2 text-left'>Name</th><th className='p-2 text-left'>Email</th><th className='p-2 text-right'>Actions</th></tr></thead>
          <tbody>
            {recipients.map((recipient) => (
              <tr key={recipient.id} className='border-t'>
                <td className='p-2'>{recipient.display_name || '—'}</td>
                <td className='p-2'>{recipient.email}</td>
                <td className='p-2 text-right'>
                  <button type='button' onClick={() => openEdit(recipient)} className='mr-2 inline-flex items-center gap-1 rounded border px-2 py-1'>
                    <Pencil size={14} /> Edit
                  </button>
                  <button type='button' disabled={deletingId === recipient.id} onClick={() => void remove(recipient)} className='inline-flex items-center gap-1 rounded border border-red-200 px-2 py-1 text-red-700 disabled:opacity-50'>
                    <Trash2 size={14} /> {deletingId === recipient.id ? 'Removing…' : 'Remove'}
                  </button>
                </td>
              </tr>
            ))}
            {loading && <tr><td colSpan={3} className='p-4 text-center text-gray-500'>Loading recipients…</td></tr>}
            {!loading && recipients.length === 0 && <tr><td colSpan={3} className='p-4 text-center text-gray-500'>No email addresses yet</td></tr>}
          </tbody>
        </table>
        <p className='px-4 pb-4 text-xs text-gray-500'>Adding an address does not send email. Select addresses in a routing rule to receive matching tender signals. Removing an address also removes it from existing rules.</p>
      </div>
    </div>
  )
}
