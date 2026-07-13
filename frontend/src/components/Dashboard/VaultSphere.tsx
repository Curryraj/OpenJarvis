// frontend/src/components/Dashboard/VaultSphere.tsx
import { useEffect, useRef } from 'react';
import { Orbit } from 'lucide-react';
import { useAppStore } from '../../lib/store';

const IDLE_PARTICLE_COUNT = 180;
const MAX_PARTICLE_COUNT = 2000;
const MIN_PARTICLE_COUNT = 60;

interface Particle {
  theta: number; // longitude
  phi: number; // latitude
  radiusJitter: number;
}

function particleCountFor(nodeCount: number): number {
  if (nodeCount <= 0) return IDLE_PARTICLE_COUNT;
  return Math.min(MAX_PARTICLE_COUNT, Math.max(MIN_PARTICLE_COUNT, nodeCount * 4));
}

function makeParticles(count: number): Particle[] {
  const particles: Particle[] = [];
  for (let i = 0; i < count; i++) {
    particles.push({
      theta: Math.random() * Math.PI * 2,
      phi: Math.acos(2 * Math.random() - 1),
      radiusJitter: 0.85 + Math.random() * 0.15,
    });
  }
  return particles;
}

export function VaultSphere() {
  const vaultStats = useAppStore((s) => s.vaultStats);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const particlesRef = useRef<Particle[]>(makeParticles(IDLE_PARTICLE_COUNT));
  const rotationRef = useRef(0);

  const nodeCount = vaultStats?.node_count ?? 0;

  useEffect(() => {
    particlesRef.current = makeParticles(particleCountFor(nodeCount));
  }, [nodeCount]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const styles = getComputedStyle(canvas);
    const accentColor = styles.getPropertyValue('--color-accent').trim() || '#c026d3';

    let frameId: number;
    const size = 220;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const render = () => {
      ctx.clearRect(0, 0, size, size);
      const cx = size / 2;
      const cy = size / 2;
      const radius = size * 0.38;

      for (const p of particlesRef.current) {
        const theta = p.theta + rotationRef.current;
        const x = Math.sin(p.phi) * Math.cos(theta);
        const y = Math.cos(p.phi);
        const z = Math.sin(p.phi) * Math.sin(theta);

        // Simple orthographic-ish projection with z used for depth shading.
        const px = cx + x * radius * p.radiusJitter;
        const py = cy + y * radius * p.radiusJitter;
        const depth = (z + 1) / 2; // 0..1

        ctx.beginPath();
        ctx.arc(px, py, 0.6 + depth * 1.1, 0, Math.PI * 2);
        ctx.fillStyle = accentColor;
        ctx.globalAlpha = 0.15 + depth * 0.55;
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (!prefersReducedMotion) {
        rotationRef.current += 0.0015;
      }
      frameId = requestAnimationFrame(render);
    };

    frameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frameId);
  }, []);

  return (
    <div className="hud-panel p-6">
      <h3 className="hud-label flex items-center gap-2 mb-4">
        <Orbit size={12} style={{ color: 'var(--color-accent)' }} />
        Vault
      </h3>
      <div className="flex items-center gap-8">
        <canvas
          ref={canvasRef}
          style={{ filter: `drop-shadow(0 0 24px var(--color-accent-glow))` }}
        />
        <div className="flex flex-col gap-4">
          <div>
            <div className="hud-label mb-1">Notes</div>
            <div className="text-lg font-semibold hud-mono" style={{ color: 'var(--color-text)' }}>
              {vaultStats ? vaultStats.node_count.toLocaleString() : '—'}
            </div>
          </div>
          <div>
            <div className="hud-label mb-1">Domains</div>
            <div className="text-lg font-semibold hud-mono" style={{ color: 'var(--color-text)' }}>
              {vaultStats ? vaultStats.domain_count.toLocaleString() : '—'}
            </div>
          </div>
          <div>
            <div className="hud-label mb-1">Last updated</div>
            <div className="text-sm hud-mono" style={{ color: 'var(--color-text-secondary)' }}>
              {vaultStats?.last_updated
                ? new Date(vaultStats.last_updated).toLocaleString()
                : '—'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
