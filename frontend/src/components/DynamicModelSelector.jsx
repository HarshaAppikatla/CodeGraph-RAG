import React, { useState, useRef, useEffect } from 'react';
import { 
  Zap, 
  Cpu, 
  Brain, 
  Sparkles, 
  ChevronDown, 
  Check, 
  Key, 
  SlidersHorizontal,
  Lock
} from 'lucide-react';
import { getKeyStatus, getDiscoveredModels } from '../services/api';

export const AVAILABLE_MODELS = [
  {
    id: 'gemini-2.0-flash',
    name: 'Gemini 2.0 Flash',
    provider: 'gemini',
    tier: 'Fast Reasoning',
    description: 'Next-gen multimodal, low latency & thinking capabilities',
    recommended: true,
  },
  {
    id: 'gemini-2.5-flash',
    name: 'Gemini 2.5 Flash',
    provider: 'gemini',
    tier: 'Production',
    description: 'Optimal latency-to-quality ratio for codebase analysis',
  },
  {
    id: 'gemini-1.5-pro',
    name: 'Gemini 1.5 Pro',
    provider: 'gemini',
    tier: 'Deep Pro',
    description: 'Extended context window for comprehensive multi-file ASTs',
  },
  {
    id: 'claude-3-7-sonnet',
    name: 'Claude 3.7 Sonnet',
    provider: 'anthropic',
    tier: 'Hybrid Thinking',
    description: 'State-of-the-art code refactoring and hybrid reasoning',
  },
  {
    id: 'claude-3-5-sonnet',
    name: 'Claude 3.5 Sonnet',
    provider: 'anthropic',
    tier: 'Coding Expert',
    description: 'Industry benchmark for precise syntax and diff generation',
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    provider: 'openai',
    tier: 'Flagship',
    description: 'High-speed reasoning across complex dependency graphs',
  },
  {
    id: 'o3-mini',
    name: 'o3-mini',
    provider: 'openai',
    tier: 'Reasoning',
    description: 'STEM & code specialized reasoning engine',
  },
  {
    id: 'deepseek-r1',
    name: 'DeepSeek R1',
    provider: 'deepseek',
    tier: 'Open Reasoning',
    description: 'Open-weights reasoning model with chain-of-thought insights',
  },
  {
    id: 'groq/openai/gpt-oss-120b',
    name: 'GPT-OSS 120B (Groq)',
    provider: 'groq',
    tier: 'Flagship Open-Weights',
    description: '120B open weights reasoning running on ultra-fast Groq LPUs',
    recommended: true,
  },
  {
    id: 'groq/qwen/qwen3.8-27b',
    name: 'Qwen 3.8 27B',
    provider: 'groq',
    tier: 'Code Expert',
    description: 'High-precision code comprehension and AST reasoning on Groq LPUs',
  },
  {
    id: 'groq/openai/gpt-oss-20b',
    name: 'GPT-OSS 20B (Groq)',
    provider: 'groq',
    tier: 'Ultra Fast',
    description: 'Ultra-fast low-latency inference on Groq LPUs',
  },
  {
    id: 'groq/llama-3.3-70b-versatile',
    name: 'Llama 3.3 70B',
    provider: 'groq',
    tier: 'Groq LPU Speed',
    description: 'Sub-second AST analysis powered by Groq LPU inference engine',
  },
  {
    id: 'groq/allam-2-7b',
    name: 'Allam 2 7B',
    provider: 'groq',
    tier: 'Fast Reasoning',
    description: 'Lightweight multilingual open weights reasoning on Groq LPUs',
  },
];

export const THINKING_LEVELS = [
  { id: 'low', label: 'Low', budget: '1,024 tokens', desc: 'Fast, concise answers' },
  { id: 'medium', label: 'Medium', budget: '4,096 tokens', desc: 'Balanced reasoning & AST trace' },
  { id: 'high', label: 'High', budget: '8,192 tokens', desc: 'Exhaustive architectural analysis' },
];

