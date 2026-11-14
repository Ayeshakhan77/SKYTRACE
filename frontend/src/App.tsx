import React, { useState } from 'react';
import QueryConsole from './components/QueryConsole';
import AssetViewer from './components/AssetViewer';
import ChangeReceipt from './components/ChangeReceipt';
import { NormalizedObservation } from './types/observation';

type ActiveTab = 'search' | 'viewer' | 'receipt';

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('search');
  const [preparedObservations, setPreparedObservations] = useState<NormalizedObservation[]>([]);
  const [comparisonMode, setComparisonMode] = useState<'single' | 'blink' | 'side_by_side'>('blink');
  const [searchContext, setSearchContext] = useState({
    targetName: 'WISE 0855',
    ra: '08h 55m 10.8s',
    dec: '-07° 14′ 43″',
    isOffline: true,
  });

  const handleObservationsPrepared = (
    prepared: NormalizedObservation[],
    context: { targetName: string; ra: string; dec: string; isOffline: boolean }
  ) => {
    setPreparedObservations(prepared);
    setSearchContext(context);
    // Automatically default to blink mode if 2 observations are prepared, otherwise single
    setComparisonMode(prepared.length >= 2 ? 'blink' : 'single');
    setActiveTab('viewer');
  };

  return (
    <div className="min-h-screen bg-darkBg text-gray-100 flex flex-col">
      {/* Top Header Bar */}
      <header className="bg-cardBg border-b border-borderCol px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-accentBlue flex items-center justify-center font-mono font-bold text-white text-sm">
            ST
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-bold tracking-wide text-white">SKYTRACE</h1>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accentBlue/20 text-accentGlow border border-accentBlue/40">
                SPHEREx EXPLORER
              </span>
            </div>
            <p className="text-xs text-gray-400">
              The changing infrared sky, made explorable.
            </p>
          </div>
        </div>

        {/* Navigation Stepper Tabs */}
        <nav className="flex items-center space-x-2 bg-darkBg p-1 rounded-xl border border-borderCol">
          <button
            type="button"
            onClick={() => setActiveTab('search')}
            className={`px-4 py-2 rounded-lg text-xs font-mono transition-colors ${
              activeTab === 'search'
                ? 'bg-accentBlue text-white font-semibold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            1. Search & Select
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('viewer')}
            className={`px-4 py-2 rounded-lg text-xs font-mono transition-colors flex items-center space-x-1.5 ${
              activeTab === 'viewer'
                ? 'bg-accentBlue text-white font-semibold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span>2. Observation Viewer</span>
            {preparedObservations.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-black/40 text-[10px]">
                {preparedObservations.length}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('receipt')}
            className={`px-4 py-2 rounded-lg text-xs font-mono transition-colors ${
              activeTab === 'receipt'
                ? 'bg-accentBlue text-white font-semibold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            3. Change Receipt
          </button>
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-6 md:p-8 flex justify-center">
        <div className="w-full max-w-6xl">
          {activeTab === 'search' && (
            <QueryConsole onObservationsPrepared={handleObservationsPrepared} />
          )}

          {activeTab === 'viewer' && (
            <AssetViewer
              observations={preparedObservations}
              comparisonMode={comparisonMode}
              onComparisonModeChange={setComparisonMode}
              onOpenReceipt={() => setActiveTab('receipt')}
            />
          )}

          {activeTab === 'receipt' && (
            <ChangeReceipt
              observations={preparedObservations}
              searchContext={searchContext}
              comparisonMode={comparisonMode}
            />
          )}
        </div>
      </main>

      {/* Scientific Footer */}
      <footer className="border-t border-borderCol bg-cardBg/50 px-6 py-3 text-[11px] font-mono text-gray-500 flex flex-wrap items-center justify-between gap-2">
        <span>NASA Space Apps Challenge 2026 • Planet X & SPHEREx</span>
        <span>
          Visual exploration tool only — unassessed checks do not constitute scientific discovery claims[cite: 2].
        </span>
      </footer>
    </div>
  );
}