// One-time read for visitors trying to make sense of the prediction rows.
// Lives as a collapsible <details> so it doesn't dominate the page once
// understood. Place it just above the predictions list on event detail.

export function PredictionLegend() {
  return (
    <details className="border border-term-border bg-term-panel">
      <summary className="cursor-pointer px-4 py-2.5 font-mono text-xs font-bold text-term-muted uppercase tracking-[0.2em] select-none flex items-center gap-2">
        <span className="text-term-amber">ⓘ</span>
        How to read these predictions
      </summary>
      <div className="px-4 pb-4 text-xs text-term-text/85 space-y-3 leading-relaxed">
        <div>
          <strong className="text-term-text">kind</strong> — the prediction scope.
          <ul className="list-disc list-inside mt-1 space-y-1 text-term-muted">
            <li>
              <span className="font-semibold text-src-fred">MARKET</span>:
              broad-index call. The analyzer always emits SPY + QQQ for every event.
            </li>
            <li>
              <span className="font-semibold text-term-amber">COMPANY</span>:
              single-stock call. Only emitted for company-specific events
              (8-K, earnings).
            </li>
          </ul>
        </div>

        <div>
          <strong className="text-term-text">direction</strong> — expected
          price action over the next 24h.
          <ul className="list-disc list-inside mt-1 space-y-1 text-term-muted">
            <li>
              <span className="text-term-up font-semibold">▲ BULLISH</span>:
              expected to go up
            </li>
            <li>
              <span className="text-term-down font-semibold">▼ BEARISH</span>:
              expected to go down
            </li>
            <li>
              <span className="text-term-muted font-semibold">● NEUTRAL</span>:
              minor move (|return| &lt; 0.5%)
            </li>
          </ul>
        </div>

        <div>
          <strong className="text-term-text">magnitude</strong> — expected
          size of the move:
          <span className="ml-2 font-mono text-term-muted">
            LOW &lt; 0.5% &nbsp;|&nbsp; MEDIUM 0.5%–2% &nbsp;|&nbsp; HIGH &gt; 2%
          </span>
        </div>

        <div>
          <strong className="text-term-text">confidence</strong> (0%–100%) —
          how sure the LLM is about <em>direction</em>, not magnitude. 50% is
          coin-flip; readings under 60% should be taken as low-conviction.
        </div>

        <div>
          <strong className="text-term-text">Outcome columns</strong> — once
          the prediction window elapses, the validator computes:
          <ul className="list-disc list-inside mt-1 space-y-1 text-term-muted">
            <li>
              <span className="font-mono">TICKER RETURN</span>: actual % move
              of the predicted ticker over the window.
            </li>
            <li>
              <span className="font-mono">ALIGNED ✓ / ✗</span>:
              did the actual move match the prediction?
              <ul className="list-disc list-inside ml-4 mt-1 text-term-dim">
                <li>BULLISH ✓ when return &gt; +0.5%</li>
                <li>BEARISH ✓ when return &lt; −0.5%</li>
                <li>NEUTRAL ✓ when |return| &lt; 0.5%</li>
              </ul>
            </li>
          </ul>
        </div>

        <div>
          <strong className="text-term-text">Windows</strong> — outcomes
          mature at two horizons after prediction time:
          <span className="ml-2 font-mono text-term-muted">24h · 7d</span>.
          Missing rows mean either the window hasn&apos;t elapsed yet, or the
          price snapshot needed to compute it isn&apos;t available.
        </div>
      </div>
    </details>
  );
}
