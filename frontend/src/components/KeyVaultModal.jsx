import React, { useState, useEffect } from 'react';
import { 
  X, 
  Key, 
  Lock, 
  CheckCircle2, 
  ExternalLink, 
  Trash2, 
  Eye, 
  EyeOff, 
  ShieldCheck, 
  Zap, 
  Sparkles, 
  Cpu, 
  Brain, 
  Activity, 
  AlertCircle, 
  RefreshCw 
} from 'lucide-react';
import { api } from '../services/api';

export const PROVIDER_METADATA = [
  {
    id: 'gemini',
    name: 'Google Gemini',
    icon: Zap,
    dotColor: 'bg-amber-400',
    color: 'text-amber-400',
    borderColor: 'border-amber-500/30',
    bgColor: 'bg-amber-500/10',
    envName: 'GEMINI_API_KEY',
    link: 'https://aistudio.google.com/app/apikey',
    placeholder: 'AIzaSy...',
    description: 'Powers Gemini 2.0 Flash, 2.5 Flash, 3.8 Flash, and 1.5 Pro models with dual-stream AST reasoning.',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    icon: Cpu,
    dotColor: 'bg-emerald-400',
    color: 'text-emerald-400',
    borderColor: 'border-emerald-500/30',
    bgColor: 'bg-emerald-500/10',
    envName: 'OPENAI_API_KEY',
    link: 'https://platform.openai.com/account/api-keys',
    placeholder: 'sk-proj-...',
    description: 'Powers GPT-4o and o3-mini reasoning models for structural graph traversal synthesis.',
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    icon: Sparkles,
    dotColor: 'bg-purple-400',
    color: 'text-purple-400',
    borderColor: 'border-purple-500/30',
    bgColor: 'bg-purple-500/10',
    envName: 'ANTHROPIC_API_KEY',
    link: 'https://console.anthropic.com/settings/keys',
    placeholder: 'sk-ant-...',
    description: 'Powers Claude 3.7 Sonnet (Hybrid Thinking) and Claude 3.5 Sonnet code-generation models.',
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    icon: Brain,
    dotColor: 'bg-blue-400',
    color: 'text-blue-400',
    borderColor: 'border-blue-500/30',
    bgColor: 'bg-blue-500/10',
    envName: 'DEEPSEEK_API_KEY',
    link: 'https://platform.deepseek.com/api_keys',
    placeholder: 'sk-...',
    description: 'Powers DeepSeek R1 open-weights reasoning model with chain-of-thought analysis.',
  },
  {
    id: 'groq',
    name: 'Groq Cloud',
    icon: Zap,
    dotColor: 'bg-rose-400',
    color: 'text-rose-400',
    borderColor: 'border-rose-500/30',
    bgColor: 'bg-rose-500/10',
    envName: 'GROQ_API_KEY',
    link: 'https://console.groq.com/keys',
    placeholder: 'gsk_...',
    description: 'Powers Llama 3.3 70B and dynamic Groq models with sub-second LPU inference latency.',
  },
];

