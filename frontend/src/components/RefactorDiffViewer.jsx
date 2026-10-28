import React, { useState } from 'react';
import { Columns, FileText, Check, Copy, FileCode, AlertTriangle, CheckCircle2, Activity, TrendingUp, TrendingDown, Minus } from 'lucide-react';

export const RefactorDiffViewer = ({ diffs = [], summary = '', turn = 1 }) => {
  const [viewMode, setViewMode] = useState('side-by-side'); // 'side-by-side' | 'unified'
  const [selectedFileIdx, setSelectedFileIdx] = useState(0);
  const [copiedFile, setCopiedFile] = useState(null);

  if (!diffs || diffs.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-center text-slate-500 text-xs font-mono">
        No diffs available for this refactoring turn.
      </div>
    );
  }

  const activeDiff = diffs[selectedFileIdx] || diffs[0];
  const syntaxVal = activeDiff.syntax_validation;
  const metrics = activeDiff.metrics_delta;
  const hasSyntaxErrors = syntaxVal && !syntaxVal.is_valid && syntaxVal.errors?.length > 0;
  const isAstValidated = syntaxVal && syntaxVal.is_valid && !syntaxVal.skipped;

  const handleCopy = (text, key) => {
    navigator.clipboard.writeText(text);
    setCopiedFile(key);
    setTimeout(() => setCopiedFile(null), 2000);
  };

  const fullPatch = diffs.map(d => d.diffCode || '').join('\n\n');

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
      {/* Header bar with summary & view mode toggles */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono text-[10px] font-bold">
              Turn {turn}
            </span>
            <h4 className="text-xs font-bold text-slate-100">
              Refactoring Proposal ({diffs.length} {diffs.length === 1 ? 'file' : 'files'} changed)
            </h4>
          </div>
          {summary && <p className="text-xs text-slate-400 mt-1">{summary}</p>}
        </div>

        <div className="flex items-center space-x-2">
          {/* View mode toggle */}
          <div className="flex items-center bg-slate-950 border border-slate-800 p-0.5 rounded-xl">
            <button
              onClick={() => setViewMode('side-by-side')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition ${
                viewMode === 'side-by-side'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Columns className="h-3.5 w-3.5" />
              <span>Side-by-Side</span>
            </button>
            <button
              onClick={() => setViewMode('unified')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition ${
                viewMode === 'unified'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              <span>Unified Patch</span>
            </button>
          </div>

          {/* Copy Full Patch */}
          <button
            onClick={() => handleCopy(fullPatch, 'all')}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-bold flex items-center space-x-1.5 transition border border-slate-700"
            title="Copy Full Unified Git Patch"
          >
            {copiedFile === 'all' ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            <span>{copiedFile === 'all' ? 'Copied All!' : 'Copy Patch'}</span>
          </button>
        </div>
      </div>

      {/* File Navigation Tabs (when multiple files changed) */}
      {diffs.length > 1 && (
        <div className="flex items-center space-x-2 overflow-x-auto pb-1 scrollbar-thin">
          {diffs.map((d, idx) => {
            const hasErr = d.syntax_validation && !d.syntax_validation.is_valid;
            return (
              <button
                key={idx}
                onClick={() => setSelectedFileIdx(idx)}
                className={`px-3 py-1.5 rounded-xl text-xs font-mono font-medium flex items-center space-x-1.5 transition whitespace-nowrap border ${
                  selectedFileIdx === idx
                    ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-300'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <FileCode className="h-3.5 w-3.5" />
                <span>{d.file.split('/').pop() || d.file}</span>
                {hasErr && (
                  <span className="h-2 w-2 rounded-full bg-amber-400 ring-2 ring-amber-400/30 ml-1" title="Syntax issue in this file" />
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* File Path Indicator & Syntax Validation Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono bg-slate-950 px-3.5 py-2.5 rounded-xl border border-slate-800">
        <div className="flex items-center space-x-2 truncate">
          <span className="text-cyan-400 font-bold truncate">{activeDiff.file}</span>
        </div>

        <div className="flex items-center space-x-3">
          {/* AST Syntax Validation Status Badge */}
          {hasSyntaxErrors ? (
            <span className="flex items-center space-x-1 bg-amber-500/10 text-amber-400 px-2.5 py-1 rounded-lg border border-amber-500/30 font-sans text-xs font-bold">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>{syntaxVal.errors.length} Syntax Issue(s) Detected</span>
            </span>
          ) : isAstValidated ? (
            <span className="flex items-center space-x-1 bg-emerald-500/10 text-emerald-400 px-2.5 py-1 rounded-lg border border-emerald-500/30 font-sans text-xs font-bold">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>AST Validated</span>
            </span>
          ) : null}

          {/* Per-File Copy */}
          <button
            onClick={() => handleCopy(activeDiff.diffCode || '', activeDiff.file)}
            className="text-slate-400 hover:text-slate-200 flex items-center space-x-1 text-[11px] transition"
          >
            {copiedFile === activeDiff.file ? (
              <>
                <Check className="h-3 w-3 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy File Diff</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* AST Code Health & Complexity Delta Metrics Card */}
      {metrics && (
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 space-y-2.5 font-mono text-xs shadow-inner">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-2">
            <div className="flex items-center space-x-2">
              <Activity className="h-4 w-4 text-cyan-400" />
              <span className="font-bold text-slate-200">AST Code Health Delta</span>
            </div>

            {/* Verdict Badge */}
            <div className="flex items-center space-x-1.5">
              {metrics.verdict === 'IMPROVED' ? (
                <span className="flex items-center space-x-1 bg-emerald-500/10 text-emerald-400 px-2.5 py-0.5 rounded-full border border-emerald-500/30 font-bold text-[11px]">
                  <TrendingDown className="h-3.5 w-3.5" />
                  <span>Health Improved (+{metrics.health_score_delta} pts)</span>
                </span>
              ) : metrics.verdict === 'COMPLEXITY_INCREASED' ? (
                <span className="flex items-center space-x-1 bg-rose-500/10 text-rose-400 px-2.5 py-0.5 rounded-full border border-rose-500/30 font-bold text-[11px]">
                  <TrendingUp className="h-3.5 w-3.5" />
                  <span>Complexity Increased ({metrics.health_score_delta} pts)</span>
                </span>
              ) : (
                <span className="flex items-center space-x-1 bg-slate-800 text-slate-300 px-2.5 py-0.5 rounded-full border border-slate-700 font-bold text-[11px]">
                  <Minus className="h-3.5 w-3.5" />
                  <span>Health Neutral</span>
                </span>
              )}
            </div>
          </div>

          {/* 4 Stat Badges Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-0.5 text-[11px]">
            {/* Cyclomatic Complexity */}
            <div className="bg-slate-900/90 border border-slate-800/80 rounded-lg p-2 flex flex-col justify-between">
              <span className="text-slate-400 text-[10px]">Complexity V(G)</span>
              <div className="flex items-baseline space-x-1.5 mt-1 font-bold">
                <span className="text-slate-400">{metrics.pre_refactor?.cyclomatic_complexity ?? 1}</span>
                <span className="text-slate-600">→</span>
                <span className="text-slate-100">{metrics.post_refactor?.cyclomatic_complexity ?? 1}</span>
                {metrics.deltas?.complexity !== 0 && (
                  <span className={`text-[10px] ml-auto ${metrics.deltas?.complexity < 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    ({metrics.deltas?.complexity > 0 ? `+${metrics.deltas?.complexity}` : metrics.deltas?.complexity})
                  </span>
                )}
              </div>
            </div>

            {/* Nesting Depth */}
            <div className="bg-slate-900/90 border border-slate-800/80 rounded-lg p-2 flex flex-col justify-between">
              <span className="text-slate-400 text-[10px]">Max Nesting</span>
              <div className="flex items-baseline space-x-1.5 mt-1 font-bold">
                <span className="text-slate-400">{metrics.pre_refactor?.max_nesting_depth ?? 0}</span>
                <span className="text-slate-600">→</span>
                <span className="text-slate-100">{metrics.post_refactor?.max_nesting_depth ?? 0}</span>
                {metrics.deltas?.nesting !== 0 && (
                  <span className={`text-[10px] ml-auto ${metrics.deltas?.nesting < 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    ({metrics.deltas?.nesting > 0 ? `+${metrics.deltas?.nesting}` : metrics.deltas?.nesting})
                  </span>
                )}
              </div>
            </div>

            {/* Parameter Count */}
            <div className="bg-slate-900/90 border border-slate-800/80 rounded-lg p-2 flex flex-col justify-between">
              <span className="text-slate-400 text-[10px]">Parameters</span>
              <div className="flex items-baseline space-x-1.5 mt-1 font-bold">
                <span className="text-slate-400">{metrics.pre_refactor?.param_count ?? 0}</span>
                <span className="text-slate-600">→</span>
                <span className="text-slate-100">{metrics.post_refactor?.param_count ?? 0}</span>
              </div>
            </div>

            {/* Executable LOC */}
            <div className="bg-slate-900/90 border border-slate-800/80 rounded-lg p-2 flex flex-col justify-between">
              <span className="text-slate-400 text-[10px]">Clean LOC</span>
              <div className="flex items-baseline space-x-1.5 mt-1 font-bold">
                <span className="text-slate-400">{metrics.pre_refactor?.loc ?? 0}</span>
                <span className="text-slate-600">→</span>
                <span className="text-slate-100">{metrics.post_refactor?.loc ?? 0}</span>
                {metrics.deltas?.loc !== 0 && (
                  <span className="text-[10px] ml-auto text-slate-400">
                    ({metrics.deltas?.loc > 0 ? `+${metrics.deltas?.loc}` : metrics.deltas?.loc})
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Syntax Error Summary Bar (renders when tree-sitter detects syntax problems) */}
      {hasSyntaxErrors && (
        <div className="bg-amber-950/40 border border-amber-500/30 rounded-xl px-4 py-3 text-xs text-amber-200 space-y-1.5 font-mono shadow-inner">
          <div className="flex items-center space-x-2 font-bold text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            <span>AST Syntax Warnings Detected in Proposed Change:</span>
          </div>
          <ul className="list-disc list-inside space-y-1 text-amber-300/90 pl-1 text-[11px]">
            {syntaxVal.errors.map((err, idx) => (
              <li key={idx}>
                Line {err.line}:{err.column} — <span className="font-bold text-amber-200">{err.type}</span> around{' '}
                <code className="bg-amber-900/60 text-amber-100 px-1.5 py-0.5 rounded border border-amber-500/30">
                  {err.snippet || 'EOF'}
                </code>{' '}
                ({err.symbol})
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* VIEW MODE 1: SIDE-BY-SIDE DUAL PANE */}
      {viewMode === 'side-by-side' ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 font-mono text-xs">
          {/* Left Pane: Original Code (Removed / Modified) */}
          <div className="bg-red-950/20 border border-red-500/30 rounded-xl overflow-hidden flex flex-col">
            <div className="bg-red-950/40 px-3 py-2 border-b border-red-500/20 flex items-center justify-between text-[11px] font-bold text-red-400">
              <span className="uppercase tracking-wider">// ORIGINAL SINK</span>
              <span className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 text-[10px]">BEFORE</span>
            </div>
            <div className="p-3 overflow-x-auto text-red-200 leading-relaxed font-mono flex-1 min-h-[140px] whitespace-pre">
              {activeDiff.old_code || '// No previous code removed'}
            </div>
          </div>

          {/* Right Pane: Proposed Refactored Code */}
          <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-xl overflow-hidden flex flex-col">
            <div className="bg-emerald-950/40 px-3 py-2 border-b border-emerald-500/20 flex items-center justify-between text-[11px] font-bold text-emerald-400">
              <span className="uppercase tracking-wider">// REFACTORED SOURCE</span>
              <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px]">AFTER</span>
            </div>
            <div className="p-3 overflow-x-auto text-emerald-200 leading-relaxed font-mono flex-1 min-h-[140px] whitespace-pre">
              {activeDiff.new_code || activeDiff.diffCode || '// Proposed replacement'}
            </div>
          </div>
        </div>
      ) : (
        /* VIEW MODE 2: SYNTAX-HIGHLIGHTED UNIFIED PATCH */
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs overflow-x-auto">
          <div className="space-y-0.5">
            {(activeDiff.diffCode || '').split('\n').map((line, lIdx) => {
              let lineStyle = 'text-slate-300';
              if (line.startsWith('---') || line.startsWith('+++')) {
                lineStyle = 'text-cyan-400 font-bold';
              } else if (line.startsWith('@@')) {
                lineStyle = 'text-indigo-400 bg-indigo-950/40 px-1 rounded block';
              } else if (line.startsWith('+')) {
                lineStyle = 'text-emerald-400 bg-emerald-950/30 px-1 rounded block';
              } else if (line.startsWith('-')) {
                lineStyle = 'text-red-400 bg-red-950/30 px-1 rounded block';
              }
              return (
                <div key={lIdx} className={`${lineStyle} whitespace-pre`}>
                  {line || ' '}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
