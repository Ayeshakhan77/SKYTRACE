import React, { useState } from 'react';
import { CURATED_TARGETS } from '../data/fixtures';
import { NormalizedObservation, TargetPreset } from '../types/observation';
import { prepareObservations, searchObservations } from '../services/api';

interface QueryConsoleProps {
  onObservationsPrepared: (
    prepared: NormalizedObservation[],
    searchContext: { targetName: string; ra: string; dec: string; isOffline: boolean }
  ) => void;
}

export default function QueryConsole({ onObservationsPrepared }: QueryConsoleProps) {
  const [selectedPresetId, setSelectedPresetId] = useState<string>('wise-0855');
  const [targetName, setTargetName] = useState<string>(CURATED_TARGETS[2].name);
  const [ra, setRa] = useState<string>(CURATED_TARGETS[2].ra);
  const [dec, setDec] = useState<string>(CURATED_TARGETS[2].dec);
  const [radiusDeg, setRadiusDeg] = useState<number>(CURATED_TARGETS[2].radiusDeg);

  // Default to Offline Fixture Mode so UI works standalone until live backend is connected
  const [useOfflineMode, setUseOfflineMode] = useState<boolean>(true);

  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [isPreparing, setIsPreparing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [truncated, setTruncated] = useState<boolean>(false);
  const [results, setResults] = useState<NormalizedObservation[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);

  const handleSelectPreset = (preset: TargetPreset) => {
    setSelectedPresetId(preset.id);
    setTargetName(preset.name);
    setRa(preset.ra);
    setDec(preset.dec);
    setRadiusDeg(preset.radiusDeg);
    setErrorMsg(null);
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!ra.trim() || !dec.trim()) {
      setErrorMsg('Both Right Ascension (RA) and Declination (Dec) are required.');
      return;
    }

    setIsSearching(true);
    try {
      const response = await searchObservations({
        targetName: targetName.trim() || 'Custom Sky Position',
        ra: ra.trim(),
        dec: dec.trim(),
        radiusDeg,
        useOfflineFallback: useOfflineMode,
      });

      setSearchId(response.searchId);
      setResults(response.observations);
      setTruncated(response.truncated);
      setSelectedKeys([]);
    } catch (err: any) {
      setErrorMsg(err.message || 'Archive search failed.');
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const toggleSelectObservation = (key: string) => {
    setErrorMsg(null);
    setSelectedKeys((prev) => {
      if (prev.includes(key)) {
        return prev.filter((k) => k !== key);
      }
      if (prev.length >= 2) {
        setErrorMsg('Maximum 2 observations can be selected per preparation request.');
        return prev;
      }
      return [...prev, key];
    });
  };

  const handlePrepare = async () => {
    const selectedObs = results.filter((obs) =>
      selectedKeys.includes(obs.backendSelectionKey)
    );
    if (selectedObs.length === 0) return;

    setIsPreparing(true);
    setErrorMsg(null);
    try {
      const prepared = await prepareObservations(selectedObs, useOfflineMode);
      onObservationsPrepared(prepared, {
        targetName: targetName || 'Custom Sky Position',
        ra,
        dec,
        isOffline: useOfflineMode,
      });
    } catch (err: any) {
      setErrorMsg(err.message || 'Observation preparation failed.');
    } finally {
      setIsPreparing(false);
    }
  };

  const activePreset = CURATED_TARGETS.find((t) => t.id === selectedPresetId);

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header + Mode Switch */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">Search & Target Selection</h2>
          <p className="text-sm text-gray-400">
            Query NASA/IPAC SPHEREx archive collections using curated presets or custom sky coordinates.
          </p>
        </div>

        {/* Live vs Offline Fixture Toggle */}
        <div className="flex items-center space-x-2 bg-cardBg border border-borderCol rounded-lg p-1.5">
          <button
            type="button"
            onClick={() => setUseOfflineMode(true)}
            className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
              useOfflineMode
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Offline Fixture (WISE 0855)
          </button>
          <button
            type="button"
            onClick={() => setUseOfflineMode(false)}
            className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
              !useOfflineMode
                ? 'bg-accentBlue text-white'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Live FastAPI Backend
          </button>
        </div>
      </div>

      {/* Curated Target Presets Bar */}
      <div className="bg-cardBg border border-borderCol rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono uppercase text-gray-400">
            Curated Target Presets (5 Official Targets)
          </span>
          <span className="text-[11px] font-mono text-gray-500">
            Frame: ICRS | Epoch: J2000
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {CURATED_TARGETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => handleSelectPreset(preset)}
              className={`px-3.5 py-2 rounded-lg text-xs font-medium border transition-all ${
                selectedPresetId === preset.id
                  ? 'bg-accentBlue/15 border-accentBlue text-white'
                  : 'bg-darkBg border-borderCol text-gray-400 hover:border-gray-600 hover:text-gray-200'
              }`}
            >
              {preset.name}
            </button>
          ))}
        </div>

        {activePreset && (
          <p className="text-xs text-gray-400 bg-darkBg/60 border border-borderCol/70 rounded-lg px-3 py-2">
            <span className="font-mono text-accentGlow mr-2">NOTE:</span>
            {activePreset.notes}
          </p>
        )}
      </div>

      {/* Search Form */}
      <form
        onSubmit={handleSearch}
        className="bg-cardBg border border-borderCol rounded-xl p-5 space-y-4"
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1">TARGET LABEL</label>
            <input
              type="text"
              value={targetName}
              onChange={(e) => {
                setTargetName(e.target.value);
                setSelectedPresetId('');
              }}
              placeholder="e.g., WISE 0855"
              className="w-full px-3 py-2 bg-darkBg border border-borderCol rounded-lg text-sm text-white focus:outline-none focus:border-accentBlue"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1">
              RIGHT ASCENSION (RA)
            </label>
            <input
              type="text"
              value={ra}
              onChange={(e) => setRa(e.target.value)}
              placeholder="08h 55m 10.8s"
              className="w-full px-3 py-2 bg-darkBg border border-borderCol rounded-lg text-sm font-mono text-white focus:outline-none focus:border-accentBlue"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1">
              DECLINATION (DEC)
            </label>
            <input
              type="text"
              value={dec}
              onChange={(e) => setDec(e.target.value)}
              placeholder="-07° 14′ 43″"
              className="w-full px-3 py-2 bg-darkBg border border-borderCol rounded-lg text-sm font-mono text-white focus:outline-none focus:border-accentBlue"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1">
              SEARCH RADIUS (DEG)
            </label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              max="2.0"
              value={radiusDeg}
              onChange={(e) => setRadiusDeg(parseFloat(e.target.value) || 0.05)}
              className="w-full px-3 py-2 bg-darkBg border border-borderCol rounded-lg text-sm font-mono text-white focus:outline-none focus:border-accentBlue"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2">
          <div className="text-xs font-mono text-gray-500">
            A preset represents a sky search position, not a confirmed object detection.
          </div>

          <button
            type="submit"
            disabled={isSearching}
            className="px-5 py-2.5 rounded-lg bg-accentBlue hover:bg-blue-600 disabled:opacity-50 text-sm font-semibold text-white transition-colors"
          >
            {isSearching ? 'Searching SPHEREx Archive...' : 'Search Observations'}
          </button>
        </div>
      </form>

      {/* Error / Warning Banners */}
      {errorMsg && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-xs font-mono text-red-300">
          ⚠️ {errorMsg}
        </div>
      )}

      {truncated && (
        <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-700/60 text-xs font-mono text-amber-300">
          ⚠️ Archive search results were truncated at the 500-row metadata limit. Narrow your search radius if needed.
        </div>
      )}

      {/* Search Results & Selection List */}
      {results.length > 0 && (
        <div className="bg-cardBg border border-borderCol rounded-xl p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-borderCol pb-3">
            <div>
              <h3 className="text-sm font-semibold text-white">
                Discovered SPHEREx Observations ({results.length})
              </h3>
              <p className="text-xs font-mono text-gray-400">
                SEARCH ID: {searchId} • Select 1 or 2 products to prepare for visual comparison
              </p>
            </div>

            <div className="flex items-center space-x-3">
              {selectedKeys.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedKeys([])}
                  className="px-3 py-2 text-xs font-mono text-gray-400 hover:text-white border border-borderCol rounded-lg"
                >
                  Clear Selection ({selectedKeys.length})
                </button>
              )}
              <button
                type="button"
                disabled={selectedKeys.length === 0 || isPreparing}
                onClick={handlePrepare}
                className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 disabled:opacity-40 text-xs font-semibold text-white transition-colors"
              >
                {isPreparing
                  ? 'Preparing Assets...'
                  : `Prepare Selected (${selectedKeys.length}/2) →`}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {results.map((obs) => {
              const isSelected = selectedKeys.includes(obs.backendSelectionKey);
              return (
                <div
                  key={obs.backendSelectionKey}
                  onClick={() => toggleSelectObservation(obs.backendSelectionKey)}
                  className={`cursor-pointer p-4 rounded-xl border transition-all ${
                    isSelected
                      ? 'bg-accentBlue/15 border-accentBlue'
                      : 'bg-darkBg border-borderCol hover:border-gray-600'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-mono font-bold text-accentGlow">
                      {obs.archiveObservationId || obs.sourceProductId}
                    </span>
                    <span
                      className={`text-[11px] font-mono px-2 py-0.5 rounded ${
                        isSelected
                          ? 'bg-accentBlue text-white'
                          : 'bg-borderCol text-gray-400'
                      }`}
                    >
                      {isSelected ? '✓ SELECTED' : 'CLICK TO SELECT'}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs font-mono text-gray-300 mt-3">
                    <div>
                      <span className="text-gray-500 block text-[10px]">OBSERVATION DATE</span>
                      {obs.observationTime
                        ? new Date(obs.observationTime).toUTCString().replace('GMT', 'UTC')
                        : 'Unavailable'}
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">WAVELENGTH / BAND</span>
                      {obs.wavelength ? `${obs.wavelength} µm` : 'N/A'} (
                      {obs.detector || 'Detector N/A'})
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">COLLECTION</span>
                      {obs.provenance.collection || 'SPHEREx'}
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">SELECTION KEY</span>
                      {obs.backendSelectionKey.slice(0, 12)}...
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}