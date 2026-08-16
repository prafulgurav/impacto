'use client';
// 'use client': reads and writes localStorage and the document element.

import { useEffect, useState } from 'react';

import copy from '@/lib/copy/en-IN';

export type Theme = 'light' | 'dark' | 'system';
const STORAGE_KEY = 'impacto-theme';

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('system');

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored) setTheme(stored);
  }, []);

  const choose = (next: Theme) => {
    setTheme(next);
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  };

  const options: Theme[] = ['system', 'light', 'dark'];
  const labels: Record<Theme, string> = {
    system: copy.theme.system,
    light: copy.theme.light,
    dark: copy.theme.dark,
  };

  return (
    <fieldset className="m-0 border-0 p-0">
      <legend className="sr-only">{copy.theme.toggle}</legend>
      <div className="inline-flex overflow-hidden rounded-full border border-[var(--color-border)]">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => choose(option)}
            aria-pressed={theme === option}
            className={`px-3 py-1 text-xs transition-colors ${
              theme === option
                ? 'bg-[var(--color-text-primary)] text-[var(--color-surface-1)]'
                : 'text-[var(--color-text-secondary)]'
            }`}
          >
            {labels[option]}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export default ThemeToggle;
