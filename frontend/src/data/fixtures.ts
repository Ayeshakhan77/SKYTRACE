import { TargetPreset } from '../types/observation';

export const CURATED_TARGETS: TargetPreset[] = [
  {
    id: 'barnards-star',
    name: "Barnard's Star",
    ra: '17h 57m 48.5s',
    dec: '+04° 41′ 36″',
    epoch: 'J2000',
    frame: 'ICRS',
    radiusDeg: 0.05,
    notes: 'High proper-motion red dwarf; verify multi-epoch SPHEREx coverage.',
  },
  {
    id: 'epsilon-indi-b',
    name: 'Epsilon Indi B',
    ra: '22h 04m 10.5s',
    dec: '-56° 46′ 58″',
    epoch: 'J2000',
    frame: 'ICRS',
    radiusDeg: 0.05,
    notes: 'Nearby brown dwarf binary system; inspect infrared band compatibility.',
  },
  {
    id: 'wise-0855',
    name: 'WISE 0855',
    ra: '08h 55m 10.8s',
    dec: '-07° 14′ 43″',
    epoch: 'J2000',
    frame: 'ICRS',
    radiusDeg: 0.05,
    notes: 'Coldest known Y-dwarf; includes cached QR2 D1 offline UI fixture (May 2025 / May 2026).',
  },
  {
    id: 'rw-aurigae',
    name: 'RW Aurigae',
    ra: '05h 07m 49.6s',
    dec: '+30° 24′ 05″',
    epoch: 'J2000',
    frame: 'ICRS',
    radiusDeg: 0.05,
    notes: 'Variable T Tauri star system; check spectral and detector consistency.',
  },
  {
    id: 'r-draconis',
    name: 'R Draconis',
    ra: '16h 32m 40.2s',
    dec: '+66° 45′ 18″',
    epoch: 'J2000',
    frame: 'ICRS',
    radiusDeg: 0.05,
    notes: 'Mira-type variable star; evaluate chronological separation across archive releases.',
  },
];

// Real cached WISE 0855 QR2/D1 cutout records, copied verbatim from the backend's
// examples/cache/cutouts/*/record.json (retrieved from IRSA on 3 Nov 2026).
// Previews are the backend-generated PNGs, served from frontend/public/fixtures/.
// Use for offline UI and Change Receipt testing only — NOT evidence of change:
// different processing versions (v20 vs v24), different local wavelengths,
// per-image display scaling, alignment/PSF/photometry not assessed.
import record2025 from './records/e3a440b1023a5200908226705840183d.json';
import record2026 from './records/a73d0dc77ac55c24b369e1a0e88c6edf.json';

export const WISE_0855_FIXTURE_RECORDS: any[] = [record2025, record2026];
export const FIXTURE_PREVIEW_PATH = (cutoutId: string) => `/fixtures/${cutoutId}.png`;