const getProviderIcon = (provider) => {
  switch (provider) {
    case 'gemini':
      return <Zap className="w-3.5 h-3.5 text-amber-400" />;
    case 'anthropic':
      return <Sparkles className="w-3.5 h-3.5 text-orange-400" />;
    case 'openai':
      return <Cpu className="w-3.5 h-3.5 text-emerald-400" />;
    case 'deepseek':
      return <Brain className="w-3.5 h-3.5 text-blue-400" />;
    case 'groq':
      return <Zap className="w-3.5 h-3.5 text-rose-400" />;
    default:
      return <Zap className="w-3.5 h-3.5 text-cyan-400" />;
  }
};

const getProviderBadge = (provider) => {
  switch (provider) {
    case 'gemini':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
    case 'anthropic':
      return 'bg-orange-500/10 text-orange-400 border-orange-500/30';
    case 'openai':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    case 'deepseek':
      return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
    case 'groq':
      return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
    default:
      return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30';
  }
};

export default function DynamicModelSelector({
  selectedModel = AVAILABLE_MODELS[0],
  onSelectModel,
  thinkingLevel = 'medium',
  onSelectThinkingLevel,
  onOpenKeyModal,
  onOpenKeyVault,
  availableModels = AVAILABLE_MODELS,
  keyStatus: externalKeyStatus,
  onKeyStatusRefreshed,
}) {
  const [internalKeyStatus, setInternalKeyStatus] = useState({ gemini: true });
  const [loading, setLoading] = useState(true);
  const [discoveredModels, setDiscoveredModels] = useState([]);
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [isThinkingDropdownOpen, setIsThinkingDropdownOpen] = useState(false);
  const [filterProvider, setFilterProvider] = useState('all');

  const modelDropdownRef = useRef(null);
  const thinkingDropdownRef = useRef(null);

  // Merge external and internal key status
  const keyStatus = externalKeyStatus || internalKeyStatus;

  // Compute active model registry: dynamically discovered models take precedence over static list
  const effectiveModels = (discoveredModels && discoveredModels.length > 0)
    ? discoveredModels
    : (availableModels || AVAILABLE_MODELS);

  const refreshKeys = async () => {
    try {
      const res = await getKeyStatus();
      if (res) {
        setInternalKeyStatus(res);
        onKeyStatusRefreshed?.(res);
      }
    } catch (err) {
      console.warn("Key status check notice:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchLiveModels = async () => {
    try {
      const live = await getDiscoveredModels();
      if (live && Array.isArray(live) && live.length > 0) {
        setDiscoveredModels(live);
      }
    } catch (err) {
      console.warn("Live models query notice:", err);
    }
  };

  useEffect(() => {
    refreshKeys();
    fetchLiveModels();
  }, []);

  // Re-fetch live models whenever keyStatus changes (e.g. key added or deleted)
  useEffect(() => {
    fetchLiveModels();
  }, [keyStatus]);

  // Helper: Determine if model provider is unlocked
  const isUnlocked = (model) => {
    const provider = (model?.provider || 'gemini').toLowerCase();
    return Boolean(keyStatus[provider]);
  };

  // Auto-fallback execution when key status changes or model is locked
  useEffect(() => {
    if (!loading && selectedModel && !isUnlocked(selectedModel)) {
      const fallback = effectiveModels.find(m => isUnlocked(m)) || effectiveModels[0];
      if (fallback && fallback.id !== selectedModel.id) {
        onSelectModel?.(fallback);
      }
    }
  }, [keyStatus, loading, selectedModel, effectiveModels]);

  const triggerOpenVault = (provider) => {
    setIsModelDropdownOpen(false);
    const targetProvider = provider || 'gemini';
    if (onOpenKeyVault) {
      onOpenKeyVault(targetProvider);
    } else if (onOpenKeyModal) {
      onOpenKeyModal(targetProvider);
    }
  };

  // Close dropdowns when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(event.target)) {
        setIsModelDropdownOpen(false);
      }
      if (thinkingDropdownRef.current && !thinkingDropdownRef.current.contains(event.target)) {
        setIsThinkingDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentModel = effectiveModels.find(m => m.id === selectedModel?.id) || selectedModel || effectiveModels[0];
  const currentThinking = THINKING_LEVELS.find(t => t.id === thinkingLevel) || THINKING_LEVELS[1];
  const currentUnlocked = isUnlocked(currentModel);

  const filteredModels = filterProvider === 'all' 
    ? effectiveModels 
    : effectiveModels.filter(m => m.provider === filterProvider);

  return (
    <div className="flex items-center gap-2">
      {/* 1. Model Selector Dropdown */}
      <div className="relative" ref={modelDropdownRef}>
        <button
          type="button"
          onClick={() => {
            setIsModelDropdownOpen(!isModelDropdownOpen);
            setIsThinkingDropdownOpen(false);
          }}
          className={`flex items-center gap-2 px-3 py-1.5 bg-slate-950/90 hover:bg-slate-800/90 border rounded-xl text-xs font-medium text-slate-200 transition-all shadow-inner group ${
            currentUnlocked
              ? 'border-slate-700/70 hover:border-cyan-500/50'
              : 'border-amber-500/40 text-amber-200'
          }`}
        >
          <span className="flex items-center gap-1.5 font-semibold text-slate-100">
            {currentUnlocked ? (
              getProviderIcon(currentModel.provider)
            ) : (
              <Lock className="w-3.5 h-3.5 text-amber-400" />
            )}
            <span>{currentModel.name}</span>
          </span>
          
          {currentUnlocked ? (
            <span className={`px-1.5 py-0.5 text-[10px] font-mono rounded border ${getProviderBadge(currentModel.provider)}`}>
              {currentModel.tier}
            </span>
          ) : (
            <span className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-center gap-1 font-semibold">
              🔒 Key Required
            </span>
          )}

          <ChevronDown className={`w-3.5 h-3.5 text-slate-400 group-hover:text-cyan-400 transition-transform duration-200 ${isModelDropdownOpen ? 'rotate-180 text-cyan-400' : ''}`} />
        </button>

        {isModelDropdownOpen && (
          <div className="absolute left-0 bottom-full mb-2 w-84 sm:w-96 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl backdrop-blur-xl z-50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-150">
            {/* Header & Filter Tabs */}
            <div className="p-3 border-b border-slate-800 bg-slate-950/60 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <SlidersHorizontal className="w-3.5 h-3.5 text-cyan-400" />
                  Select Reasoning Model
                </span>
                <button
                  type="button"
                  onClick={() => triggerOpenVault(currentModel.provider)}
                  className="flex items-center gap-1 text-[11px] font-mono text-cyan-400 hover:text-cyan-300 underline underline-offset-2 cursor-pointer"
                >
                  <Key className="w-3 h-3" />
                  Manage Keys
                </button>
              </div>

              {/* Provider Quick Filter Pills */}
              <div className="flex items-center gap-1 pt-1 overflow-x-auto pb-0.5">
                {['all', 'gemini', 'openai', 'anthropic', 'deepseek', 'groq'].map((prov) => (
                  <button
                    key={prov}
                    type="button"
                    onClick={() => setFilterProvider(prov)}
                    className={`px-2 py-0.5 rounded-lg text-[10px] font-mono uppercase transition-colors cursor-pointer ${
                      filterProvider === prov
                        ? 'bg-cyan-500 text-slate-950 font-bold'
                        : 'bg-slate-800/80 hover:bg-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {prov}
                  </button>
                ))}
              </div>
            </div>

            {/* Model List with Lock Awareness */}
            <div className="max-h-76 overflow-y-auto p-1.5 space-y-1">
              {filteredModels.map((model) => {
                const unlocked = isUnlocked(model);
                const isSelected = model.id === currentModel.id;

                return (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => {
                      if (unlocked) {
                        onSelectModel?.(model);
                        setIsModelDropdownOpen(false);
                      } else {
                        // Pre-focus the KeyVault modal on the required provider tab
                        triggerOpenVault(model.provider);
                      }
                    }}
                    className={`w-full text-left p-2.5 rounded-xl transition-all flex items-start justify-between gap-3 cursor-pointer ${
                      isSelected
                        ? 'bg-cyan-500/10 border border-cyan-500/40 text-cyan-200 shadow-sm'
                        : unlocked
                        ? 'hover:bg-slate-800/70 border border-transparent text-slate-300'
                        : 'bg-slate-950/40 border border-slate-900/80 opacity-60 hover:opacity-85 hover:border-amber-500/30 text-slate-400'
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <div className="mt-0.5 p-1 rounded-lg bg-slate-950 border border-slate-800">
                        {unlocked ? (
                          getProviderIcon(model.provider)
                        ) : (
                          <Lock className="w-3.5 h-3.5 text-amber-400" />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-bold ${unlocked ? 'text-slate-100' : 'text-slate-300'}`}>
                            {model.name}
                          </span>
                          
                          {/* Unlocked Active Badge vs Locked Key Required Badge */}
                          {unlocked ? (
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-semibold">
                              {model.discovered ? 'Live ⚡' : 'Active'}
                            </span>
                          ) : (
                            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-center gap-1 font-semibold">
                              🔒 Key Required
                            </span>
                          )}

                          <span className={`px-1.5 py-0.2 text-[9px] font-mono rounded border ${getProviderBadge(model.provider)}`}>
                            {model.tier}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5 line-clamp-1">{model.description}</p>
                      </div>
                    </div>

                    <div className="flex items-center shrink-0 mt-1">
                      {isSelected ? (
                        <Check className="w-4 h-4 text-cyan-400" />
                      ) : !unlocked ? (
                        <span className="text-[9px] font-mono text-cyan-400 underline underline-offset-2">
                          Add Key →
                        </span>
                      ) : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 2. Thinking Level Submenu */}
      <div className="relative" ref={thinkingDropdownRef}>
        <button
          type="button"
          onClick={() => {
            setIsThinkingDropdownOpen(!isThinkingDropdownOpen);
            setIsModelDropdownOpen(false);
          }}
          className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-950/90 hover:bg-slate-800/90 border border-slate-700/70 hover:border-purple-500/50 rounded-xl text-xs font-mono text-purple-300 transition-all shadow-inner group"
          title={`Reasoning Budget: ${currentThinking.budget}`}
        >
          <Brain className="w-3.5 h-3.5 text-purple-400" />
          <span>Thinking: {currentThinking.label}</span>
          <ChevronDown className={`w-3 h-3 text-purple-400/70 group-hover:text-purple-300 transition-transform duration-200 ${isThinkingDropdownOpen ? 'rotate-180' : ''}`} />
        </button>

        {isThinkingDropdownOpen && (
          <div className="absolute left-0 bottom-full mb-2 w-56 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl backdrop-blur-xl z-50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-150 p-1.5 space-y-1">
            <div className="px-2.5 py-1.5 border-b border-slate-800 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Reasoning Token Budget
            </div>
            {THINKING_LEVELS.map((level) => {
              const isSelected = level.id === thinkingLevel;
              return (
                <button
                  key={level.id}
                  type="button"
                  onClick={() => {
                    onSelectThinkingLevel?.(level.id);
                    setIsThinkingDropdownOpen(false);
                  }}
                  className={`w-full text-left p-2 rounded-xl transition-all flex items-center justify-between text-xs font-mono cursor-pointer ${
                    isSelected
                      ? 'bg-purple-500/15 border border-purple-500/40 text-purple-200 font-bold'
                      : 'hover:bg-slate-800/70 text-slate-300 border border-transparent'
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span>{level.label}</span>
                      <span className="text-[10px] text-slate-400 font-normal">({level.budget})</span>
                    </div>
                    <div className="text-[10px] text-slate-500 font-sans">{level.desc}</div>
                  </div>
                  {isSelected && <Check className="w-3.5 h-3.5 text-purple-400 shrink-0" />}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
