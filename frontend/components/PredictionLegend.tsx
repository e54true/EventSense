// One-time read for visitors trying to make sense of the prediction rows.
// Lives as a collapsible <details> so it doesn't dominate the page once
// understood. Place it just above the predictions list on event detail.

export function PredictionLegend() {
  return (
    <details className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <summary className="cursor-pointer px-4 py-3 text-xs font-semibold text-slate-700 uppercase tracking-wider select-none flex items-center gap-2">
        <span className="text-indigo-600">ⓘ</span>
        How to read these predictions
      </summary>
      <div className="px-4 pb-4 text-xs text-slate-700 space-y-3 leading-relaxed">
        <div>
          <strong className="text-slate-900">kind</strong> — the prediction scope.
          <ul className="list-disc list-inside mt-1 space-y-1 text-slate-600">
            <li>
              <span className="font-semibold text-indigo-700">MARKET</span>:
              broad-index call. The analyzer always emits SPY + QQQ for every event.
            </li>
            <li>
              <span className="font-semibold text-amber-800">COMPANY</span>:
              single-stock call. Only emitted for company-specific events
              (8-K, earnings).
            </li>
          </ul>
        </div>

        <div>
          <strong className="text-slate-900">direction</strong> — expected
          price action over the next 24h.
          <ul className="list-disc list-inside mt-1 space-y-1 text-slate-600">
            <li>
              <span className="text-green-700 font-semibold">▲ BULLISH</span>:
              expected to go up
            </li>
            <li>
              <span className="text-rose-700 font-semibold">▼ BEARISH</span>:
              expected to go down
            </li>
            <li>
              <span className="text-slate-600 font-semibold">● NEUTRAL</span>:
              minor move (|return| &lt; 0.5%)
            </li>
          </ul>
        </div>

        <div>
          <strong className="text-slate-900">magnitude</strong> — expected
          size of the move:
          <span className="ml-2 font-mono text-slate-600">
            LOW &lt; 0.5% &nbsp;|&nbsp; MEDIUM 0.5%–2% &nbsp;|&nbsp; HIGH &gt; 2%
          </span>
        </div>

        <div>
          <strong className="text-slate-900">confidence</strong> (0%–100%) —
          how sure the LLM is about <em>direction</em>, not magnitude. 50% is
          coin-flip; readings under 60% should be taken as low-conviction.
        </div>

        <div>
          <strong className="text-slate-900">Outcome columns</strong> — once
          the prediction window elapses, the validator computes:
          <ul className="list-disc list-inside mt-1 space-y-1 text-slate-600">
            <li>
              <span className="font-mono">TICKER</span>: actual % move of the
              predicted ticker over the window
            </li>
            <li>
              <span className="font-mono">SPY</span>: actual % move of S&amp;P
              500 baseline over the same window
            </li>
            <li>
              <span className="font-mono">EXCESS</span>: ticker − SPY
              (alpha). Positive = outperformed market, negative = lagged.
            </li>
            <li>
              <span className="font-mono">ALIGNED ✓ / ✗</span>:
              did the sign match? For COMPANY predictions we compare EXCESS;
              for MARKET predictions we compare TICKER directly (SPY-vs-SPY
              would always be 0 excess).
            </li>
          </ul>
        </div>

        <div>
          <strong className="text-slate-900">Windows</strong> — outcomes
          mature at three horizons after prediction time:
          <span className="ml-2 font-mono text-slate-600">1h · 24h · 7d</span>.
          Missing rows mean either the window hasn&apos;t elapsed yet, or the
          price snapshot needed to compute it isn&apos;t available.
        </div>
      </div>
    </details>
  );
}
