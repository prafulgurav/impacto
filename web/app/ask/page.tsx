'use client';
// 'use client': consumes an SSE stream and keeps conversation state.

import { useCallback, useEffect, useRef, useState } from 'react';

import CitationList from '@/components/CitationList';
import copy from '@/lib/copy/en-IN';
import { API_BASE, api } from '@/lib/api/client';
import { formatDate } from '@/lib/format';

/**
 * The explainer chat.
 *
 * The `composed` event carries a complete, deterministic, fully-cited answer and
 * arrives before any model token. It is rendered the instant it lands; narration
 * replaces it only if it arrives and passes compliance. The user therefore never
 * sees a spinner where an answer should be, and never sees an ungrounded answer.
 */

interface Citation {
  label: string;
  kind: string;
  detail: string;
}

interface Answer {
  question: string;
  composed: string;
  narrated: string;
  citations: Citation[];
  usedLlm: boolean;
  auditId: string | null;
  answeredAt: string;
  done: boolean;
  reverted: boolean;
}

const HISTORY_KEY = 'impacto-ask-history';

export default function AskPage() {
  const [question, setQuestion] = useState('');
  const [current, setCurrent] = useState<Answer | null>(null);
  const [history, setHistory] = useState<Answer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const beaconSent = useRef<string | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      if (raw) setHistory(JSON.parse(raw) as Answer[]);
    } catch {
      // A corrupt history is not worth failing the screen over.
    }
  }, []);

  /**
   * Confirm the answer actually painted.
   *
   * The server records what it produced; this records what a user saw. For a
   * five-year evidentiary record those are different claims.
   */
  useEffect(() => {
    if (!current?.done || !current.auditId) return;
    if (beaconSent.current === current.auditId) return;
    beaconSent.current = current.auditId;
    void api.renderedBeacon(current.auditId).catch(() => undefined);
  }, [current]);

  const ask = useCallback(async (q: string) => {
    setBusy(true);
    setError(null);

    const answer: Answer = {
      question: q,
      composed: '',
      narrated: '',
      citations: [],
      usedLlm: false,
      auditId: null,
      answeredAt: new Date().toISOString(),
      done: false,
      reverted: false,
    };
    setCurrent(answer);

    try {
      const response = await fetch(
        `${API_BASE}/explain/stream?q=${encodeURIComponent(q)}`,
        { credentials: 'include' },
      );
      if (!response.ok || !response.body) throw new Error('stream failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let working = { ...answer };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line; the tail may be partial.
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
          const event = /^event: (.+)$/m.exec(frame)?.[1];
          const raw = /^data: (.+)$/m.exec(frame)?.[1];
          if (!event || !raw) continue;
          const data = JSON.parse(raw);

          if (event === 'composed') {
            working = {
              ...working,
              composed: data.answer,
              citations: data.citations ?? [],
            };
          } else if (event === 'token') {
            working = { ...working, narrated: working.narrated + data.t };
          } else if (event === 'revert') {
            // Narration was produced but failed compliance. Discard what was
            // painted rather than leaving non-compliant text on screen.
            working = { ...working, narrated: '', reverted: true };
          } else if (event === 'done') {
            working = {
              ...working,
              usedLlm: Boolean(data.usedLlm),
              auditId: data.auditId ?? null,
              narrated: data.usedLlm ? working.narrated : '',
              done: true,
            };
          }
          setCurrent({ ...working });
        }
      }

      const finished = { ...working, done: true };
      setCurrent(finished);
      setHistory((prev) => {
        const next = [finished, ...prev].slice(0, 20);
        try {
          localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
        } catch {
          // Storage full or blocked; history is a convenience, not the product.
        }
        return next;
      });
    } catch {
      setError(copy.ask.errorBody);
    } finally {
      setBusy(false);
    }
  }, []);

  const shown = current?.usedLlm && current.narrated ? current.narrated : current?.composed;

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
          {copy.ask.title}
        </h1>
        <p className="mt-1 max-w-prose text-xs text-[var(--color-text-secondary)]">
          {copy.ask.aiDisclosure}
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = question.trim();
          if (trimmed.length >= 3) void ask(trimmed);
        }}
        className="flex gap-2"
      >
        <label htmlFor="ask-input" className="sr-only">
          {copy.ask.placeholder}
        </label>
        <input
          id="ask-input"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={copy.ask.placeholder}
          className="min-w-0 flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length < 3}
          className="rounded-lg bg-[var(--color-text-primary)] px-4 py-2 text-sm font-medium text-[var(--color-surface-1)] disabled:opacity-40"
        >
          {copy.ask.submit}
        </button>
      </form>

      {error && (
        <p role="alert" className="m-0 text-sm text-[var(--color-neg)]">
          {error}
        </p>
      )}

      {current && (
        <section aria-live="polite">
          <h2 className="m-0 text-sm font-semibold">{current.question}</h2>
          {shown ? (
            <div className="mt-2 flex flex-col gap-2">
              {shown.split('\n\n').map((para, i) => (
                <p key={i} className="m-0 max-w-prose text-sm leading-relaxed">
                  {para}
                </p>
              ))}
            </div>
          ) : (
            <p className="m-0 mt-2 text-sm text-[var(--color-muted)]">
              {copy.ask.thinking}
            </p>
          )}

          {current.done && (
            <CitationList citations={current.citations} defaultOpen />
          )}
        </section>
      )}

      {history.length > 0 && (
        <section>
          <h2 className="m-0 mb-2 text-sm font-semibold">
            {copy.ask.historyHeading}
          </h2>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {history.map((entry, index) => (
              <li
                key={`${entry.auditId ?? index}`}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3"
              >
                <p className="m-0 text-sm font-medium">{entry.question}</p>
                <p className="m-0 mt-1 line-clamp-3 text-sm text-[var(--color-text-secondary)]">
                  {entry.usedLlm && entry.narrated ? entry.narrated : entry.composed}
                </p>
                {/* Answers are marked with the date they were generated: an
                    explanation read offline three days later is about a
                    different market than the one in front of the user. */}
                <p className="m-0 mt-1 text-[11px] text-[var(--color-muted)]">
                  {copy.ask.historyDate} {formatDate(entry.answeredAt)}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
