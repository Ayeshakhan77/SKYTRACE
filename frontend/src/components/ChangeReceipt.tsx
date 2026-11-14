import React, { useMemo } from 'react';
import {
  ChangeReceiptData,
  NormalizedObservation,
  ValidationStatus,
} from '../types/observation';

interface ChangeReceiptProps {
  observations: NormalizedObservation[];
  searchContext: {
    targetName: string;
    ra: string;
    dec: string;
    isOffline: boolean;
  };
  comparisonMode: 'single' | 'blink' | 'side_by_side';
}

export default function ChangeReceipt({
  observations,
  searchContext,
  comparisonMode,
}: ChangeReceiptProps) {
  const receipt: ChangeReceiptData = useMemo(() => {
    const hasProvenance = observations.length > 0;
    return {
      receiptId: `RCPT-${Date.now().toString(36).toUpperCase()}`,
      specVersion: 'SKYTRACE-RCPT-1.0',
      generatedAt: new Date().toISOString(),
      // Per Section 7: Receipt is "ready" when observations & provenance are available,
      // even while scientific validation checks remain "not_assessed".
      readinessStatus: hasProvenance ? 'ready' : 'partial',
      targetName: searchContext.targetName || 'Unspecified Target',
      requestedRa: searchContext.ra || 'N/A',
      requestedDec: searchContext.dec || 'N/A',
      comparisonMode,
      observations,
      validationChecks: {
        identityAssessment: 'not_assessed',
        wavelengthCompatibility: 'not_assessed',
        calibrationCompatibility: 'not_assessed',
        wcsRegistration: 'not_assessed',
        psfMatching: 'not_assessed',
        photometricValidation: 'not_assessed',
        dataQualityReview: 'not_assessed',
      },
    };
  }, [observations, searchContext, comparisonMode]);

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify(receipt, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${receipt.receiptId}_change_receipt.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const renderStatusBadge = (status: ValidationStatus) => {
    const styles: Record<ValidationStatus, string> = {
      not_assessed: 'bg-amber-950/60 text-amber-300 border-amber-700/60',
      pending: 'bg-blue-950/60 text-blue-300 border-blue-700/60',
      passed: 'bg-emerald-950/60 text-emerald-300 border-emerald-700/60',
      failed: 'bg-red-950/60 text-red-300 border-red-700/60',
      not_applicable: 'bg-gray-800 text-gray-400 border-gray-700',
    };
    return (
      <span
        className={`px-2.5 py-0.5 rounded text-[11px] font-mono uppercase border ${styles[status]}`}
      >
        {status.replace('_', ' ')}
      </span>
    );
  };

  if (observations.length === 0) {
    return (
      <div className="bg-cardBg border border-borderCol rounded-xl p-10 text-center space-y-3 max-w-4xl">
        <p className="text-sm font-mono text-gray-300">NO OBSERVATIONS SELECTED FOR RECEIPT</p>
        <p className="text-xs text-gray-500">
          Search and prepare 1 or 2 SPHEREx observations first to generate a transparent Change Receipt.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Top Header & JSON Export */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">
            SKYTRACE Change Receipt & Provenance Ledger
          </h2>
          <p className="text-xs text-gray-400">
            Transparent audit record distinguishing visual exploration from scientifically validated findings[cite: 2].
          </p>
        </div>

        <button
          type="button"
          onClick={handleDownloadJson}
          className="px-4 py-2 rounded-lg bg-accentBlue hover:bg-blue-600 text-xs font-semibold text-white transition-colors"
        >
          Export Receipt JSON ↓
        </button>
      </div>

      {/* Section A & B: Receipt Identity + Search & Comparison Context */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-cardBg border border-borderCol rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-borderCol pb-2">
            <span className="text-xs font-mono font-bold text-accentGlow">
              A. RECEIPT IDENTITY
            </span>
            <span className="px-2.5 py-0.5 rounded text-[11px] font-mono bg-emerald-950/60 text-emerald-300 border border-emerald-700/60">
              RECEIPT {receipt.readinessStatus.toUpperCase()}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs font-mono">
            <div>
              <span className="text-gray-500 block text-[10px]">RECEIPT ID</span>
              <span className="text-white">{receipt.receiptId}</span>
            </div>
            <div>
              <span className="text-gray-500 block text-[10px]">SPEC VERSION</span>
              <span className="text-gray-300">{receipt.specVersion}</span>
            </div>
            <div className="col-span-2">
              <span className="text-gray-500 block text-[10px]">GENERATED TIMESTAMP</span>
              <span className="text-gray-300">{receipt.generatedAt}</span>
            </div>
          </div>
        </div>

        <div className="bg-cardBg border border-borderCol rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-borderCol pb-2">
            <span className="text-xs font-mono font-bold text-accentGlow">
              B & D. SEARCH & COMPARISON MODE
            </span>
            <span className="text-[11px] font-mono text-gray-400">
              {searchContext.isOffline ? 'OFFLINE FIXTURE' : 'LIVE ARCHIVE'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs font-mono">
            <div>
              <span className="text-gray-500 block text-[10px]">TARGET / POSITION</span>
              <span className="text-white">{receipt.targetName}</span>
            </div>
            <div>
              <span className="text-gray-500 block text-[10px]">ACTIVE VIEW MODE</span>
              <span className="text-amber-300 uppercase">
                Visual {receipt.comparisonMode.replace(/_/g, ' ')}
              </span>
            </div>
            <div>
              <span className="text-gray-500 block text-[10px]">RA / DEC (ICRS J2000)</span>
              <span className="text-gray-300">
                {receipt.requestedRa}, {receipt.requestedDec}
              </span>
            </div>
            <div>
              <span className="text-gray-500 block text-[10px]">SCIENTIFIC VALIDATION</span>
              <span className="text-amber-400">NOT PERFORMED</span>
            </div>
          </div>
        </div>
      </div>

      {/* Section C: Observation Provenance */}
      <div className="bg-cardBg border border-borderCol rounded-xl p-5 space-y-4">
        <h3 className="text-xs font-mono font-bold text-accentGlow border-b border-borderCol pb-2">
          C. OBSERVATION PROVENANCE ({observations.length} SELECTED)
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {observations.map((obs, idx) => (
            <div
              key={obs.backendSelectionKey}
              className="p-4 rounded-lg bg-darkBg border border-borderCol space-y-2.5 text-xs font-mono"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-white">
                  #{idx + 1}: {obs.archiveObservationId || obs.sourceProductId}
                </span>
                <span className="text-[11px] text-gray-400">
                  {obs.provenance.collection || 'SPHEREx'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div>
                  <span className="text-gray-500 block">TIMESTAMP (UTC)</span>
                  <span className="text-gray-200">{obs.observationTime || 'Unavailable'}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">WAVELENGTH / DETECTOR</span>
                  <span className="text-gray-200">
                    {obs.wavelength ? `${obs.wavelength} µm` : 'N/A'} • {obs.detector || 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block">BACKEND SELECTION KEY</span>
                  <span className="text-gray-400 break-all">{obs.backendSelectionKey}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">PROCESSING VERSION</span>
                  <span className="text-gray-400">
                    {obs.processingVersion ?? 'Unavailable'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block">PREVIEW / FITS ASSETS</span>
                  <span className="text-gray-200">
                    Preview: {obs.previewStatus} | FITS: {obs.fitsStatus}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block">CHECKSUM</span>
                  <span className="text-gray-400 break-all">
                    {obs.provenance.checksum || 'Unavailable'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Section E: Scientific Validation Checks */}
      <div className="bg-cardBg border border-borderCol rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-borderCol pb-2">
          <h3 className="text-xs font-mono font-bold text-accentGlow">
            E. SCIENTIFIC VALIDATION CHECKS
          </h3>
          <span className="text-[11px] font-mono text-gray-400">
            Unassessed checks are explicitly preserved—never marked as passed[cite: 2].
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { label: 'Identity Assessment', status: receipt.validationChecks.identityAssessment },
            {
              label: 'Wavelength Compatibility',
              status: receipt.validationChecks.wavelengthCompatibility,
            },
            {
              label: 'Calibration Compatibility',
              status: receipt.validationChecks.calibrationCompatibility,
            },
            { label: 'WCS Registration', status: receipt.validationChecks.wcsRegistration },
            { label: 'PSF Matching', status: receipt.validationChecks.psfMatching },
            {
              label: 'Photometric Validation',
              status: receipt.validationChecks.photometricValidation,
            },
            { label: 'Data Quality Review', status: receipt.validationChecks.dataQualityReview },
          ].map((item) => (
            <div
              key={item.label}
              className="p-3 rounded-lg bg-darkBg border border-borderCol flex flex-col justify-between gap-2"
            >
              <span className="text-xs text-gray-300">{item.label}</span>
              <div>{renderStatusBadge(item.status)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Section F & G: Findings vs. Limitations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-cardBg border border-borderCol rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-mono font-bold text-emerald-400 border-b border-borderCol pb-2">
            F. WHAT THIS EVIDENCE SUPPORTS (FINDINGS)
          </h3>
          <ul className="space-y-2 text-xs text-gray-300 list-disc pl-4">
            <li>
              <strong>Visual Exploration:</strong> Multi-epoch SPHEREx cutouts were retrieved and inspected chronologically via {receipt.comparisonMode.replace('_', ' ')} mode[cite: 2].
            </li>
            <li>
              <strong>Validated Scientific Findings:</strong> None yet. No scientifically validated difference product exists for this selection[cite: 2].
            </li>
            <li>
              <strong>Candidate Status:</strong> Any apparent visual variation remains an unverified candidate subject to instrumental and wavelength differences[cite: 2].
            </li>
          </ul>
        </div>

        <div className="bg-red-950/20 border border-red-900/50 rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-mono font-bold text-red-400 border-b border-red-900/40 pb-2">
            G. SCIENTIFIC LIMITATIONS & SAFEGUARDS
          </h3>
          <ul className="space-y-2 text-xs text-gray-300 list-disc pl-4">
            <li>
              <strong>Fixed-Coordinate Search:</strong> Searching a sky position does not establish object identity or confirm proper motion[cite: 2].
            </li>
            <li>
              <strong>Per-Image Scaling:</strong> Preview images use independent display scaling and cannot support numerical brightness comparisons[cite: 2].
            </li>
            <li>
              <strong>Band & Calibration Differences:</strong> Visual differences may arise from wavelength, detector, calibration, or WCS alignment offsets[cite: 2].
            </li>
            <li>
              <strong>No Discovery Claim:</strong> A visual candidate is not a confirmed astronomical discovery[cite: 2].
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}