import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Signal, Monitor, Shield, List, Activity, Clock, ClipboardList, Bot } from 'lucide-react'
import type { ReactNode } from 'react'
import ThemeToggle from '../ui/ThemeToggle'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/connectors', label: 'Source Connections', icon: Monitor },
  { to: '/rules', label: 'Rules & Policies', icon: Shield },
  { to: '/recipients', label: 'Recipients', icon: List },
  { to: '/signal-history', label: 'Signal History', icon: Activity },
  { to: '/delivery-status', label: 'Delivery Status', icon: Clock },
  { to: '/tenders', label: 'Tender Operations', icon: ClipboardList },
  { to: '/pursuit-copilot', label: 'Pursuit Copilot', icon: Bot },
]

const HIDDEN_ROUTES = new Set(['/playground', '/settings'])

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[#f7f8fc] dark:bg-slate-950">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[248px] flex-col border-r border-gray-200 bg-white lg:flex dark:bg-gray-900 dark:border-gray-700">
        <div className="flex h-[72px] items-center gap-3 border-b border-gray-100 px-5 dark:border-gray-700">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <Signal size={19} />
          </div>
          <div>
            <span className="block text-sm font-bold tracking-tight text-gray-950 dark:text-gray-100">RPG Foresight</span>
            <span className="block text-[10px] font-medium uppercase tracking-[0.14em] text-gray-400 dark:text-gray-500">Agentic tender signals</span>
          </div>
        </div>
        <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 dark:border-gray-700">
          <ThemeToggle />
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Theme</span>
        </div>
        <div className="px-5 pb-2 pt-6 text-[10px] font-bold uppercase tracking-[0.16em] text-gray-400 dark:text-gray-500">Workspace</div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="m-3 rounded-xl border border-amber-100 bg-amber-50 px-3 py-3 dark:border-amber-900/30 dark:bg-amber-900/10">
          <div className="flex items-center gap-2 text-xs font-semibold text-amber-900 dark:text-amber-100">
            <span className="h-2 w-2 rounded-full bg-amber-500" /> Agentic mode
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-amber-800 dark:text-amber-300">Automated ingestion from CRM + public sources</p>
        </div>
      </aside>

      <div className="min-h-screen lg:pl-[248px]">
        <header className="sticky top-0 z-10 flex h-[64px] items-center justify-between border-b border-gray-200 bg-white/95 px-4 backdrop-blur sm:px-6 dark:bg-gray-900/95 dark:border-gray-700">
          <div className="flex items-center gap-3 lg:hidden">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white"><Signal size={17} /></div>
            <span className="text-sm font-bold text-gray-900 dark:text-gray-100">RPG Foresight</span>
          </div>
          <div className="hidden text-sm font-semibold text-gray-700 dark:text-gray-300 lg:block">Tender signal workspace</div>
          <div className="ml-auto flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            <ThemeToggle />
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Tenant: KEC-001
          </div>
        </header>
        <nav className="flex gap-1 overflow-x-auto border-b border-gray-200 bg-white px-3 py-2 lg:hidden dark:border-gray-700 dark:bg-gray-900" aria-label="Main navigation">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold ${
                  isActive ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-gray-500 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800'
                }`
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="p-4 sm:p-6 lg:p-8">
          {HIDDEN_ROUTES.has(window.location.pathname) ? (
            <p role="status" className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
              This page is no longer available.
            </p>
          ) : children}
        </main>
      </div>
    </div>
  )
}