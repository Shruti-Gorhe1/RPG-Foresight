import { useCallback, useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

const STORAGE_KEY = 'rpg_theme'

export default function ThemeToggle() {
  const [dark, setDark] = useState<boolean>(false)

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    const preferDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const initial = stored ? stored === 'dark' : preferDark
    setDark(initial)
    if (initial) document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
  }, [])

  const toggle = useCallback(() => {
    const next = !dark
    setDark(next)
    localStorage.setItem(STORAGE_KEY, next ? 'dark' : 'light')
    if (next) document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
  }, [dark])

  return (
    <button
      onClick={toggle}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="rounded-lg p-2 text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
    >
      {dark ? <Moon size={16} className="text-gray-600 dark:text-gray-300" /> : <Sun size={16} className="text-gray-600 dark:text-gray-300" />}
      <span className="sr-only">{dark ? 'Dark mode' : 'Light mode'}</span>
    </button>
  )
}