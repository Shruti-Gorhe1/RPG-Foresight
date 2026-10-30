export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-4 animate-fade-in">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Settings</h2>
      <div className="card p-6 text-sm text-gray-600 space-y-2">
        <p>Configure this app via environment variables (see <code className="font-mono text-zen-700">app/.env.example</code>).</p>
        <p>Backend base URL is resolved through the nginx proxy in production and the Vite dev proxy locally.</p>
      </div>
    </div>
  )
}

