import { useEffect } from 'react';
import { EnergyDashboard } from '../components/Dashboard/EnergyDashboard';
import { CostComparison } from '../components/Dashboard/CostComparison';
import { VaultSphere } from '../components/Dashboard/VaultSphere';
import { TraceDebugger } from '../components/Dashboard/TraceDebugger';
import { fetchVaultStats } from '../lib/api';
import { useAppStore } from '../lib/store';

export function DashboardPage() {
  const now = new Date();
  const stamp = now.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  const setVaultStats = useAppStore((s) => s.setVaultStats);

  useEffect(() => {
    fetchVaultStats()
      .then(setVaultStats)
      .catch(() => setVaultStats(null));
  }, [setVaultStats]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10">
      <div className="max-w-5xl mx-auto">
        <header className="mb-6">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
              System Overview
            </h1>
            <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              {stamp}
            </div>
          </div>
          <p className="text-sm mt-2 max-w-2xl" style={{ color: 'var(--color-text-secondary)' }}>
            Live telemetry for the on-device inference engine — power draw, token throughput, and local compute usage.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <EnergyDashboard />
          <CostComparison />
        </div>

        <div className="mb-4">
          <VaultSphere />
        </div>

        <TraceDebugger />
      </div>
    </div>
  );
}
