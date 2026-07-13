import { HardDrive } from 'lucide-react';
import { useAppStore } from '../../lib/store';

export function CostComparison() {
  const savings = useAppStore((s) => s.savings);

  if (!savings || savings.total_tokens === 0) {
    return (
      <div className="hud-panel p-6">
        <h3 className="hud-label flex items-center gap-2 mb-4">
          <HardDrive size={12} style={{ color: 'var(--color-success)' }} />
          Local Inference
        </h3>
        <div className="h-48 flex items-center justify-center text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
          <span className="hud-mono">awaiting first inference…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="hud-panel p-6">
      <h3 className="hud-label flex items-center gap-2 mb-4">
        <HardDrive size={12} style={{ color: 'var(--color-success)' }} />
        Local Inference
      </h3>

      <div
        className="flex items-center gap-3 p-3 rounded-lg"
        style={{ background: 'var(--color-accent-subtle)', border: '1px solid var(--color-accent)' }}
      >
        <HardDrive size={18} style={{ color: 'var(--color-accent)' }} />
        <div className="flex-1">
          <div className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
            Your hardware
          </div>
          <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {savings.total_calls} requests &middot; {savings.total_tokens.toLocaleString()} tokens
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold" style={{ color: 'var(--color-success)' }}>
            ${savings.local_cost.toFixed(4)}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
            electricity only
          </div>
        </div>
      </div>

      <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--color-border)' }}>
        <p className="text-[10px] leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
          Prompt tokens: {savings.total_prompt_tokens.toLocaleString()} &middot; Completion tokens: {savings.total_completion_tokens.toLocaleString()}
        </p>
      </div>
    </div>
  );
}