export default function KeyVaultModal({
  isOpen,
  onClose,
  activeKeys = {},
  onSaveKey,
  onDeleteKey,
  isEncryptedInBackend = false,
  maskedKeyDisplay = '',
  onKeysUpdated,
  defaultProvider = 'gemini',
  initialTab,
}) {
  const targetInitial = (initialTab || defaultProvider || 'gemini').toLowerCase();
  const [selectedProvider, setSelectedProvider] = useState(targetInitial);
  const [keyInputs, setKeyInputs] = useState({});
  const [showKey, setShowKey] = useState({});
  const [statusMessage, setStatusMessage] = useState({ text: '', type: '' });
  const [isTesting, setIsTesting] = useState(false);
  const [backendStatus, setBackendStatus] = useState({});
  const [maskedKeys, setMaskedKeys] = useState({});

  useEffect(() => {
    const tabToFocus = initialTab || defaultProvider;
    if (tabToFocus) {
      setSelectedProvider(tabToFocus.toLowerCase());
    }
  }, [initialTab, defaultProvider, isOpen]);

  // Fetch live key configuration status from backend
  const fetchStatus = async () => {
    try {
      const res = await api.getKeysStatus();
      if (res) {
        setBackendStatus(res.status || res);
        if (res.masked_keys) setMaskedKeys(res.masked_keys);
      }
    } catch {
      // Offline fallback: rely on local state
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchStatus();
      setStatusMessage({ text: '', type: '' });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const currentMeta = PROVIDER_METADATA.find(p => p.id === selectedProvider) || PROVIDER_METADATA[0];

  const isConfigured = (providerId) => {
    return Boolean(
      backendStatus[providerId] ||
      activeKeys[providerId] ||
      (providerId === 'gemini' && (isEncryptedInBackend || maskedKeyDisplay))
    );
  };

  const handleInputChange = (providerId, value) => {
    setKeyInputs(prev => ({ ...prev, [providerId]: value }));
  };

  const handleSave = async (providerId) => {
    const rawVal = (keyInputs[providerId] || '').trim();
    if (!rawVal) return;
    setStatusMessage({ text: 'Encrypting and storing key...', type: 'info' });

    try {
      await api.saveApiKey(providerId, rawVal);
      await onSaveKey?.(providerId, rawVal);
      setKeyInputs(prev => ({ ...prev, [providerId]: '' }));
      setStatusMessage({ text: `✅ Key for ${providerId.toUpperCase()} saved & encrypted in database!`, type: 'success' });
      await fetchStatus();
      onKeysUpdated?.();
      setTimeout(() => setStatusMessage({ text: '', type: '' }), 3500);
    } catch (err) {
      setStatusMessage({ text: `❌ Save failed: ${err.message}`, type: 'error' });
    }
  };

  const handleClear = async (providerId) => {
    setStatusMessage({ text: 'Clearing key...', type: 'info' });
    try {
      await api.deleteApiKey(providerId);
      await onDeleteKey?.(providerId);
      setKeyInputs(prev => ({ ...prev, [providerId]: '' }));
      setStatusMessage({ text: `Key for ${providerId.toUpperCase()} removed from vault.`, type: 'info' });
      await fetchStatus();
      onKeysUpdated?.();
      setTimeout(() => setStatusMessage({ text: '', type: '' }), 3500);
    } catch (err) {
      setStatusMessage({ text: `❌ Clear failed: ${err.message}`, type: 'error' });
    }
  };

  const handleTest = async (providerId) => {
    const inputVal = (keyInputs[providerId] || '').trim();
    setIsTesting(true);
    setStatusMessage({ text: `Testing connection to ${providerId.toUpperCase()} (connecting to backend)...`, type: 'info' });

    try {
      const res = await api.testApiKey(providerId, inputVal || undefined);
      setIsTesting(false);
      if (res && res.success) {
        setStatusMessage({ text: `✅ ${res.message || 'Key authenticated successfully!'}`, type: 'success' });
      } else {
        setStatusMessage({ text: `⚠️ Validation notice: ${res?.error || res?.message || 'Check key validity'}`, type: 'error' });
      }
    } catch (err) {
      setIsTesting(false);
      setStatusMessage({ text: `❌ Test connection failed: ${err.message}`, type: 'error' });
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div 
        className="max-w-2xl w-full bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-slate-800/80 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-inner">
              <Key className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-slate-100 text-base">Unified Multi-Provider Key Vault</h3>
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-[10px] font-bold flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" />
                  AES-128-CBC
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Multi-provider key isolation: routes individual provider keys strictly to their matching models.
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 rounded-xl text-slate-400 hover:text-slate-100 hover:bg-slate-800/80 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 1. Provider Navigation Tab Bar */}
        <div className="p-2 border-b border-slate-800/70 bg-slate-950/40 flex items-center gap-1 overflow-x-auto">
          {PROVIDER_METADATA.map((prov) => {
            const Icon = prov.icon;
            const isSelected = selectedProvider === prov.id;
            const configured = isConfigured(prov.id);

            return (
              <button
                key={prov.id}
                type="button"
                onClick={() => setSelectedProvider(prov.id)}
                className={`px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-2 transition-all whitespace-nowrap cursor-pointer ${
                  isSelected
                    ? 'bg-slate-800 border border-cyan-500/40 text-cyan-200 shadow-sm'
                    : 'hover:bg-slate-800/50 text-slate-400 hover:text-slate-200 border border-transparent'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${prov.dotColor}`} />
                <Icon className={`w-3.5 h-3.5 ${prov.color}`} />
                <span>{prov.name}</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[9px] font-mono font-bold ${
                  configured 
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' 
                    : 'bg-slate-800 text-slate-500 border border-slate-700/60'
                }`}>
                  {configured ? 'Active 🟢' : 'Not Configured ⚪'}
                </span>
              </button>
            );
          })}
        </div>

        {/* Active Provider Configuration View */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {/* Title & Docs Link */}
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <div className="flex items-center gap-3">
              <div className={`p-2.5 rounded-2xl ${currentMeta.bgColor} border ${currentMeta.borderColor}`}>
                <currentMeta.icon className={`w-5 h-5 ${currentMeta.color}`} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-bold text-slate-100">{currentMeta.name}</h4>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                    isConfigured(currentMeta.id)
                      ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                      : 'bg-slate-800 text-slate-400 border border-slate-700'
                  }`}>
                    {isConfigured(currentMeta.id) ? 'Active 🟢' : 'Not Configured ⚪'}
                  </span>
                </div>
                <p className="text-[11px] font-mono text-slate-500 mt-0.5">{currentMeta.envName}</p>
              </div>
            </div>

            <a
              href={currentMeta.link}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-xl text-xs font-mono text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              <span>Get API Key</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>

          <p className="text-xs text-slate-400 leading-relaxed">
            {currentMeta.description}
          </p>

          {/* Active Key Status Card */}
          {isConfigured(currentMeta.id) && (
            <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl text-xs space-y-1.5 text-emerald-300 font-mono">
              <div className="font-bold flex items-center gap-1.5">
                <Lock className="w-4 h-4 text-emerald-400" />
                <span>Secure Storage Active ({currentMeta.name})</span>
              </div>
              <div className="text-[11px] text-slate-300">
                Current Key:{' '}
                <span className="text-cyan-400 font-bold">
                  {maskedKeys[currentMeta.id] || (currentMeta.id === 'gemini' && maskedKeyDisplay ? maskedKeyDisplay : '•••••••••••••••• (Encrypted)')}
                </span>
              </div>
            </div>
          )}

          {/* Input Box */}
          <div className="space-y-1.5">
            <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider font-mono">
              Enter {currentMeta.name} API Key
            </label>
            <div className="relative">
              <input
                type={showKey[currentMeta.id] ? 'text' : 'password'}
                value={keyInputs[currentMeta.id] || ''}
                onChange={(e) => handleInputChange(currentMeta.id, e.target.value)}
                placeholder={currentMeta.placeholder}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-3.5 pr-10 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-cyan-500 font-mono placeholder-slate-600"
              />
              <button
                type="button"
                onClick={() => setShowKey(prev => ({ ...prev, [currentMeta.id]: !prev[currentMeta.id] }))}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 cursor-pointer"
              >
                {showKey[currentMeta.id] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Real-time Status Message */}
          {statusMessage.text && (
            <div className={`p-3 rounded-xl text-xs font-mono flex items-center gap-2 ${
              statusMessage.type === 'success' 
                ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                : statusMessage.type === 'error'
                ? 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
                : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30'
            }`}>
              {statusMessage.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
              ) : statusMessage.type === 'error' ? (
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              ) : (
                <Activity className="w-4 h-4 shrink-0 text-cyan-400 animate-pulse" />
              )}
              <span className="flex-1">{statusMessage.text}</span>
            </div>
          )}

          {/* Action Buttons: Save, Live Test, Clear */}
          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={() => handleSave(currentMeta.id)}
              disabled={!(keyInputs[currentMeta.id] || '').trim()}
              className="flex-1 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-40 text-slate-950 font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 transition cursor-pointer flex items-center justify-center gap-1.5"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>Save Key</span>
            </button>

            <button
              type="button"
              onClick={() => handleTest(currentMeta.id)}
              disabled={isTesting || (!isConfigured(currentMeta.id) && !(keyInputs[currentMeta.id] || '').trim())}
              className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-cyan-300 font-bold text-xs rounded-xl border border-slate-700 transition cursor-pointer flex items-center gap-1.5"
            >
              {isTesting ? <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" /> : <Activity className="w-3.5 h-3.5" />}
              <span>Live Test</span>
            </button>

            {isConfigured(currentMeta.id) && (
              <button
                type="button"
                onClick={() => handleClear(currentMeta.id)}
                className="px-3.5 py-2.5 bg-slate-800 hover:bg-rose-500/20 hover:text-rose-400 text-slate-400 font-bold text-xs rounded-xl border border-slate-700 transition cursor-pointer flex items-center gap-1.5"
                title="Clear Key"
              >
                <Trash2 className="w-4 h-4" />
                <span>Clear</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
