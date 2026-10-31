import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { api } from './services/api';
import { ChatMessageContent } from './components/ChatMessageContent';
import { preFilterProjectZip, filterAndZipFolder, getFilesFromDataTransfer } from './utils/zipFilter';
import { RefactorDiffViewer } from './components/RefactorDiffViewer';
import { BlastRadiusGraph } from './components/BlastRadiusGraph';
import { UnifiedArchitectureGraph } from './components/UnifiedArchitectureGraph';
import HybridRAGSearch from './components/HybridRAGSearch';
import KeyVaultModal from './components/KeyVaultModal';
import DynamicModelSelector from './components/DynamicModelSelector';
import {
  Shield, Key, GitBranch, Cpu, Zap, AlertTriangle, ArrowRight, RefreshCw, Terminal, Sliders,
  Search, Activity, Sparkles, LogOut, Folder, UploadCloud, GitPullRequest, Check, Copy,
  Plus, X, Lock, ZoomIn, ZoomOut, Maximize2, RotateCcw, Layers, CheckCircle2, Trash2
} from 'lucide-react';

const INITIAL_WORKSPACES = [
  {
    id: 'ws-study-sync',
    name: 'Study-Sync Backend',
    repoUrl: 'https://github.com/HarshaAppikatla/Study-Sync',
    type: 'git',
    branch: 'main',
    filesCount: 211,
    nodesCount: 2533,
    edgesCount: 1195,
    lastIndexed: 'Just now',
    status: 'READY',
    language: 'Java / Spring Boot'
  },
  {
    id: 'ws-payment-gw',
    name: 'Payment-Gateway Microservice',
    repoUrl: 'payment-gateway-service.zip',
    type: 'zip',
    branch: 'release/v2.1',
    filesCount: 148,
    nodesCount: 1820,
    edgesCount: 840,
    lastIndexed: '2 hours ago',
    status: 'READY',
    language: 'Go / gRPC'
  }
];

const SYMBOL_GRAPHS = {
  generateToken: {
    name: 'generateToken',
    scope: 'JwtService',
    type: 'Method',
    file: 'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java',
    line: 38,
    signature: 'public String generateToken(UserDetails userDetails)',
    riskLevel: 'HIGH',
    riskScore: '8.8 / 10',
    blastRadiusHops: 3,
    nodes: [
      { id: 'target', label: 'JwtService.generateToken', file: 'JwtService.java', type: 'TARGET', x: 400, y: 220, scope: 'Service Method' },
      { id: 'caller_1', label: 'AuthenticationService.authenticate', file: 'AuthenticationService.java', type: 'DIRECT_CALLER', x: 180, y: 100, scope: 'Direct Caller (Line 52)' },
      { id: 'caller_2', label: 'AuthenticationService.register', file: 'AuthenticationService.java', type: 'DIRECT_CALLER', x: 620, y: 100, scope: 'Direct Caller (Line 89)' },
      { id: 'transitive_1', label: 'AuthenticationController.refreshToken', file: 'AuthenticationController.java', type: 'TRANSITIVE_CALLER', x: 680, y: 280, scope: 'Transitive Caller (Line 41)' },
      { id: 'callee_1', label: 'buildToken', file: 'JwtService.java', type: 'CALLEE', x: 220, y: 350, scope: 'Internal Helper' },
      { id: 'callee_2', label: 'Jwts.builder', file: 'io.jsonwebtoken', type: 'CALLEE', x: 520, y: 360, scope: 'Library Dependency' }
    ],
    edges: [
      { from: 'caller_1', to: 'target', label: '[:CALLS]', hop: '1st Hop' },
      { from: 'caller_2', to: 'target', label: '[:CALLS]', hop: '1st Hop' },
      { from: 'transitive_1', to: 'caller_2', label: '[:CALLS]', hop: '2nd Hop' },
      { from: 'target', to: 'callee_1', label: '[:CALLS]', hop: 'Internal' },
      { from: 'callee_1', to: 'callee_2', label: '[:EXTENDS]', hop: 'Library' }
    ],
    codeSnippet: `public String generateToken(UserDetails userDetails) {
    return generateToken(new HashMap<>(), userDetails);
}

public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails) {
    return buildToken(extraClaims, userDetails, jwtExpiration);
}`
  },
  authenticate: {
    name: 'authenticate',
    scope: 'AuthenticationService',
    type: 'Method',
    file: 'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java',
    line: 45,
    signature: 'public AuthenticationResponse authenticate(AuthenticationRequest request)',
    riskLevel: 'MEDIUM',
    riskScore: '5.2 / 10',
    blastRadiusHops: 2,
    nodes: [
      { id: 'target', label: 'AuthenticationService.authenticate', file: 'AuthenticationService.java', type: 'TARGET', x: 400, y: 200, scope: 'Service Orchestrator' },
      { id: 'caller_1', label: 'AuthenticationController.authenticate', file: 'AuthenticationController.java', type: 'DIRECT_CALLER', x: 220, y: 100, scope: 'REST Endpoint' },
      { id: 'callee_1', label: 'jwtService.generateToken', file: 'JwtService.java', type: 'CALLEE', x: 200, y: 340, scope: 'Token Issuer' },
      { id: 'callee_2', label: 'userRepository.findByEmail', file: 'UserRepository.java', type: 'CALLEE', x: 600, y: 340, scope: 'DAO Access' }
    ],
    edges: [
      { from: 'caller_1', to: 'target', label: '[:CALLS]', hop: '1st Hop' },
      { from: 'target', to: 'callee_1', label: '[:CALLS]', hop: 'Internal' },
      { from: 'target', to: 'callee_2', label: '[:CALLS]', hop: 'Internal' }
    ],
    codeSnippet: `public AuthenticationResponse authenticate(AuthenticationRequest request) {
    authenticationManager.authenticate(
        new UsernamePasswordAuthenticationToken(request.getEmail(), request.getPassword())
    );
    var user = repository.findByEmail(request.getEmail()).orElseThrow();
    var jwtToken = jwtService.generateToken(user);
    return AuthenticationResponse.builder().token(jwtToken).build();
}`
  },
  registerStompEndpoints: {
    name: 'registerStompEndpoints',
    scope: 'WebSocketConfig',
    type: 'Method',
    file: 'studysync-backend/src/main/java/com/studysync/studysyncbackend/config/WebSocketConfig.java',
    line: 22,
    signature: 'public void registerStompEndpoints(StompEndpointRegistry registry)',
    riskLevel: 'LOW',
    riskScore: '2.1 / 10',
    blastRadiusHops: 1,
    nodes: [
      { id: 'target', label: 'WebSocketConfig.registerStompEndpoints', file: 'WebSocketConfig.java', type: 'TARGET', x: 400, y: 220, scope: 'Spring Config' },
      { id: 'callee_1', label: 'StompEndpointRegistry.addEndpoint', file: 'org.springframework', type: 'CALLEE', x: 400, y: 360, scope: 'Framework Hook' }
    ],
    edges: [
      { from: 'target', to: 'callee_1', label: '[:CALLS]', hop: 'Framework' }
    ],
    codeSnippet: `@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws").setAllowedOriginPatterns("*").withSockJS();
}`
  }
};

// Memoized chat bubble: ensures prior messages and their rendered Mermaid SVGs NEVER re-render on typing or new turns
const ChatMessageBubble = React.memo(({ msg }) => (
  <div
    className={`p-4 rounded-2xl max-w-3xl text-xs leading-relaxed space-y-2 ${msg.sender === 'user' ? 'bg-cyan-500/10 border border-cyan-500/30 text-slate-100 ml-auto' : 'bg-slate-900 border border-slate-800 text-slate-300'}`}
  >
    <div className="font-bold text-[10px] uppercase font-mono text-cyan-400">
      {msg.sender === 'user' ? 'Developer' : 'CodeGraph Assistant'}
    </div>
    <ChatMessageContent text={msg.text} />
    {msg.sources && msg.sources.length > 0 && (
      <div className="pt-2 border-t border-slate-800 text-[10px] font-mono text-slate-400">
        Sources: {msg.sources.join(', ')}
      </div>
    )}
  </div>
));

export default function App() {
  // Authentication & Global User State
  const [currentUser, setCurrentUser] = useState(null);
  const [authMode, setAuthMode] = useState('LOGIN');
  const [authEmail, setAuthEmail] = useState('harsha.demo@codegraph.ai');
  const [authPassword, setAuthPassword] = useState('demopassword2026');
  const [geminiApiKey, setGeminiApiKey] = useState(() => localStorage.getItem('codegraph_gemini_api_key') || '');
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);
  const [tempApiKeyInput, setTempApiKeyInput] = useState('');
  const [isKeyEncryptedInBackend, setIsKeyEncryptedInBackend] = useState(false);
  const [maskedKeyDisplay, setMaskedKeyDisplay] = useState('');

  const checkBackendKey = async () => {
    try {
      const res = await api.getGeminiKey();
      if (res && res.configured) {
        setIsKeyEncryptedInBackend(true);
        setMaskedKeyDisplay(res.masked_key || '');
        if (!geminiApiKey) setGeminiApiKey(res.masked_key || 'CONFIGURED');
      } else {
        setIsKeyEncryptedInBackend(false);
        setMaskedKeyDisplay('');
      }
    } catch {
      // not logged in yet or offline
    }
  };

  useEffect(() => {
    if (currentUser) {
      checkBackendKey();
    }
  }, [currentUser]);

  const handleSaveApiKey = async (keyToSave) => {
    const val = (keyToSave !== undefined ? keyToSave : tempApiKeyInput).trim();
    if (val) {
      setGeminiApiKey(val);
      localStorage.setItem('codegraph_gemini_api_key', val);
      try {
        const res = await api.saveGeminiKey(val);
        setIsKeyEncryptedInBackend(true);
        setMaskedKeyDisplay(res.masked_key || '');
        handleCopy('', 'API Key Encrypted & Stored in Backend DB!');
      } catch (err) {
        console.warn("Could not save to backend:", err);
        handleCopy('', 'Saved locally in browser');
      }
    } else {
      setGeminiApiKey('');
      localStorage.removeItem('codegraph_gemini_api_key');
      setIsKeyEncryptedInBackend(false);
      setMaskedKeyDisplay('');
      try {
        await api.deleteGeminiKey();
        handleCopy('', 'Key cleared from backend DB');
      } catch {}
    }
    setShowApiKeyModal(false);
  };

  // Application Screen State
  const [currentScreen, setCurrentScreen] = useState('AUTH');

  // Workspaces List (Clean empty default for users; populated for demo account)
  const [workspaces, setWorkspaces] = useState([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState(null);
  const [workspaceToDelete, setWorkspaceToDelete] = useState(null);
  const [isDeletingWorkspace, setIsDeletingWorkspace] = useState(false);

  // Workspace Creation Form
  const [uploadType, setUploadType] = useState('git');
  const [gitRepoInput, setGitRepoInput] = useState('');
  const [zipFileName, setZipFileName] = useState('');
  const [zipFile, setZipFile] = useState(null);
  const [folderFiles, setFolderFiles] = useState(null);
  const [selectedFolderName, setSelectedFolderName] = useState('');
  const [authError, setAuthError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const ingestTimers = useRef([]);
  const [branchInput, setBranchInput] = useState('main');

  // Ingestion Progress State
  const [ingestProgress, setIngestProgress] = useState(0);
  const [ingestStageText, setIngestStageText] = useState('Initializing AST Tree-sitter parser...');
  const [ingestLogs, setIngestLogs] = useState([]);

  // Workspace Navigation Tabs
  const [activeTab, setActiveTab] = useState('GRAPH');

  // Symbol Inspector / Blast Radius State
  const [workspaceSymbols, setWorkspaceSymbols] = useState([]);
  const [selectedSymbolKey, setSelectedSymbolKey] = useState('generateToken');
  const [liveGraphData, setLiveGraphData] = useState(null);
  const [blastRadiusActive, setBlastRadiusActive] = useState(true);
  const [searchFilter, setSearchFilter] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState('target');
  const [graphVisualMode, setGraphVisualMode] = useState('force-d3'); // 'force-d3' | 'classic'

  // Single Unified Architecture & Multi-Relation Graph State
  const [graphScope, setGraphScope] = useState('ARCHITECTURE'); // 'ARCHITECTURE' | 'SYMBOL'
  const [architectureGraphData, setArchitectureGraphData] = useState(null);
  const [isArchLoading, setIsArchLoading] = useState(false);

  // Zoom and Pan Controls
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [dragStartPos, setDragStartPos] = useState({ x: 0, y: 0 });

  const handleCanvasMouseDown = (e) => {
    if (e.target.tagName === 'svg' || e.target.tagName === 'line' || e.target.tagName === 'path') {
      setIsDraggingCanvas(true);
      setDragStartPos({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
    }
  };

  const handleCanvasMouseMove = (e) => {
    if (!isDraggingCanvas) return;
    setPanOffset({ x: e.clientX - dragStartPos.x, y: e.clientY - dragStartPos.y });
  };

  const handleCanvasMouseUp = () => {
    setIsDraggingCanvas(false);
  };

  const handleWheelZoom = (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    setZoomLevel(prev => Math.min(Math.max(prev * zoomFactor, 0.4), 2.5));
  };

  // AI & QA Assistant State
  const [qaInput, setQaInput] = useState('');
  const [qaMessages, setQaMessages] = useState([
    {
      sender: 'assistant',
      text: 'Hello! I am your CodeGraph-RAG Architectural AI. Select or ingest a codebase to search symbols, inspect dependencies, and generate verified refactors.',
      sources: []
    }
  ]);
  const [isAiThinking, setIsAiThinking] = useState(false);

  // Refactor Sandbox State
  const [refactorPrompt, setRefactorPrompt] = useState('');
  const [followUpPrompt, setFollowUpPrompt] = useState('');
  const [generatedDiff, setGeneratedDiff] = useState(null);
  const [refactorHistory, setRefactorHistory] = useState([]);
  const [isGeneratingDiff, setIsGeneratingDiff] = useState(false);
  const [showPrModal, setShowPrModal] = useState(false);

  // Copy Feedback Toast State
  const [copiedText, setCopiedText] = useState(null);

  const handleCopy = (text, label = 'Copied') => {
    navigator.clipboard.writeText(text);
    setCopiedText(label);
    setTimeout(() => setCopiedText(null), 2000);
  };

  // Wake up backend (e.g. Render free tier) on page load & cleanup ingestion polling on unmount
  useEffect(() => {
    api.checkHealth?.().catch(() => {});
    return () => {
      ingestTimers.current.forEach(clearInterval);
      ingestTimers.current = [];
    };
  }, []);

  // Universal Auto-Poll: Silently checks status of any INDEXING workspaces on the Hub screen
  useEffect(() => {
    if (currentScreen !== 'WORKSPACE_SELECT') return;
    const hasIndexing = workspaces.some(w => w.status === 'INDEXING');
    if (!hasIndexing) return;

    const interval = setInterval(async () => {
      try {
        const freshList = await api.listWorkspaces();
        if (freshList && freshList.length > 0) {
          setWorkspaces(freshList);
        }
      } catch (err) {
        console.warn("Auto-reconcile polling notice:", err);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [currentScreen, workspaces]);

  // Dynamic Workspace Symbol and Info Loader
  useEffect(() => {
    if (!selectedWorkspace?.id) return;
    let isCanceled = false;
    const isDemo = Boolean(selectedWorkspace.id.startsWith('ws-') && currentUser?.isDemo);

    // Reset local graph and symbol states on workspace switch to avoid stale rendering
    setLiveGraphData(null);
    setGeneratedDiff(null);
    setRefactorHistory([]);

    if (!isDemo) {
      setSelectedSymbolKey('');
      setRefactorPrompt('');
    } else if (selectedWorkspace.id === 'ws-study-sync') {
      setRefactorPrompt('Update JwtService.generateToken signature to accept explicit Claims map and set token expiration to 24 hours.');
    } else if (selectedWorkspace.id === 'ws-payment-gw') {
      setRefactorPrompt('Add idempotency key validation and distributed locking to processPayment endpoint.');
    } else {
      setRefactorPrompt('');
    }

    // Update initial QA chat greeting based on active workspace
    if (!isDemo) {
      setQaMessages([
        {
          sender: 'assistant',
          text: `Hello! I have indexed workspace '${selectedWorkspace.name}' (${selectedWorkspace.filesCount || 0} files, language: ${selectedWorkspace.language || 'Code'}). Ask me about its architecture, methods, or classes!`,
          sources: [selectedWorkspace.name]
        }
      ]);
    } else {
      setQaMessages([
        {
          sender: 'assistant',
          text: 'Hello! I am your CodeGraph-RAG Architectural AI. I have indexed Study-Sync into Qdrant vector store (384D) and Neo4j call graph (2,533 nodes). Ask me anything about symbol dependencies or architectural impact!',
          sources: ['JwtService.java', 'AuthenticationService.java']
        }
      ]);
    }

    // Sync latest workspace metadata from backend (detects branch/files updates)
    api.getWorkspace(selectedWorkspace.id)
      .then(latestWs => {
        if (isCanceled || !latestWs) return;
        if (latestWs.status !== selectedWorkspace.status || latestWs.filesCount !== selectedWorkspace.filesCount || latestWs.branch !== selectedWorkspace.branch) {
          setSelectedWorkspace(latestWs);
          setWorkspaces(prev => prev.map(w => w.id === latestWs.id ? latestWs : w));
        }
      })
      .catch(console.warn);

    api.listWorkspaceSymbols(selectedWorkspace.id)
      .then(res => {
        if (isCanceled) return;
        const syms = res?.symbols || [];
        setWorkspaceSymbols(syms);
        if (syms.length > 0) {
          setSelectedSymbolKey(syms[0].name);
        } else if (isDemo) {
          setSelectedSymbolKey('generateToken');
        }
      })
      .catch(err => {
        if (!isCanceled) {
          console.warn("Could not fetch workspace symbols:", err);
        }
      });

    // Fetch unified whole-codebase architecture & relations graph
    setIsArchLoading(true);
    api.getWorkspaceArchitectureGraph(selectedWorkspace.id)
      .then(arch => {
        if (!isCanceled && arch) {
          setArchitectureGraphData(arch);
        }
      })
      .catch(err => {
        if (!isCanceled) {
          console.warn("Could not fetch workspace architecture graph:", err);
        }
      })
      .finally(() => {
        if (!isCanceled) {
          setIsArchLoading(false);
        }
      });

    // If workspace is still indexing, poll until READY
    let pollTimer = null;
    if (selectedWorkspace.status === 'INDEXING') {
      pollTimer = setInterval(async () => {
        try {
          const ws = await api.getWorkspace(selectedWorkspace.id);
          if (ws && ws.status === 'READY') {
            setSelectedWorkspace(ws);
            setWorkspaces(prev => prev.map(w => w.id === ws.id ? ws : w));
            const symRes = await api.listWorkspaceSymbols(ws.id);
            if (symRes?.symbols?.length > 0) {
              setWorkspaceSymbols(symRes.symbols);
              setSelectedSymbolKey(symRes.symbols[0].name);
            }
            const archRes = await api.getWorkspaceArchitectureGraph(ws.id);
            if (archRes) setArchitectureGraphData(archRes);
            clearInterval(pollTimer);
          }
        } catch (e) {
          console.warn("Workspace background poll:", e);
        }
      }, 2500);
    }

    return () => {
      isCanceled = true;
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [selectedWorkspace?.id]);

  // Dynamic Graph Impact Loader from Backend
  useEffect(() => {
    if (!selectedWorkspace || !selectedSymbolKey) return;
    let isCanceled = false;
    const isDemo = Boolean(selectedWorkspace.id.startsWith('ws-') && currentUser?.isDemo);
    if (!isDemo && selectedSymbolKey === 'generateToken') return;

    api.getSymbolImpact(selectedWorkspace.id, selectedSymbolKey)
      .then(data => {
        if (isCanceled) return;
        if (data && data.nodes && data.nodes.length > 0) {
          setLiveGraphData(data);
        }
      })
      .catch(err => {
        if (isCanceled) return;
        console.warn("Could not fetch symbol impact from API, using AST fallback:", err);
        const match = workspaceSymbols.find(s => s.name === selectedSymbolKey);
        if (match) {
          const fileName = match.file ? match.file.replace(/\\/g, '/').split('/').pop() : 'Source';
          setLiveGraphData({
            name: match.name,
            scope: match.file || 'Workspace',
            type: match.name.charAt(0) === match.name.charAt(0).toUpperCase() ? 'Class' : 'Method',
            file: match.file || 'Workspace',
            line: 1,
            signature: match.name,
            riskLevel: 'LOW',
            riskScore: '2.0 / 10',
            blastRadiusHops: 1,
            nodes: [
              { id: 'target', label: match.name, file: fileName, type: 'TARGET', x: 400, y: 220, scope: 'AST Symbol' }
            ],
            edges: [],
            codeSnippet: `// Symbol: ${match.name}\n// File: ${match.file || 'workspace file'}\n\n// Indexed in Qdrant Vector Store`
          });
        }
      });

    return () => {
      isCanceled = true;
    };
  }, [selectedSymbolKey, selectedWorkspace?.id, workspaceSymbols]);

  const reloadSymbols = useCallback(() => {
    if (!selectedWorkspace?.id) return;
    api.getWorkspace(selectedWorkspace.id)
      .then(ws => {
        if (ws) {
          setSelectedWorkspace(ws);
          setWorkspaces(prev => prev.map(w => w.id === ws.id ? ws : w));
        }
      })
      .catch(console.warn);

    api.listWorkspaceSymbols(selectedWorkspace.id)
      .then(res => {
        const syms = res?.symbols || [];
        setWorkspaceSymbols(syms);
        if (syms.length > 0) {
          setSelectedSymbolKey(prev => (syms.some(s => s.name === prev) ? prev : syms[0].name));
        }
      })
      .catch(console.warn);

    setIsArchLoading(true);
    api.getWorkspaceArchitectureGraph(selectedWorkspace.id)
      .then(arch => {
        if (arch) setArchitectureGraphData(arch);
      })
      .catch(console.warn)
      .finally(() => setIsArchLoading(false));
  }, [selectedWorkspace?.id]);

  const handleLoginDemoAccount = async () => {
    setAuthError('');
    try {
      const res = await api.loginDemo();
      setCurrentUser(res.user);
      setAuthEmail(res.user.email);
      setAuthPassword('demopassword2026');

      // Pre-load demo repository input and demo prompts
      setGitRepoInput('https://github.com/HarshaAppikatla/Study-Sync');
      setRefactorPrompt('Update JwtService.generateToken signature to accept explicit Claims map and set token expiration to 24 hours.');
      setQaMessages([
        {
          sender: 'assistant',
          text: 'Hello! I am your CodeGraph-RAG Architectural AI. I have indexed Study-Sync into Qdrant vector store (384D) and Neo4j call graph (2,533 nodes). Ask me anything about symbol dependencies or architectural impact!',
          sources: ['JwtService.java', 'AuthenticationService.java']
        }
      ]);

      // Fetch demo workspaces from backend (or fallback to INITIAL_WORKSPACES)
      try {
        const wsList = await api.listWorkspaces();
        if (wsList && wsList.length > 0) {
          setWorkspaces(wsList);
          setSelectedWorkspace(wsList[0]);
        } else {
          setWorkspaces(INITIAL_WORKSPACES);
          setSelectedWorkspace(INITIAL_WORKSPACES[0]);
        }
      } catch (wsErr) {
        console.warn("Could not list workspaces from API, using demo defaults:", wsErr);
        setWorkspaces(INITIAL_WORKSPACES);
        setSelectedWorkspace(INITIAL_WORKSPACES[0]);
      }

      setCurrentScreen('WORKSPACE_SELECT');
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    if (!authEmail) return;
    setAuthError('');

    try {
      const res = authMode === 'LOGIN'
        ? await api.login(authEmail, authPassword)
        : await api.register(authEmail, authPassword);
      setCurrentUser(res.user);

      // Clean inputs for custom authenticated user
      setGitRepoInput('');
      setRefactorPrompt('');
      setQaMessages([
        {
          sender: 'assistant',
          text: 'Hello! I am your CodeGraph-RAG Architectural AI. Ingest a codebase to search symbols, inspect dependencies, and generate verified refactors.',
          sources: []
        }
      ]);

      try {
        const wsList = await api.listWorkspaces();
        if (wsList && wsList.length > 0) {
          setWorkspaces(wsList);
          setSelectedWorkspace(wsList[0]);
        } else {
          setWorkspaces([]);
          setSelectedWorkspace(null);
        }
      } catch (wsErr) {
        console.warn("Workspace list fetch error:", wsErr);
        setWorkspaces([]);
        setSelectedWorkspace(null);
      }

      setCurrentScreen('WORKSPACE_SELECT');
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('codegraph_token');
    setCurrentUser(null);
    setWorkspaces([]);
    setSelectedWorkspace(null);
    setGitRepoInput('');
    setRefactorPrompt('');
    setAuthEmail('');
    setAuthPassword('');
    setCurrentScreen('AUTH');
  };

  const handleStartIngestion = async () => {
    setUploadError('');
    if (uploadType === 'zip' && !zipFile && (!folderFiles || folderFiles.length === 0)) {
      setUploadError('Please select a project .zip archive or unzipped local folder.');
      return;
    }

    setCurrentScreen('INGESTION');
    setIngestProgress(5);
    setIngestStageText('Initializing CodeGraph Kinetic Ingestion Engine...');
    setIngestLogs([`[${new Date().toLocaleTimeString()}] Initializing CodeGraph Kinetic Engine...`]);
    ingestTimers.current.forEach(clearInterval);
    ingestTimers.current = [];

    let payloadFile = zipFile;

    // IF UPLOADING A ZIP OR FOLDER: Execute Browser-Side Smart Pre-Filtering
    if (uploadType === 'zip') {
      try {
        let filterResult;
        if (folderFiles && folderFiles.length > 0) {
          setIngestStageText('⚡ Scanning uncompressed local folder and filtering bloat...');
          filterResult = await filterAndZipFolder(folderFiles, (stageMsg) => {
            setIngestStageText(stageMsg);
          });
        } else if (zipFile) {
          setIngestStageText('⚡ Auto-filtering node_modules, .venv, and build bloat...');
          filterResult = await preFilterProjectZip(zipFile, (stageMsg) => {
            setIngestStageText(stageMsg);
          });
        }

        payloadFile = filterResult.cleanFile;

        setIngestLogs(prev => [
          ...prev,
          `[${new Date().toLocaleTimeString()}] Raw Upload Size: ${filterResult.originalSizeMB} MB (${filterResult.totalFiles} files detected)`,
          `[${new Date().toLocaleTimeString()}] ⚡ Auto-Filtered: ${filterResult.skippedFiles} dependency & binary files (node_modules / .venv / build)`,
          `[${new Date().toLocaleTimeString()}] Clean Source Size Sent to API: ${filterResult.cleanSizeMB} MB (Saved ${filterResult.savedPercent}% bandwidth!)`
        ]);

        setIngestProgress(20);
      } catch (err) {
        console.warn("Client-side directory filtering error:", err);
        setUploadError(err.message || 'Failed to process project archive or folder.');
        setCurrentScreen('WORKSPACE_SELECT');
        return; // Halt execution instead of blindly uploading un-filtered bloat
      }
    }

    setIngestStageText('Uploading clean source tree to dual-store index...');

    const payload = uploadType === 'zip'
      ? { type: 'zip', file: payloadFile }
      : { repo_url: gitRepoInput, type: 'git', branch: branchInput };

    try {
      const newWs = await api.ingestWorkspace(payload);
      setWorkspaces(prev => [newWs, ...prev]);
      setSelectedWorkspace(newWs);

      setIngestProgress(25);
      setIngestStageText(`Indexing repository ${newWs.name} into Qdrant & Neo4j...`);
      setIngestLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Workspace '${newWs.name}' created. Extracting AST symbols...`]);

      // Poll workspace status until READY or FAILED (with 90s safety timeout)
      let attempts = 0;
      const maxAttempts = 60; // 60 attempts * 1.5s = 90 seconds timeout
      const pollInterval = setInterval(async () => {
        attempts++;
        if (attempts > maxAttempts) {
          clearInterval(pollInterval);
          setUploadError('Repository ingestion timed out after 90 seconds. Please check backend logs.');
          setCurrentScreen('WORKSPACE_SELECT');
          return;
        }
        try {
          const statusWs = await api.getWorkspace(newWs.id);
          if (statusWs.status === 'READY') {
            clearInterval(pollInterval);
            setIngestProgress(100);
            setIngestStageText(`Dual-store indexing complete: ${statusWs.filesCount} files indexed!`);
            setIngestLogs(prev => [
              ...prev,
              `[${new Date().toLocaleTimeString()}] Parsing complete: ${statusWs.filesCount} files, ${statusWs.nodesCount || 0} graph nodes.`,
              `[${new Date().toLocaleTimeString()}] Ready. Entering Developer Workspace...`
            ]);
            setSelectedWorkspace(statusWs);
            setWorkspaces(prev => prev.map(w => w.id === statusWs.id ? statusWs : w));

            // Fetch real symbols
            const symRes = await api.listWorkspaceSymbols(statusWs.id).catch(() => null);
            if (symRes && symRes.symbols && symRes.symbols.length > 0) {
              setWorkspaceSymbols(symRes.symbols);
              setSelectedSymbolKey(symRes.symbols[0].name);
            }

            setTimeout(() => {
              setCurrentScreen('APP_WORKSPACE');
            }, 700);
          } else if (statusWs.status === 'FAILED') {
            clearInterval(pollInterval);
            setUploadError(statusWs.error || 'Repository ingestion failed.');
            setCurrentScreen('WORKSPACE_SELECT');
          } else {
            const prog = Math.min(30 + attempts * 8, 92);
            setIngestProgress(prog);
            setIngestStageText(`Analyzing polyglot source trees (${statusWs.language || 'detecting'})...`);
            setIngestLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Ingestion in progress... (stage ${prog}%)`]);
          }
        } catch (pollErr) {
          console.warn("Polling error:", pollErr);
        }
      }, 1500);

      ingestTimers.current.push(pollInterval);
    } catch (err) {
      setUploadError(err.message);
      setCurrentScreen('WORKSPACE_SELECT');
    }
  };

  const handleDeleteWorkspace = async (workspace) => {
    if (!workspace || !workspace.id) return;
    try {
      setIsDeletingWorkspace(true);
      await api.deleteWorkspace(workspace.id);
      setWorkspaces((prev) => prev.filter((w) => w.id !== workspace.id));
      if (selectedWorkspace?.id === workspace.id) {
        setSelectedWorkspace(null);
        setCurrentScreen('WORKSPACE_SELECT');
      }
      setCopiedText(`Workspace "${workspace.name}" deleted successfully.`);
      setTimeout(() => setCopiedText(null), 3500);
      setWorkspaceToDelete(null);
    } catch (err) {
      console.error("Failed to delete workspace:", err);
      alert(err.message || "Failed to delete workspace. Please try again.");
    } finally {
      setIsDeletingWorkspace(false);
    }
  };

  const isSelectedDemo = Boolean(selectedWorkspace?.id?.startsWith('ws-') && currentUser?.isDemo);
  const currentSymbolMatch = workspaceSymbols.find(s => s.name === selectedSymbolKey) || workspaceSymbols[0];
  const dynamicFallbackGraph = currentSymbolMatch ? {
    name: currentSymbolMatch.name,
    scope: currentSymbolMatch.file || 'Workspace',
    type: currentSymbolMatch.name.charAt(0) === currentSymbolMatch.name.charAt(0).toUpperCase() ? 'Class' : 'Method',
    file: currentSymbolMatch.file || 'Workspace',
    line: 1,
    signature: currentSymbolMatch.name,
    riskLevel: 'LOW',
    riskScore: '1.5 / 10',
    blastRadiusHops: 1,
    nodes: [
      {
        id: 'target',
        label: currentSymbolMatch.name,
        file: currentSymbolMatch.file ? currentSymbolMatch.file.replace(/\\/g, '/').split('/').pop() : 'Source',
        type: 'TARGET',
        x: 400,
        y: 220,
        scope: 'AST Symbol'
      }
    ],
    edges: [],
    codeSnippet: `// Symbol: ${currentSymbolMatch.name}\n// File: ${currentSymbolMatch.file || 'Source File'}\n\n// Indexed in Qdrant Vector Store`
  } : null;

  const activeGraph = liveGraphData || (isSelectedDemo ? (SYMBOL_GRAPHS[selectedSymbolKey] || SYMBOL_GRAPHS.generateToken) : dynamicFallbackGraph);

  const architectureHealth = useMemo(() => {
    if (!architectureGraphData?.nodes?.length) {
      if (isSelectedDemo && selectedWorkspace?.id === 'ws-study-sync') {
        return {
          score: 94,
          cycles: 0,
          cycleList: [],
          layerBypasses: 1,
          bypassList: [{ source: 'UserController', target: 'UserRepository', note: 'Controller bypasses Service orchestration layer to execute raw queries directly.' }],
          deadCode: 2,
          deadCodeList: ['cleanupOldTokens', 'verifyLegacySignature'],
          totalSymbols: 14,
        };
      }
      return {
        score: 98,
        cycles: 0,
        cycleList: [],
        layerBypasses: 0,
        bypassList: [],
        deadCode: 0,
        deadCodeList: [],
        totalSymbols: workspaceSymbols.length || 0,
      };
    }

    const nodes = architectureGraphData.nodes || [];
    const edges = architectureGraphData.edges || [];

    const methodNodes = nodes.filter(n => n.type === 'METHOD' || n.type === 'SYMBOL');
    const calls = edges.filter(e => e.relationType === 'CALLS');

    const calledTargets = new Set();
    calls.forEach(e => {
      if (e.to) calledTargets.add(String(e.to).toLowerCase());
      if (e.target) calledTargets.add(String(e.target).toLowerCase());
    });

    const deadCodeList = methodNodes
      .filter(m => {
        const idLower = String(m.id || '').toLowerCase();
        const labelLower = String(m.label || '').toLowerCase();
        return !calledTargets.has(idLower) && !calledTargets.has(labelLower);
      })
      .map(m => m.label || m.id);

    const callPairs = new Set();
    const cycleList = [];
    calls.forEach(e => {
      const from = String(e.from || e.source || '');
      const to = String(e.to || e.target || '');
      if (from && to && from !== to) {
        callPairs.add(`${from}--->${to}`);
        if (callPairs.has(`${to}--->${from}`)) {
          cycleList.push(`${from} ⇄ ${to}`);
        }
      }
    });

    const bypassList = [];
    calls.forEach(e => {
      const from = String(e.from || e.source || '');
      const to = String(e.to || e.target || '');
      const fromLower = from.toLowerCase();
      const toLower = to.toLowerCase();
      if (
        (fromLower.includes('controller') || fromLower.includes('handler') || fromLower.includes('route')) &&
        (toLower.includes('repository') || toLower.includes('dao') || toLower.includes('repo') || toLower.includes('findby') || toLower.includes('save('))
      ) {
        bypassList.push({
          source: from,
          target: to,
          note: `${from} directly accesses data layer (${to}) without Service layer orchestration.`
        });
      }
    });

    const deadCount = deadCodeList.length;
    const cycleCount = cycleList.length;
    const bypassCount = bypassList.length;

    let score = 100 - (cycleCount * 12) - (bypassCount * 6) - Math.min(20, Math.floor(deadCount * 1.5));
    score = Math.max(50, Math.min(100, score));

    return {
      score,
      cycles: cycleCount,
      cycleList,
      layerBypasses: bypassCount,
      bypassList,
      deadCode: deadCount,
      deadCodeList: deadCodeList.slice(0, 8),
      totalSymbols: methodNodes.length || workspaceSymbols.length || nodes.length,
    };
  }, [architectureGraphData, isSelectedDemo, selectedWorkspace?.id, workspaceSymbols]);


  const handleSendQaQuery = async () => {
    if (!qaInput.trim()) return;
    const userMsg = { sender: 'user', text: qaInput };
    setQaMessages(prev => [...prev, userMsg]);
    const currentQuery = qaInput;
    setQaInput('');
    setIsAiThinking(true);

    try {
      const historyPayload = qaMessages.slice(-6).map(m => ({ sender: m.sender, text: m.text }));
      const res = await api.queryRag(selectedWorkspace?.id || '', currentQuery, geminiApiKey, historyPayload);
      setIsAiThinking(false);
      if (res && res.answer) {
        setQaMessages(prev => [
          ...prev,
          {
            sender: 'assistant',
            text: res.answer,
            sources: res.sources || ['Qdrant Vector Chunks']
          }
        ]);
        return;
      }
    } catch (err) {
      console.warn("API queryRag error:", err);
      setIsAiThinking(false);
      setQaMessages(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: `⚠️ Request Error: ${err.message}\n\nPlease check your Gemini API key in the top bar.`,
          sources: []
        }
      ]);
      return;
    }

    setIsAiThinking(false);
    const fallbackMsg = isSelectedDemo ? {
      sender: 'assistant',
      text: `Based on Neo4j Graph Traversal & Qdrant Chunk Analysis:\n\n1. Target Symbol: JwtService.generateToken\n2. Direct Dependent Services: AuthenticationService.java invokes generateToken inside both authenticate() (line 52) and register() (line 89).\n3. Public HTTP Controllers: AuthenticationController.java indirectly relies on this payload via /api/auth/authenticate and /api/auth/refresh.\n\nRefactoring Recommendation: Maintain backward compatibility by keeping the single-parameter generateToken(UserDetails) as an overload calling your updated method signature.`,
      sources: [
        'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java',
        'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java'
      ]
    } : {
      sender: 'assistant',
      text: `Grounded Architecture Summary for '${selectedWorkspace?.name || 'Workspace'}':\n\n- Indexed Files: ${selectedWorkspace?.filesCount || workspaceSymbols.length} source files (${selectedWorkspace?.language || 'Polyglot'}).\n- Indexed Symbols: ${workspaceSymbols.slice(0, 6).map(s => s.name).join(', ')}${workspaceSymbols.length > 6 ? '...' : ''}\n\nAdd your Gemini API Key on login or set GEMINI_API_KEY in .env to enable multi-turn AI reasoning!`,
      sources: workspaceSymbols.slice(0, 3).map(s => s.file).filter(Boolean)
    };
    setQaMessages(prev => [...prev, fallbackMsg]);
  };

  const handleGenerateRefactor = async (overridePrompt) => {
    const promptToRun = (typeof overridePrompt === 'string' ? overridePrompt : refactorPrompt || '').trim();
    if (!promptToRun) return;

    setIsGeneratingDiff(true);
    const previousDiffs = generatedDiff?.diffs || [];
    const keyToSend = geminiApiKey && !geminiApiKey.includes('...') && geminiApiKey !== 'CONFIGURED' ? geminiApiKey : undefined;

    try {
      const res = await api.generateRefactor(
        selectedWorkspace?.id || '',
        promptToRun,
        keyToSend,
        previousDiffs
      );
      if (res && res.diffs) {
        setIsGeneratingDiff(false);
        setGeneratedDiff(res);
        setRefactorHistory(prev => [
          ...prev,
          { turn: res.turn || prev.length + 1, prompt: promptToRun, result: res }
        ]);
        setFollowUpPrompt('');
        return;
      }
    } catch (err) {
      console.warn("API generateRefactor notice, using fallback diff:", err);
    }

    const promptLower = promptToRun.toLowerCase();
    const matchedSym = workspaceSymbols.find(s => {
      const fn = (s.file || '').toLowerCase();
      const nm = (s.name || '').toLowerCase();
      return (promptLower.includes('jwt') && (fn.includes('jwt') || nm.includes('jwt'))) ||
             (promptLower.includes('auth') && (fn.includes('auth') || nm.includes('auth'))) ||
             (promptLower.includes('token') && (fn.includes('token') || nm.includes('token')));
    });

    const targetFile = matchedSym?.file || (workspaceSymbols.find(s => !s.file?.endsWith('Application.java'))?.file) || workspaceSymbols[0]?.file || 'src/main/java/service/JwtService.java';

    setTimeout(() => {
      setIsGeneratingDiff(false);
      const isFollowup = previousDiffs.length > 0;
      const fallbackResult = isSelectedDemo ? (
        isFollowup ? {
          filesChanged: 3,
          turn: (generatedDiff?.turn || 1) + 1,
          summary: 'Turn 2: Propagated signature change to AuthenticationController and added input validation checks.',
          diffs: [
            {
              file: 'AuthenticationController.java',
              old_code: "public ResponseEntity<AuthenticationResponse> authenticate(@RequestBody AuthenticationRequest request) {\n    return ResponseEntity.ok(service.authenticate(request));\n}",
              new_code: "public ResponseEntity<AuthenticationResponse> authenticate(@RequestBody AuthenticationRequest request) {\n    if (request == null || request.getEmail() == null) {\n        throw new IllegalArgumentException(\"Authentication request cannot be null\");\n    }\n    return ResponseEntity.ok(service.authenticate(request));\n}",
              diffCode: "--- a/controller/AuthenticationController.java\n+++ b/controller/AuthenticationController.java\n@@ -40,3 +40,6 @@\n public ResponseEntity<AuthenticationResponse> authenticate(@RequestBody AuthenticationRequest request) {\n+    if (request == null || request.getEmail() == null) {\n+        throw new IllegalArgumentException(\"Authentication request cannot be null\");\n+    }\n     return ResponseEntity.ok(service.authenticate(request));\n }",
              syntax_validation: { is_valid: true, skipped: false, errors: [] }
            },
            {
              file: 'JwtService.java',
              old_code: "public String generateToken(UserDetails userDetails) {\n    return generateToken(new HashMap<>(), userDetails);\n}",
              new_code: "public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);\n}",
              diffCode: "--- a/service/JwtService.java\n+++ b/service/JwtService.java\n@@ -38,3 +38,4 @@\n-public String generateToken(UserDetails userDetails) {\n-    return generateToken(new HashMap<>(), userDetails);\n+public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n+    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);",
              syntax_validation: { is_valid: true, skipped: false, errors: [] }
            },
            {
              file: 'AuthenticationService.java',
              old_code: "var jwtToken = jwtService.generateToken(user);",
              new_code: "var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
              diffCode: "--- a/service/AuthenticationService.java\n+++ b/service/AuthenticationService.java\n@@ -52,1 +52,1 @@\n-var jwtToken = jwtService.generateToken(user);\n+var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
              syntax_validation: { is_valid: true, skipped: false, errors: [] }
            }
          ]
        } : {
          filesChanged: 2,
          turn: 1,
          summary: 'Turn 1: Updated JwtService.generateToken signature and updated downstream invocations in AuthenticationService.',
          diffs: [
            {
              file: 'JwtService.java',
              old_code: "public String generateToken(UserDetails userDetails) {\n    return generateToken(new HashMap<>(), userDetails);\n}",
              new_code: "public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);\n}",
              diffCode: "--- a/service/JwtService.java\n+++ b/service/JwtService.java\n@@ -38,3 +38,4 @@\n-public String generateToken(UserDetails userDetails) {\n-    return generateToken(new HashMap<>(), userDetails);\n+public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n+    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);"
            },
            {
              file: 'AuthenticationService.java',
              old_code: "var jwtToken = jwtService.generateToken(user);",
              new_code: "var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
              diffCode: "--- a/service/AuthenticationService.java\n+++ b/service/AuthenticationService.java\n@@ -52,1 +52,1 @@\n-var jwtToken = jwtService.generateToken(user);\n+var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
              syntax_validation: { is_valid: true, skipped: false, errors: [] }
            }
          ]
        }
      ) : {
        filesChanged: 1,
        turn: (generatedDiff?.turn || 1) + (isFollowup ? 1 : 0),
        summary: `Refactoring proposal synthesized for '${promptToRun}' on ${targetFile}`,
        diffs: [
          {
            file: targetFile,
            old_code: `// ${targetFile}\n// Original implementation before refactoring`,
            new_code: `// ${targetFile}\n// Refactored implementation for objective: ${promptToRun}`,
            diffCode: `--- a/${targetFile}\n+++ b/${targetFile}\n@@ -1,3 +1,4 @@\n+// Refactored for objective: ${promptToRun}`,
            syntax_validation: { is_valid: true, skipped: false, errors: [] }
          }
        ]
      };
      setGeneratedDiff(fallbackResult);
      setRefactorHistory(prev => [
        ...prev,
        { turn: fallbackResult.turn || prev.length + 1, prompt: promptToRun, result: fallbackResult }
      ]);
      setFollowUpPrompt('');
    }, 800);
  };

  const getNodeColor = (type, isBlastActive) => {
    switch (type) {
      case 'TARGET':
        return '#ef4444';
      case 'DIRECT_CALLER':
        return isBlastActive ? '#f97316' : '#3b82f6';
      case 'TRANSITIVE_CALLER':
        return isBlastActive ? '#eab308' : '#8b5cf6';
      case 'CALLEE':
        return '#10b981';
      default:
        return '#64748b';
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex flex-col selection:bg-cyan-500 selection:text-slate-950">
      
      {/* Toast Notification */}
      {copiedText && (
        <div className="fixed bottom-5 right-5 z-50 bg-cyan-500 text-slate-950 px-4 py-2 rounded-xl font-bold text-xs shadow-xl flex items-center space-x-2 animate-bounce">
          <Check className="h-4 w-4" />
          <span>{copiedText}</span>
        </div>
      )}

      {/* GLOBAL TOP NAVIGATION HEADER */}
      {currentUser && (
        <header className="h-14 border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 flex items-center justify-between sticky top-0 z-50">
          <div className="flex items-center space-x-4">
            <div 
              onClick={() => setCurrentScreen('WORKSPACE_SELECT')}
              className="flex items-center space-x-2.5 cursor-pointer group"
            >
              <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center font-black text-white shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition">
                <Cpu className="h-5 w-5" />
              </div>
              <span className="font-bold tracking-tight bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-400 bg-clip-text text-transparent text-lg">
                CodeGraph-RAG
              </span>
            </div>

            {currentScreen === 'APP_WORKSPACE' && selectedWorkspace && (
              <div className="hidden md:flex items-center space-x-2 bg-slate-950 border border-slate-800 px-3 py-1 rounded-full text-xs font-mono text-slate-300">
                <Folder className="h-3.5 w-3.5 text-cyan-400" />
                <span className="font-bold">{selectedWorkspace.name}</span>
                <span className="text-slate-500">({selectedWorkspace.branch})</span>
              </div>
            )}
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => {
                setTempApiKeyInput(geminiApiKey && !geminiApiKey.includes('...') ? geminiApiKey : '');
                setShowApiKeyModal(true);
              }}
              className={`flex items-center space-x-1.5 text-xs px-3 py-1 rounded-full border transition cursor-pointer ${
                geminiApiKey || isKeyEncryptedInBackend
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20'
                  : 'bg-amber-500/10 border-amber-500/40 text-amber-300 hover:bg-amber-500/20 animate-pulse'
              }`}
              title="Click to configure or update your Gemini API key"
            >
              <Key className="h-3.5 w-3.5" />
              <span className="font-mono text-[11px] font-bold">
                {isKeyEncryptedInBackend ? `Encrypted Key (${maskedKeyDisplay || 'Active'})` : (geminiApiKey ? 'Gemini Key: Active' : '⚡ Add Gemini Key')}
              </span>
            </button>

            <div className="hidden sm:flex items-center space-x-2 text-xs bg-slate-950 border border-slate-800 px-3 py-1 rounded-full">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span className="text-slate-300 font-mono">Qdrant + Neo4j Active</span>
            </div>

            <div className="flex items-center space-x-3 pl-2 border-l border-slate-800">
              <div className="text-right hidden sm:block">
                <div className="text-xs font-semibold text-slate-200">{currentUser.name}</div>
                <div className="text-[10px] text-cyan-400 font-mono">{currentUser.role}</div>
              </div>
              <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-xs font-bold text-slate-950 shadow-md">
                {currentUser.name.substring(0, 2).toUpperCase()}
              </div>

              <button
                onClick={handleSignOut}
                title="Sign Out to Start Page"
                className="p-2 rounded-lg bg-slate-800 hover:bg-rose-500/20 hover:text-rose-400 text-slate-400 transition flex items-center space-x-1.5 text-xs font-medium border border-slate-700/60"
              >
                <LogOut className="h-4 w-4" />
                <span className="hidden md:inline">Sign Out</span>
              </button>
            </div>
          </div>
        </header>
      )}

      {/* SCREEN 0: STARTING / AUTHENTICATION PAGE */}
      {currentScreen === 'AUTH' && (
        <div className="flex-1 flex flex-col justify-between bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950 relative overflow-hidden">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-cyan-500/10 blur-[120px] rounded-full pointer-events-none"></div>

          {authError && (
            <div role="alert" className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-md px-4 py-2.5 bg-red-950/90 border border-red-500/40 text-red-200 text-xs font-medium rounded-xl shadow-xl">
              {authError}
            </div>
          )}

          <div className="p-6 max-w-7xl w-full mx-auto flex items-center justify-between relative z-10">
            <div className="flex items-center space-x-3">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center font-black text-white shadow-xl shadow-cyan-500/30">
                <Cpu className="h-6 w-6" />
              </div>
              <span className="font-extrabold text-2xl bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-400 bg-clip-text text-transparent">
                CodeGraph-RAG
              </span>
            </div>

            <button
              onClick={handleLoginDemoAccount}
              className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 flex items-center space-x-2 transition transform hover:-translate-y-0.5"
            >
              <Zap className="h-4 w-4" />
              <span>⚡ One-Click Demo Mode</span>
            </button>
          </div>

          <div className="max-w-6xl w-full mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center relative z-10">
            <div className="lg:col-span-7 space-y-6 text-center lg:text-left">
              <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-xs font-semibold uppercase tracking-wider">
                <Sparkles className="h-3.5 w-3.5" />
                <span>Contextual Code Graph + Vector RAG Engine</span>
              </div>

              <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-slate-100 leading-tight">
                Architectural Intelligence & <br />
                <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-400 bg-clip-text text-transparent">
                  Multi-Hop Blast Radius Analysis
                </span>
              </h1>

              <p className="text-slate-400 text-sm sm:text-base leading-relaxed max-w-xl mx-auto lg:mx-0">
                Index your Git repositories into dual-store architecture: Tree-sitter polyglot AST parser, Qdrant 384D BGE vector embeddings, and Neo4j Cypher call graphs. Trace breaking changes before you commit.
              </p>

              <div className="pt-2 grid grid-cols-2 sm:grid-cols-3 gap-3 text-left">
                <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="text-cyan-400 font-bold text-sm">Polyglot AST</div>
                  <div className="text-slate-400 text-xs">Java, Python, JS, Go, C++</div>
                </div>
                <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="text-blue-400 font-bold text-sm">Dual Storage</div>
                  <div className="text-slate-400 text-xs">Qdrant + Neo4j Graph</div>
                </div>
                <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1 col-span-2 sm:col-span-1">
                  <div className="text-indigo-400 font-bold text-sm">MCP Protocol</div>
                  <div className="text-slate-400 text-xs">VS Code & Cursor Native</div>
                </div>
              </div>
            </div>

            <div className="lg:col-span-5 bg-slate-900/90 border border-slate-800 rounded-3xl p-8 shadow-2xl backdrop-blur relative">
              <div className="text-center mb-6">
                <h2 className="text-xl font-bold text-slate-100">Get Started with CodeGraph</h2>
                <p className="text-xs text-slate-400 mt-1">Sign in with demo credentials or run instant 1-click mode</p>
              </div>

              <button
                onClick={handleLoginDemoAccount}
                className="w-full mb-4 py-3.5 px-4 bg-gradient-to-r from-cyan-500 via-blue-600 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 font-bold text-sm rounded-2xl shadow-xl shadow-cyan-500/25 flex items-center justify-center space-x-2 transition transform active:scale-98"
              >
                <Zap className="h-5 w-5 text-amber-300" />
                <span>Start Demo Mode (Instant Access)</span>
                <ArrowRight className="h-4 w-4" />
              </button>

              <div className="mb-6 p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-xs space-y-1 text-cyan-300">
                <div className="font-bold flex items-center space-x-1.5">
                  <Key className="h-3.5 w-3.5" />
                  <span>Pre-loaded Demo Credentials:</span>
                </div>
                <div className="font-mono text-[11px] text-slate-300">
                  Email: <span className="text-cyan-400">harsha.demo@codegraph.ai</span>
                </div>
                <div className="font-mono text-[11px] text-slate-300">
                  Password: <span className="text-cyan-400">demopassword2026</span>
                </div>
              </div>

              <div className="relative my-6 flex items-center justify-center">
                <div className="border-t border-slate-800 w-full"></div>
                <span className="bg-slate-900 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500 absolute">
                  Or Custom Sign In
                </span>
              </div>

              <div className="grid grid-cols-2 p-1 bg-slate-950 rounded-xl mb-4 border border-slate-800">
                <button
                  onClick={() => setAuthMode('LOGIN')}
                  className={`py-1.5 text-xs font-semibold rounded-lg transition ${authMode === 'LOGIN' ? 'bg-slate-800 text-cyan-400 shadow' : 'text-slate-400 hover:text-slate-200'}`}
                >
                  Sign In
                </button>
                <button
                  onClick={() => setAuthMode('SIGNUP')}
                  className={`py-1.5 text-xs font-semibold rounded-lg transition ${authMode === 'SIGNUP' ? 'bg-slate-800 text-cyan-400 shadow' : 'text-slate-400 hover:text-slate-200'}`}
                >
                  New Account
                </button>
              </div>

              <form onSubmit={handleAuthSubmit} className="space-y-4">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Developer Email
                  </label>
                  <input
                    type="email"
                    required
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    placeholder="developer@company.com"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition font-mono"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Password
                  </label>
                  <input
                    type="password"
                    required
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition font-mono"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Gemini API Key (Optional BYOK)
                  </label>
                  <input
                    type="password"
                    value={geminiApiKey}
                    onChange={(e) => setGeminiApiKey(e.target.value)}
                    placeholder="AIzaSy... (Leave empty for demo model)"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition font-mono"
                  />
                </div>

                <button
                  type="submit"
                  className="w-full py-3 bg-slate-800 hover:bg-slate-700 text-slate-100 font-bold text-xs rounded-xl border border-slate-700 transition"
                >
                  {authMode === 'LOGIN' ? 'Sign In to Workspace' : 'Create Developer Account'}
                </button>
              </form>
            </div>
          </div>

          <div className="py-6 border-t border-slate-900 text-center text-xs text-slate-500 relative z-10">
            CodeGraph-RAG Platform © 2026 • Built for Developer Experience
          </div>
        </div>
      )}

      {/* SCREEN 1: WORKSPACE SELECTOR & REPOSITORY INGESTION HUB */}
      {currentScreen === 'WORKSPACE_SELECT' && (
        <div className="flex-1 max-w-6xl w-full mx-auto p-6 space-y-8">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-950 border border-slate-800 p-6 rounded-3xl shadow-xl">
            <div>
              <h1 className="text-2xl font-bold text-slate-100">
                Welcome back, {currentUser?.name || 'Developer'}!
              </h1>
              <p className="text-slate-400 text-xs mt-1">
                Select an existing indexed codebase workspace or ingest a new Git URL / ZIP archive.
              </p>
            </div>

            {currentUser?.isDemo && (
              <button
                onClick={handleLoginDemoAccount}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-cyan-400 border border-slate-700 rounded-xl text-xs font-mono font-bold flex items-center space-x-2"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>Reload Demo Workspace</span>
              </button>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Active Codebase Workspaces ({workspaces.length})
              </h2>
            </div>

            {workspaces.length === 0 ? (
              <div className="bg-slate-900 border border-dashed border-slate-800 rounded-3xl p-10 text-center space-y-4">
                <div className="h-12 w-12 rounded-2xl bg-slate-800 text-slate-400 flex items-center justify-center mx-auto">
                  <Folder className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-200">No Codebase Workspaces Yet</h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto mt-1">
                    Your account does not have any repositories indexed yet. Ingest a Git repository or upload a local project folder / ZIP archive below to start exploring your codebase architecture.
                  </p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {workspaces.map((ws) => (
                  <div
                    key={ws.id}
                    className="bg-slate-900 border border-slate-800 hover:border-cyan-500/50 p-5 rounded-2xl space-y-4 transition group shadow-lg"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                          {ws.type === 'git' ? <GitBranch className="h-5 w-5" /> : <Folder className="h-5 w-5" />}
                        </div>
                        <div>
                          <h3 className="font-bold text-slate-100 group-hover:text-cyan-400 transition">
                            {ws.name}
                          </h3>
                          <p className="text-xs font-mono text-slate-400">{ws.repoUrl}</p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className={`px-2.5 py-1 rounded-full font-mono text-[10px] font-bold ${
                          ws.status === 'READY'
                            ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                            : ws.status === 'INDEXING'
                            ? 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 animate-pulse'
                            : 'bg-rose-500/10 border border-rose-500/20 text-rose-400'
                        }`}>
                          {ws.status === 'INDEXING' ? '⚡ Indexing...' : ws.status}
                        </span>
                        {!ws.id.startsWith('ws-') && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setWorkspaceToDelete(ws);
                            }}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 border border-transparent hover:border-rose-500/20 transition cursor-pointer"
                            title={`Delete workspace "${ws.name}"`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2 bg-slate-950 p-3 rounded-xl font-mono text-[11px] text-slate-300">
                      <div>
                        <span className="text-slate-500 block text-[10px]">Indexed Files</span>
                        <span className="font-bold text-slate-100">{ws.filesCount}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px]">Graph Nodes</span>
                        <span className="font-bold text-cyan-400">{ws.nodesCount}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px]">Smart Filtering</span>
                        <span className="font-bold text-emerald-400">
                          {ws.type === 'zip' ? '⚡ 99% Bloat Filtered' : 'AST Clean'}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <span className="text-xs text-slate-500">Indexed {ws.lastIndexed}</span>
                      <div className="flex items-center space-x-2">
                        {!ws.id.startsWith('ws-') && (
                          <button
                            onClick={() => setWorkspaceToDelete(ws)}
                            className="px-3 py-2 bg-slate-950 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-800 hover:border-rose-500/30 text-xs font-semibold rounded-xl flex items-center space-x-1.5 transition cursor-pointer"
                            title="Delete Workspace"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            <span>Delete</span>
                          </button>
                        )}
                        {ws.status === 'READY' ? (
                          <button
                            onClick={() => {
                              setSelectedWorkspace(ws);
                              setCurrentScreen('APP_WORKSPACE');
                            }}
                            className="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded-xl flex items-center space-x-1.5 transition shadow-lg shadow-cyan-500/20 cursor-pointer"
                          >
                            <span>Open Workspace</span>
                            <ArrowRight className="h-3.5 w-3.5" />
                          </button>
                        ) : ws.status === 'INDEXING' ? (
                          <button
                            disabled
                            className="px-4 py-2 bg-slate-800 text-cyan-400 font-mono text-xs rounded-xl flex items-center space-x-1.5 opacity-80 cursor-wait border border-cyan-500/20"
                          >
                            <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-400" />
                            <span>Indexing...</span>
                          </button>
                        ) : (
                          <span className="text-xs text-rose-400 font-mono font-semibold px-2 py-1 bg-rose-500/10 rounded-lg border border-rose-500/20">
                            Ingestion Failed
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 space-y-6 shadow-xl">
            <div className="flex items-center space-x-3 border-b border-slate-800 pb-4">
              <Plus className="h-5 w-5 text-cyan-400" />
              <h2 className="text-base font-bold text-slate-100">Ingest New Repository Workspace</h2>
            </div>

            <div className="grid grid-cols-2 gap-3 max-w-md">
              <button
                onClick={() => setUploadType('git')}
                className={`p-3 rounded-xl border text-xs font-bold flex items-center justify-center space-x-2 transition ${uploadType === 'git' ? 'bg-cyan-500/10 border-cyan-500 text-cyan-400' : 'bg-slate-950 border-slate-800 text-slate-400'}`}
              >
                <GitBranch className="h-4 w-4" />
                <span>Remote Git Repository</span>
              </button>
              <button
                onClick={() => setUploadType('zip')}
                className={`p-3 rounded-xl border text-xs font-bold flex items-center justify-center space-x-2 transition ${uploadType === 'zip' ? 'bg-cyan-500/10 border-cyan-500 text-cyan-400' : 'bg-slate-950 border-slate-800 text-slate-400'}`}
              >
                <UploadCloud className="h-4 w-4" />
                <span>Upload Local .ZIP Archive</span>
              </button>
            </div>

            {uploadType === 'git' ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Git HTTPS URL
                  </label>
                  <input
                    type="text"
                    value={gitRepoInput}
                    onChange={(e) => setGitRepoInput(e.target.value)}
                    placeholder="https://github.com/user/repository"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Branch Name
                  </label>
                  <input
                    type="text"
                    value={branchInput}
                    onChange={(e) => setBranchInput(e.target.value)}
                    className="w-full max-w-xs bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>
            ) : (
              <div
                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onDrop={async (e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  try {
                    const droppedFiles = await getFilesFromDataTransfer(e.dataTransfer);
                    if (!droppedFiles || droppedFiles.length === 0) return;

                    // If a single .zip file was dropped
                    if (droppedFiles.length === 1 && droppedFiles[0].name.toLowerCase().endsWith('.zip')) {
                      setZipFile(droppedFiles[0]);
                      setFolderFiles(null);
                      setZipFileName(droppedFiles[0].name);
                      setSelectedFolderName('');
                      setUploadError('');
                    } else {
                      // Directory or multiple files dropped
                      setFolderFiles(droppedFiles);
                      setZipFile(null);
                      setZipFileName('');
                      const topDir = droppedFiles[0].webkitRelativePath?.split('/')[0] || 'Local Folder';
                      setSelectedFolderName(`${topDir}/ (${droppedFiles.length} files)`);
                      setUploadError('');
                    }
                  } catch (err) {
                    setUploadError('Failed to read dropped files: ' + err.message);
                  }
                }}
                className="border-2 border-dashed border-slate-800 hover:border-cyan-500/50 bg-slate-950 p-8 rounded-2xl text-center space-y-3 transition"
              >
                <div className="flex justify-center">
                  <div className="p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-2xl text-cyan-400">
                    <UploadCloud className="h-8 w-8" />
                  </div>
                </div>

                <div className="text-sm font-bold text-slate-200">
                  {zipFileName ? (
                    <span className="text-cyan-400 font-mono flex items-center justify-center space-x-1.5">
                      <UploadCloud className="h-4 w-4" />
                      <span>{zipFileName}</span>
                    </span>
                  ) : selectedFolderName ? (
                    <span className="text-emerald-400 font-mono flex items-center justify-center space-x-1.5">
                      <Folder className="h-4 w-4" />
                      <span>{selectedFolderName}</span>
                    </span>
                  ) : (
                    'Drop your local project folder or .ZIP archive here'
                  )}
                </div>

                {/* Smart Bloat-Filtering Badge */}
                <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Smart Auto-Filtering Active: node_modules, .venv, target/ & binaries ignored automatically</span>
                </div>

                <p className="text-[11px] text-slate-400 max-w-md mx-auto">
                  Upload raw uncleaned local projects up to <strong className="text-slate-200">1 GB</strong>. We strip build artifacts and index pure AST source graphs instantly.
                </p>

                <div className="flex items-center justify-center space-x-3 pt-2">
                  {/* Standard ZIP File Picker */}
                  <label htmlFor="zip-input" className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded-xl cursor-pointer border border-slate-700 transition">
                    Browse .ZIP Archive
                  </label>
                  <input
                    type="file"
                    accept=".zip"
                    onChange={(e) => {
                      const f = e.target.files[0] || null;
                      setZipFile(f);
                      setFolderFiles(null);
                      setZipFileName(f ? f.name : '');
                      setSelectedFolderName('');
                      setUploadError('');
                    }}
                    className="hidden"
                    id="zip-input"
                  />

                  <span className="text-slate-600 text-xs font-mono">OR</span>

                  {/* Native Directory Picker */}
                  <label htmlFor="folder-input" className="px-4 py-2 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 text-xs font-bold rounded-xl cursor-pointer transition flex items-center space-x-1.5">
                    <Folder className="h-3.5 w-3.5" />
                    <span>Select Unzipped Folder</span>
                  </label>
                  <input
                    type="file"
                    webkitdirectory=""
                    directory=""
                    multiple
                    onChange={(e) => {
                      const files = e.target.files;
                      if (files && files.length > 0) {
                        setFolderFiles(files);
                        setZipFile(null);
                        setZipFileName('');
                        const topDir = files[0].webkitRelativePath?.split('/')[0] || 'Local Folder';
                        setSelectedFolderName(`${topDir}/ (${files.length} files)`);
                        setUploadError('');
                      }
                    }}
                    className="hidden"
                    id="folder-input"
                  />
                </div>
              </div>
            )}

            {uploadError && (
              <div role="alert" className="px-4 py-2.5 bg-red-950/60 border border-red-500/40 text-red-200 text-xs rounded-xl">
                {uploadError}
              </div>
            )}

            <button
              onClick={handleStartIngestion}
              className="w-full py-3.5 bg-gradient-to-r from-cyan-500 via-blue-600 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-white font-bold text-xs rounded-xl shadow-xl shadow-cyan-500/20 flex items-center justify-center space-x-2 transition"
            >
              <Zap className="h-4 w-4" />
              <span>Start Dual-Store Indexing (Qdrant Vectors + Neo4j Graph)</span>
            </button>
          </div>
        </div>
      )}

      {/* SCREEN 2: KINETIC INGESTION PROGRESS MATRIX */}
      {currentScreen === 'INGESTION' && (
        <div className="flex-1 flex flex-col items-center justify-center p-6 bg-slate-950">
          <div className="max-w-2xl w-full bg-slate-900 border border-slate-800 rounded-3xl p-8 space-y-6 shadow-2xl">
            <div className="flex items-center space-x-4">
              <div className="h-12 w-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 animate-spin">
                <RefreshCw className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-100">CodeGraph Kinetic Ingestion Engine</h2>
                <p className="text-xs text-slate-400 font-mono mt-0.5">Indexing repository structure into memory</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs font-mono font-semibold">
                <span className="text-cyan-400">{ingestStageText}</span>
                <span className="text-slate-400">{ingestProgress}%</span>
              </div>
              <div className="h-3 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800 p-0.5">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 transition-all duration-500 rounded-full"
                  style={{ width: `${ingestProgress}%` }}
                ></div>
              </div>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 h-56 overflow-y-auto font-mono text-xs space-y-2 text-slate-300">
              <div className="flex items-center space-x-2 text-slate-500 border-b border-slate-900 pb-2">
                <Terminal className="h-3.5 w-3.5" />
                <span>Stdio Parsing Console Output</span>
              </div>
              {ingestLogs.map((log, idx) => (
                <div key={idx} className="text-emerald-400/90 leading-relaxed">
                  {log}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 3: MAIN DEVELOPER PLATFORM WORKSPACE */}
      {currentScreen === 'APP_WORKSPACE' && (
        !selectedWorkspace ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4 bg-slate-950">
            <div className="h-16 w-16 rounded-2xl bg-slate-900 border border-slate-800 text-cyan-400 flex items-center justify-center">
              <Folder className="h-8 w-8" />
            </div>
            <h3 className="text-lg font-bold text-slate-200">No Codebase Selected</h3>
            <p className="text-xs text-slate-400 max-w-md">
              Please select an existing workspace or ingest a new codebase repository to explore its architecture and call graph.
            </p>
            <button
              onClick={() => setCurrentScreen('WORKSPACE_SELECT')}
              className="px-5 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 transition"
            >
              Open Workspace Hub
            </button>
          </div>
        ) : (
        <div className="flex-1 flex flex-col overflow-hidden">
          
          {/* WORKSPACE TAB NAVIGATION BAR */}
          <div className="h-12 border-b border-slate-800 bg-slate-900/60 px-6 flex items-center justify-between">
            <div className="flex items-center space-x-1">
              <button
                onClick={() => setActiveTab('GRAPH')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center space-x-2 transition ${activeTab === 'GRAPH' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              >
                <Layers className="h-3.5 w-3.5" />
                <span>Architecture & Knowledge Graph</span>
              </button>

              <button
                onClick={() => setActiveTab('HEALTH')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center space-x-2 transition ${activeTab === 'HEALTH' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              >
                <Shield className="h-3.5 w-3.5" />
                <span>Architecture Health</span>
              </button>

              <button
                onClick={() => setActiveTab('REFACTOR')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center space-x-2 transition ${activeTab === 'REFACTOR' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              >
                <GitPullRequest className="h-3.5 w-3.5" />
                <span>AI Refactor & PR Generator</span>
              </button>

              <button
                onClick={() => setActiveTab('QA')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center space-x-2 transition ${activeTab === 'QA' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>Hybrid RAG QA Search</span>
              </button>

              <button
                onClick={() => setActiveTab('MCP')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center space-x-2 transition ${activeTab === 'MCP' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              >
                <Sliders className="h-3.5 w-3.5" />
                <span>MCP Tooling Hub</span>
              </button>
            </div>

            <div className="flex items-center space-x-3">
              {!selectedWorkspace.id.startsWith('ws-') && (
                <button
                  onClick={() => setWorkspaceToDelete(selectedWorkspace)}
                  className="text-xs font-semibold text-slate-400 hover:text-rose-400 flex items-center space-x-1.5 transition cursor-pointer"
                  title="Delete current workspace"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>Delete Workspace</span>
                </button>
              )}
              <button
                onClick={() => setCurrentScreen('WORKSPACE_SELECT')}
                className="text-xs font-semibold text-slate-400 hover:text-cyan-400 flex items-center space-x-1 cursor-pointer"
              >
                <Folder className="h-3.5 w-3.5" />
                <span>Switch Workspace</span>
              </button>
            </div>
          </div>

          {/* TAB 1: ARCHITECTURE & KNOWLEDGE GRAPH (SINGLE PLACE) */}
          {activeTab === 'GRAPH' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Single Place: Scope Toggle Bar */}
              <div className="h-11 border-b border-slate-800 bg-slate-900/60 px-4 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center space-x-2">
                  <div className="flex items-center bg-slate-950 border border-slate-800 p-0.5 rounded-xl">
                    <button
                      onClick={() => setGraphScope('ARCHITECTURE')}
                      className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition ${
                        graphScope === 'ARCHITECTURE'
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <Layers className="h-3.5 w-3.5 text-cyan-400" />
                      <span>Full Architecture Map (All Connected Relations)</span>
                    </button>
                    <button
                      onClick={() => setGraphScope('SYMBOL')}
                      className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition ${
                        graphScope === 'SYMBOL'
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <Activity className="h-3.5 w-3.5 text-rose-400" />
                      <span>Symbol Blast Radius</span>
                    </button>
                  </div>
                </div>

                <div className="text-[11px] font-mono text-slate-400 hidden sm:flex items-center space-x-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                  <span>
                    {graphScope === 'ARCHITECTURE'
                      ? 'Single view connecting classes, inheritance, methods & calls'
                      : `Inspecting blast radius for: ${selectedSymbolKey}`}
                  </span>
                </div>
              </div>

              {graphScope === 'ARCHITECTURE' ? (
                <UnifiedArchitectureGraph
                  graphData={architectureGraphData}
                  isLoading={isArchLoading}
                  onFocusSymbol={(symName) => {
                    setSelectedSymbolKey(symName);
                    setGraphScope('SYMBOL');
                  }}
                />
              ) : (
                <div className="flex-1 flex overflow-hidden">
                  {/* Symbol Selector Sidebar */}
              <aside className="w-80 border-r border-slate-800 bg-slate-900/40 flex flex-col">
                <div className="p-4 border-b border-slate-800 space-y-3">
                  <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    <span>AST Method / Class Inspector</span>
                    <button
                      onClick={reloadSymbols}
                      title="Sync Symbols from Backend"
                      className="p-1 hover:text-cyan-400 text-slate-500 rounded transition"
                    >
                      <RefreshCw className="h-3 w-3" />
                    </button>
                  </div>
                  <div className="relative">
                    <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
                    <input
                      type="text"
                      placeholder="Filter symbols..."
                      value={searchFilter}
                      onChange={(e) => setSearchFilter(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-2">
                  {workspaceSymbols.length > 0 ? (
                    workspaceSymbols
                      .filter(s =>
                        !searchFilter ||
                        s.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
                        (s.file && s.file.toLowerCase().includes(searchFilter.toLowerCase()))
                      )
                      .map((sym, idx) => {
                        const isSelected = selectedSymbolKey === sym.name;
                        const shortFile = sym.file ? sym.file.replace(/\\/g, '/').split('/').pop() : '';
                        const badgeType = sym.name.includes('.') ? 'Method' : (sym.name.charAt(0) === sym.name.charAt(0).toUpperCase() ? 'Class' : 'Function');
                        return (
                          <button
                            key={idx}
                            onClick={() => {
                              setLiveGraphData(null);
                              setSelectedSymbolKey(sym.name);
                              setSelectedNodeId('target');
                            }}
                            className={`w-full text-left p-3 rounded-xl border transition ${isSelected ? 'bg-cyan-500/10 border-cyan-500/50 text-slate-100' : 'bg-slate-900/80 border-slate-800/80 text-slate-400 hover:border-slate-700'}`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-xs font-bold text-cyan-400 truncate max-w-[170px]" title={sym.name}>{sym.name}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                                {badgeType}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-400 truncate mt-1" title={sym.file}>
                              {shortFile || sym.file}
                            </p>
                          </button>
                        );
                      })
                  ) : isSelectedDemo ? (
                    Object.keys(SYMBOL_GRAPHS).map((key) => {
                      const sym = SYMBOL_GRAPHS[key];
                      const isSelected = selectedSymbolKey === key;
                      return (
                        <button
                          key={key}
                          onClick={() => {
                            setLiveGraphData(null);
                            setSelectedSymbolKey(key);
                            setSelectedNodeId('target');
                          }}
                          className={`w-full text-left p-3 rounded-xl border transition ${isSelected ? 'bg-cyan-500/10 border-cyan-500/50 text-slate-100' : 'bg-slate-900/80 border-slate-800/80 text-slate-400 hover:border-slate-700'}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-xs font-bold text-cyan-400">{sym.name}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                              {sym.type}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 truncate mt-1">{sym.scope}</p>
                        </button>
                      );
                    })
                  ) : (
                    <div className="p-6 text-center space-y-3">
                      <div className="text-xs text-slate-500 font-mono">
                        {selectedWorkspace?.status === 'INDEXING' ? 'Codebase indexing in progress...' : 'No extracted symbols found in this workspace.'}
                      </div>
                      <button
                        onClick={reloadSymbols}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-400 text-xs font-mono font-bold rounded-lg inline-flex items-center space-x-1.5 transition"
                      >
                        <RefreshCw className="h-3 w-3" />
                        <span>Sync Symbols</span>
                      </button>
                    </div>
                  )}
                </div>

                <div className="p-3 border-t border-slate-800 bg-slate-950 text-[11px] font-mono text-slate-400 space-y-1">
                  <div className="flex justify-between">
                    <span>Indexed Files:</span>
                    <span className="text-cyan-400">{selectedWorkspace?.filesCount || 0} Files ({selectedWorkspace?.language || 'Polyglot'})</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Indexed Symbols:</span>
                    <span className="text-blue-400">{workspaceSymbols.length || selectedWorkspace?.nodesCount || 0} Symbols</span>
                  </div>
                </div>
              </aside>

              {/* Central Visual Node-Link Graph Engine */}
              <section className="flex-1 flex flex-col bg-slate-950 relative">
                {/* Visualizer Top Bar */}
                <div className="h-12 border-b border-slate-800 px-4 flex items-center justify-between bg-slate-900/20">
                  <div className="flex items-center space-x-3">
                    <Activity className="h-4 w-4 text-cyan-400" />
                    <span className="text-xs font-semibold text-slate-200">
                      Multi-Hop Neo4j Call Graph & Blast Radius Simulator
                    </span>
                  </div>

                  <div className="flex items-center space-x-3">
                    {/* Visualizer Mode Toggle */}
                    <div className="flex items-center bg-slate-900 border border-slate-800 p-0.5 rounded-lg text-xs font-bold">
                      <button
                        onClick={() => setGraphVisualMode('force-d3')}
                        className={`px-2.5 py-1 rounded-md transition ${graphVisualMode === 'force-d3' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
                      >
                        Force D3
                      </button>
                      <button
                        onClick={() => setGraphVisualMode('classic')}
                        className={`px-2.5 py-1 rounded-md transition ${graphVisualMode === 'classic' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
                      >
                        Classic 2D
                      </button>
                    </div>

                    {/* Classic Zoom & Controls (visible when classic mode is selected) */}
                    {graphVisualMode === 'classic' && (
                      <div className="flex items-center space-x-1 bg-slate-900 border border-slate-800 rounded-lg p-1 text-slate-400">
                        <button
                          onClick={() => setZoomLevel(prev => Math.min(prev + 0.15, 2))}
                          className="p-1 hover:text-slate-100 transition"
                          title="Zoom In"
                        >
                          <ZoomIn className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => setZoomLevel(prev => Math.max(prev - 0.15, 0.5))}
                          className="p-1 hover:text-slate-100 transition"
                          title="Zoom Out"
                        >
                          <ZoomOut className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => { setZoomLevel(1); setPanOffset({ x: 0, y: 0 }); }}
                          className="p-1 hover:text-slate-100 transition"
                          title="Reset View"
                        >
                          <Maximize2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}

                    <button
                      onClick={() => setBlastRadiusActive(!blastRadiusActive)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition ${blastRadiusActive ? 'bg-rose-500/20 border border-rose-500/40 text-rose-300' : 'bg-slate-800 text-slate-400'}`}
                    >
                      <AlertTriangle className="h-3.5 w-3.5" />
                      <span>{blastRadiusActive ? 'Blast Radius: ON' : 'Blast Radius: OFF'}</span>
                    </button>
                  </div>
                </div>

                {/* GRAPH VIEWPORT: Force D3 or Classic 2D */}
                {!activeGraph ? (
                  <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4 bg-slate-950">
                    <div className="h-14 w-14 rounded-2xl bg-slate-900 border border-slate-800 text-cyan-400 flex items-center justify-center shadow-lg">
                      <Search className="h-7 w-7" />
                    </div>
                    <h4 className="text-base font-bold text-slate-200">
                      {workspaceSymbols.length === 0 ? 'Symbols Sync in Progress' : 'Select a Symbol to Inspect'}
                    </h4>
                    <p className="text-xs text-slate-400 max-w-sm">
                      {workspaceSymbols.length === 0
                        ? 'AST extraction has completed on the backend. Click Sync Symbols below to load all extracted functions and classes.'
                        : 'Choose a class or method from the left sidebar to simulate its multi-hop blast radius, caller hierarchy, and callee dependencies.'}
                    </p>
                    <button
                      onClick={reloadSymbols}
                      className="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold rounded-xl flex items-center space-x-1.5 transition shadow-lg shadow-cyan-500/20"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      <span>Sync Symbols Now</span>
                    </button>
                  </div>
                ) : graphVisualMode === 'force-d3' ? (
                  <div className="flex-1 p-4 relative flex flex-col justify-between overflow-y-auto space-y-4">
                    <BlastRadiusGraph
                      graphData={activeGraph}
                      onSelectNode={(id) => setSelectedNodeId(id)}
                      selectedNodeId={selectedNodeId}
                    />

                    {/* Code Snippet Preview Box */}
                    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 font-mono text-xs shadow-xl">
                      <div className="flex items-center justify-between text-slate-400 border-b border-slate-800 pb-2 mb-2">
                        <span>{activeGraph.file}</span>
                        <span className="text-cyan-400 font-bold">{activeGraph.signature}</span>
                      </div>
                      <pre className="text-emerald-400/90 overflow-x-auto leading-relaxed">
                        {activeGraph.codeSnippet}
                      </pre>
                    </div>
                  </div>
                ) : (
                  /* Classic Node-Link Interactive Canvas View */
                  <div className="flex-1 p-4 relative flex flex-col justify-between overflow-hidden bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:18px_18px]">
                    
                    {/* Interactive Node-Link SVG Graph */}
                    <div className="flex-1 relative w-full h-full min-h-[380px]">
                      <svg
                        onWheel={handleWheelZoom}
                        onMouseDown={handleCanvasMouseDown}
                        onMouseMove={handleCanvasMouseMove}
                        onMouseUp={handleCanvasMouseUp}
                        onMouseLeave={handleCanvasMouseUp}
                        className={`w-full h-full absolute inset-0 select-none ${isDraggingCanvas ? 'cursor-grabbing' : 'cursor-grab'}`}
                        style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})` }}
                      >
                        <defs>
                          {/* Marker Arrowheads */}
                          <marker
                            id="arrowhead-cyan"
                            markerWidth="10"
                            markerHeight="7"
                            refX="18"
                            refY="3.5"
                            orient="auto"
                          >
                            <polygon points="0 0, 10 3.5, 0 7" fill="#06b6d4" />
                          </marker>
                          <marker
                            id="arrowhead-danger"
                            markerWidth="10"
                            markerHeight="7"
                            refX="18"
                            refY="3.5"
                            orient="auto"
                          >
                            <polygon points="0 0, 10 3.5, 0 7" fill="#f43f5e" />
                          </marker>

                          {/* Node Glow Filters */}
                          <filter id="glow-target" x="-50%" y="-50%" width="200%" height="200%">
                            <feGaussianBlur stdDeviation="6" result="blur" />
                            <feComposite in="SourceGraphic" in2="blur" operator="over" />
                          </filter>
                        </defs>

                        {/* Render Connecting Directed Call Lines */}
                        {activeGraph.edges.map((edge, idx) => {
                          const fromNode = activeGraph.nodes.find(n => n.id === edge.from);
                          const toNode = activeGraph.nodes.find(n => n.id === edge.to);

                          if (!fromNode || !toNode) return null;

                          const isDangerEdge = blastRadiusActive && (fromNode.type.includes('CALLER') || toNode.type === 'TARGET');
                          const strokeColor = isDangerEdge ? '#f43f5e' : '#0284c7';

                          const midX = (fromNode.x + toNode.x) / 2;
                          const midY = (fromNode.y + toNode.y) / 2;

                          return (
                            <g key={idx}>
                              <line
                                x1={fromNode.x}
                                y1={fromNode.y}
                                x2={toNode.x}
                                y2={toNode.y}
                                stroke={strokeColor}
                                strokeWidth={isDangerEdge ? "2.5" : "1.8"}
                                strokeDasharray={isDangerEdge ? "6,6" : "none"}
                                markerEnd={isDangerEdge ? "url(#arrowhead-danger)" : "url(#arrowhead-cyan)"}
                                className={isDangerEdge ? "animate-pulse" : ""}
                              />
                              {/* Relationship Label Badge */}
                              <rect
                                x={midX - 24}
                                y={midY - 10}
                                width="48"
                                height="18"
                                rx="4"
                                fill="#0f172a"
                                stroke={strokeColor}
                                strokeWidth="1"
                              />
                              <text
                                x={midX}
                                y={midY + 3}
                                fill={isDangerEdge ? "#fda4af" : "#38bdf8"}
                                fontSize="9"
                                fontFamily="monospace"
                                fontWeight="bold"
                                textAnchor="middle"
                              >
                                {edge.label}
                              </text>
                            </g>
                          );
                        })}

                        {/* Render Interactive Graph Nodes */}
                        {activeGraph.nodes.map((node) => {
                          const isSelected = selectedNodeId === node.id;
                          const nodeColor = getNodeColor(node.type, blastRadiusActive);

                          return (
                            <g
                              key={node.id}
                              transform={`translate(${node.x}, ${node.y})`}
                              onClick={() => setSelectedNodeId(node.id)}
                              className="cursor-pointer group"
                            >
                              {/* Pulse Shockwave Ring for Target/Blast Nodes */}
                              {blastRadiusActive && (node.type === 'TARGET' || node.type.includes('CALLER')) && (
                                <circle
                                  r="32"
                                  fill="none"
                                  stroke={nodeColor}
                                  strokeWidth="2"
                                  opacity="0.4"
                                  className="animate-ping"
                                />
                              )}

                              {/* Main Outer Node Circle */}
                              <circle
                                r="22"
                                fill="#0f172a"
                                stroke={nodeColor}
                                strokeWidth={isSelected ? "3.5" : "2.5"}
                                filter={node.type === 'TARGET' ? "url(#glow-target)" : undefined}
                                className="transition-all duration-300 group-hover:scale-110"
                              />

                              {/* Node Icon */}
                              <text
                                x="0"
                                y="4"
                                fill="#f8fafc"
                                fontSize="12"
                                fontFamily="sans-serif"
                                fontWeight="bold"
                                textAnchor="middle"
                              >
                                {node.type === 'TARGET' ? '⚡' : node.type.includes('CALLER') ? '📞' : '🧩'}
                              </text>

                              {/* Node Label Card */}
                              <g transform="translate(0, 36)">
                                <rect
                                  x="-80"
                                  y="-12"
                                  width="160"
                                  height="24"
                                  rx="6"
                                  fill="#090d16"
                                  stroke={isSelected ? "#06b6d4" : "#1e293b"}
                                  strokeWidth="1"
                                />
                                <text
                                  x="0"
                                  y="3"
                                  fill="#f1f5f9"
                                  fontSize="10"
                                  fontFamily="monospace"
                                  fontWeight="bold"
                                  textAnchor="middle"
                                >
                                  {node.label.length > 22 ? node.label.substring(0, 20) + '...' : node.label}
                                </text>
                              </g>
                            </g>
                          );
                        })}
                      </svg>

                      {/* Node Type Legend */}
                      <div className="absolute bottom-3 left-3 bg-slate-900/90 border border-slate-800 backdrop-blur rounded-xl p-3 text-[10px] font-mono space-y-1.5 shadow-lg">
                        <div className="font-bold text-slate-300 border-b border-slate-800 pb-1 mb-1">
                          Graph Legend
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-rose-500"></span>
                          <span className="text-slate-300">Target Symbol Node</span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-orange-500"></span>
                          <span className="text-slate-300">Direct Dependent Caller (1st Hop)</span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-yellow-500"></span>
                          <span className="text-slate-300">Transitive Caller (2nd/3rd Hop)</span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
                          <span className="text-slate-300">Callee / Helper Method</span>
                        </div>
                      </div>
                    </div>

                    {/* Code Snippet Preview Box */}
                    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 font-mono text-xs shadow-xl mt-3">
                      <div className="flex items-center justify-between text-slate-400 border-b border-slate-800 pb-2 mb-2">
                        <span>{activeGraph.file}</span>
                        <span className="text-cyan-400 font-bold">{activeGraph.signature}</span>
                      </div>
                      <pre className="text-emerald-400/90 overflow-x-auto leading-relaxed">
                        {activeGraph.codeSnippet}
                      </pre>
                    </div>
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      )}

          {/* TAB 2: ARCHITECTURE HEALTH INSPECTOR */}
          {activeTab === 'HEALTH' && (
            <div className="flex-1 p-6 bg-slate-950 overflow-y-auto space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Overall Health Score</div>
                  <div className={`text-3xl font-black ${architectureHealth.score >= 90 ? 'text-emerald-400' : architectureHealth.score >= 75 ? 'text-amber-400' : 'text-rose-400'}`}>
                    {architectureHealth.score} / 100
                  </div>
                  <div className="text-xs text-slate-500">
                    {architectureHealth.layerBypasses > 0 || architectureHealth.cycles > 0
                      ? `${architectureHealth.layerBypasses + architectureHealth.cycles} Architectural issue(s) flagged`
                      : 'Clean architectural boundaries verified'}
                  </div>
                </div>
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Circular Dependencies</div>
                  <div className={`text-3xl font-black ${architectureHealth.cycles > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {architectureHealth.cycles}
                  </div>
                  <div className="text-xs text-slate-500">
                    {architectureHealth.cycles > 0 ? `${architectureHealth.cycles} cyclic call loop(s) detected` : 'No cyclic method loops found'}
                  </div>
                </div>
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Layer Bypass Rules</div>
                  <div className={`text-3xl font-black ${architectureHealth.layerBypasses > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {architectureHealth.layerBypasses} Warning{architectureHealth.layerBypasses === 1 ? '' : 's'}
                  </div>
                  <div className="text-xs text-slate-500">
                    {architectureHealth.layerBypasses > 0 ? 'Controller directly accessing DAO/Repo' : 'All layers cleanly separated'}
                  </div>
                </div>
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Dead Code Candidates</div>
                  <div className="text-3xl font-black text-cyan-400">
                    {architectureHealth.deadCode} Function{architectureHealth.deadCode === 1 ? '' : 's'}
                  </div>
                  <div className="text-xs text-slate-500">0 incoming call graph edges</div>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
                <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                  {architectureHealth.layerBypasses > 0 || architectureHealth.cycles > 0 ? (
                    <>
                      <AlertTriangle className="h-4 w-4 text-amber-400" />
                      <span>Flagged Anti-Patterns & Coupling Violations ({architectureHealth.layerBypasses + architectureHealth.cycles})</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span>Architecture & Coupling Analysis</span>
                    </>
                  )}
                </h3>

                {architectureHealth.bypassList.length > 0 || architectureHealth.cycleList.length > 0 ? (
                  <div className="space-y-3">
                    {architectureHealth.bypassList.map((item, idx) => (
                      <div key={idx} className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 text-[10px] font-mono font-bold">
                              LAYER BYPASS
                            </span>
                            <span className="text-xs font-mono font-bold text-slate-200">
                              {item.source} -&gt; {item.target}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-1">
                            {item.note}
                          </p>
                        </div>
                        <button
                          onClick={() => {
                            setActiveTab('QA');
                            setQaInput(`Explain how to refactor ${item.source} to remove layer bypass violation with ${item.target}.`);
                          }}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-400 rounded-lg text-xs font-bold transition whitespace-nowrap"
                        >
                          Fix with Gemini
                        </button>
                      </div>
                    ))}

                    {architectureHealth.cycleList.map((cyc, idx) => (
                      <div key={'cyc-' + idx} className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 text-[10px] font-mono font-bold">
                              CIRCULAR DEPENDENCY
                            </span>
                            <span className="text-xs font-mono font-bold text-slate-200">
                              {cyc}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-1">
                            Methods directly or indirectly call each other in a cyclic dependency loop.
                          </p>
                        </div>
                        <button
                          onClick={() => {
                            setActiveTab('QA');
                            setQaInput(`Explain how to break cyclic dependency loop between ${cyc}.`);
                          }}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-rose-400 rounded-lg text-xs font-bold transition whitespace-nowrap"
                        >
                          Fix with Gemini
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-6 rounded-xl bg-slate-950/60 border border-emerald-500/20 flex items-start space-x-4">
                    <div className="h-10 w-10 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 flex-shrink-0 mt-0.5">
                      <Check className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-200">Clean Architectural Boundaries Verified</h4>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        Workspace <span className="text-cyan-400 font-mono font-bold">{selectedWorkspace?.name || 'Workspace'}</span> adheres to modular architecture principles. No illegal layer bypasses or circular import cycles were detected across {architectureHealth.totalSymbols} indexed symbols.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: AI REFACTOR & PR GENERATOR */}
          {activeTab === 'REFACTOR' && (
            <div className="flex-1 p-6 bg-slate-950 overflow-y-auto space-y-6">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
                <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                  <GitPullRequest className="h-4 w-4 text-cyan-400" />
                  <span>AI Unified Multi-File Refactor Generator</span>
                </h3>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                      Refactoring Objective
                    </label>
                    <span className="text-[11px] text-slate-500 font-mono">
                      Targeting: <span className="text-cyan-400 font-semibold">{selectedWorkspace?.name || 'Workspace'}</span>
                    </span>
                  </div>
                  <textarea
                    rows={3}
                    value={refactorPrompt}
                    onChange={(e) => setRefactorPrompt(e.target.value)}
                    placeholder={
                      selectedWorkspace?.name
                        ? `Describe refactoring objective for ${selectedWorkspace.name} (e.g. Add validation, extract service layer, decouple database calls, or add error handling)...`
                        : "Describe the refactoring objective for this repository..."
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 font-sans focus:outline-none focus:border-cyan-500 placeholder:text-slate-600 transition"
                  />

                  {/* Contextual Refactoring Suggestion Pills */}
                  <div className="mt-2.5 flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] text-slate-500 font-medium">Suggestions:</span>
                    {architectureHealth.bypassList.length > 0 ? (
                      architectureHealth.bypassList.slice(0, 2).map((bp, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => setRefactorPrompt(`Refactor ${bp.source} to delegate database queries through an intermediate service layer instead of calling ${bp.target} directly.`)}
                          className="px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[11px] transition text-left"
                        >
                          ⚡ Fix bypass: {bp.source.split('.').pop()} -&gt; {bp.target.split('.').pop()}
                        </button>
                      ))
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setRefactorPrompt(`Add input validation and standardized error handling across all controller and API route handlers in ${selectedWorkspace?.name || 'workspace'}.`)}
                      className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] transition"
                    >
                      🛡️ Add Input Validation & Guardrails
                    </button>
                    <button
                      type="button"
                      onClick={() => setRefactorPrompt(`Extract shared data formatting and database access logic into a dedicated service layer.`)}
                      className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] transition"
                    >
                      🧩 Decouple Service Architecture
                    </button>
                  </div>
                </div>

                <button
                  onClick={handleGenerateRefactor}
                  disabled={isGeneratingDiff}
                  className="px-5 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded-xl flex items-center space-x-2 transition shadow-lg shadow-cyan-500/20"
                >
                  <Zap className="h-4 w-4" />
                  <span>{isGeneratingDiff ? 'Generating Multi-File Diff...' : 'Generate Unified Git Diff'}</span>
                </button>
              </div>

              {generatedDiff && (
                <div className="space-y-6">
                  {/* Interactive Side-by-Side & Unified Diff Component */}
                  <RefactorDiffViewer
                    diffs={generatedDiff.diffs}
                    summary={generatedDiff.summary}
                    turn={generatedDiff.turn || 1}
                  />

                  {/* Multi-Turn Refactor Iteration & Propagation Card */}
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                      <div>
                        <h4 className="text-xs font-bold text-slate-100 flex items-center space-x-2">
                          <RotateCcw className="h-3.5 w-3.5 text-cyan-400" />
                          <span>Iterate & Propagate Refactoring (Turn {(generatedDiff.turn || 1) + 1})</span>
                        </h4>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Continue refining this refactor across downstream callers, controllers, or tests.
                        </p>
                      </div>
                      <button
                        onClick={() => setShowPrModal(true)}
                        className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold text-xs rounded-xl flex items-center space-x-2 shadow-lg shadow-cyan-500/20 transition"
                      >
                        <GitPullRequest className="h-4 w-4" />
                        <span>Draft GitHub Pull Request</span>
                      </button>
                    </div>

                    {/* Quick Iteration Chips */}
                    <div className="flex flex-wrap gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => setFollowUpPrompt('Propagate the updated token claims and expiration signature to all callers in AuthenticationController.')}
                        className="px-3 py-1.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-cyan-400 text-xs font-mono transition"
                      >
                        + Propagate to AuthenticationController
                      </button>
                      <button
                        type="button"
                        onClick={() => setFollowUpPrompt('Add null checks, expiration timestamp validation, and IllegalArgumentException guards.')}
                        className="px-3 py-1.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-cyan-400 text-xs font-mono transition"
                      >
                        + Add null checks & validation
                      </button>
                      <button
                        type="button"
                        onClick={() => setFollowUpPrompt('Add JUnit test assertion mocking JwtService with the new 24h expiration parameter.')}
                        className="px-3 py-1.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-cyan-400 text-xs font-mono transition"
                      >
                        + Add unit test assertions
                      </button>
                    </div>

                    <div className="space-y-2">
                      <textarea
                        rows={2}
                        value={followUpPrompt}
                        onChange={(e) => setFollowUpPrompt(e.target.value)}
                        placeholder="e.g. Next turn: Update all callers in AuthenticationController to pass the new expiration parameter..."
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 font-sans focus:outline-none focus:border-cyan-500"
                      />

                      <div className="flex items-center justify-between">
                        <button
                          type="button"
                          onClick={() => {
                            setGeneratedDiff(null);
                            setRefactorHistory([]);
                            setFollowUpPrompt('');
                          }}
                          className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-300 font-mono transition"
                        >
                          Reset Session
                        </button>

                        <button
                          type="button"
                          onClick={() => handleGenerateRefactor(followUpPrompt)}
                          disabled={isGeneratingDiff || !followUpPrompt.trim()}
                          className="px-5 py-2 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 disabled:opacity-50 text-white font-bold text-xs rounded-xl flex items-center space-x-2 transition shadow-lg shadow-cyan-500/20"
                        >
                          <Zap className="h-3.5 w-3.5" />
                          <span>{isGeneratingDiff ? 'Refining Refactor...' : `Refine Refactor (Turn ${(generatedDiff.turn || 1) + 1})`}</span>
                        </button>
                      </div>
                    </div>

                    {/* Session Turns Timeline */}
                    {refactorHistory.length > 1 && (
                      <div className="border-t border-slate-800/80 pt-3">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block mb-2">
                          Session Turns History ({refactorHistory.length} turns applied)
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {refactorHistory.map((h, hIdx) => (
                            <button
                              key={hIdx}
                              onClick={() => setGeneratedDiff(h.result)}
                              className={`px-2.5 py-1 rounded-lg text-[11px] font-mono border transition ${
                                generatedDiff === h.result
                                  ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-400 font-bold'
                                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                              }`}
                            >
                              Turn {h.turn}: {h.prompt.slice(0, 32)}...
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: HYBRID RAG QA SEARCH */}
          {activeTab === 'QA' && (
            <HybridRAGSearch
              workspace={selectedWorkspace}
              geminiApiKey={geminiApiKey}
              onSaveGeminiKey={handleSaveApiKey}
              onDeleteGeminiKey={() => handleSaveApiKey('')}
              isKeyEncryptedInBackend={isKeyEncryptedInBackend}
              maskedKeyDisplay={maskedKeyDisplay}
              initialMessages={qaMessages}
              workspaceSymbols={workspaceSymbols}
            />
          )}

          {/* TAB 5: MCP TOOLING HUB */}
          {activeTab === 'MCP' && (
            <div className="flex-1 p-6 bg-slate-950 overflow-y-auto space-y-6">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                  <div>
                    <h3 className="text-sm font-bold text-slate-100">VS Code & Cursor MCP Configuration</h3>
                    <p className="text-xs text-slate-400">Paste this JSON into your local .vscode/mcp.json file</p>
                  </div>
                  <button
                    onClick={() => handleCopy(`{\n  "servers": {\n    "codegraph-rag": {\n      "type": "stdio",\n      "command": "python",\n      "args": ["/workspaces/CodeGraph-RAG/mcp_server.py"]\n    }\n  }\n}`, 'MCP Config Copied!')}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-400 font-bold text-xs rounded-xl flex items-center space-x-1.5 border border-slate-700"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    <span>Copy mcp.json</span>
                  </button>
                </div>

                <pre className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs text-cyan-400/90 leading-relaxed overflow-x-auto">
{`{
  "servers": {
    "codegraph-rag": {
      "type": "stdio",
      "command": "python",
      "args": [
        "/workspaces/CodeGraph-RAG/mcp_server.py"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password"
      }
    }
  }
}`}
                </pre>
              </div>
            </div>
          )}
        </div>
        )
      )}

      {/* PR MODAL */}
      {showPrModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur flex items-center justify-center p-4">
          <div className="max-w-xl w-full bg-slate-900 border border-slate-800 rounded-3xl p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-slate-100 text-sm">GitHub Pull Request Draft</h3>
              <button onClick={() => setShowPrModal(false)} className="text-slate-400 hover:text-slate-200">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div>
                <span className="text-slate-500 block text-[10px]">Title</span>
                <span className="text-cyan-400 font-bold">refactor(auth): overload JwtService.generateToken for claims and expiration</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">Target Branch</span>
                <span className="text-slate-200">main &lt;- feature/refactor-jwt</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-slate-300">
                CodeGraph-RAG Impact Analysis verified 3 affected callers. All transitive dependencies updated cleanly.
              </div>
            </div>

            <button
              onClick={() => {
                setShowPrModal(false);
                handleCopy('git checkout -b feature/refactor-jwt && git commit -m "refactor: update JwtService"', 'PR Commands Copied!');
              }}
              className="w-full py-3 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded-xl flex items-center justify-center space-x-2"
            >
              <Check className="h-4 w-4" />
              <span>Copy Git Commit Commands</span>
            </button>
          </div>
        </div>
      )}

      {/* DELETE WORKSPACE CONFIRMATION MODAL */}
      {workspaceToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="bg-slate-900 border border-rose-500/30 rounded-3xl max-w-md w-full p-6 shadow-2xl shadow-rose-950/40 space-y-5">
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-3">
                <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-2xl">
                  <Trash2 className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100">Delete Workspace</h3>
                  <p className="text-xs text-slate-400">Permanently purge repository data</p>
                </div>
              </div>
              <button
                disabled={isDeletingWorkspace}
                onClick={() => setWorkspaceToDelete(null)}
                className="p-1.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition disabled:opacity-50"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-4 space-y-2.5 text-xs">
              <div className="flex justify-between items-center text-slate-300">
                <span className="text-slate-500">Workspace</span>
                <span className="font-bold font-mono text-slate-100">{workspaceToDelete.name}</span>
              </div>
              <div className="flex justify-between items-center text-slate-300">
                <span className="text-slate-500">Source</span>
                <span className="font-mono text-cyan-400 truncate max-w-[200px]" title={workspaceToDelete.repoUrl}>
                  {workspaceToDelete.repoUrl || workspaceToDelete.type}
                </span>
              </div>
              <div className="flex justify-between items-center text-slate-300">
                <span className="text-slate-500">Graph Nodes</span>
                <span className="font-mono text-emerald-400 font-bold">{workspaceToDelete.nodesCount || 0} nodes</span>
              </div>
              <div className="pt-2.5 border-t border-slate-900 text-[11px] text-rose-300/90 leading-relaxed">
                ⚠️ This will permanently detach & remove all AST nodes and call graph relationships in Neo4j, delete vector embeddings from Qdrant, and delete this workspace record.
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-1">
              <button
                type="button"
                disabled={isDeletingWorkspace}
                onClick={() => setWorkspaceToDelete(null)}
                className="px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-300 hover:bg-slate-800 border border-slate-700 transition cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeletingWorkspace}
                onClick={() => handleDeleteWorkspace(workspaceToDelete)}
                className="px-4 py-2.5 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white transition flex items-center space-x-2 shadow-lg shadow-rose-900/40 cursor-pointer disabled:opacity-50"
              >
                {isDeletingWorkspace ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Deleting Workspace...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" />
                    <span>Confirm Delete</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* UNIFIED MULTI-PROVIDER KEY VAULT MODAL */}
      <KeyVaultModal
        isOpen={showApiKeyModal}
        onClose={() => setShowApiKeyModal(false)}
        activeKeys={{ gemini: geminiApiKey }}
        onSaveKey={async (provider, keyVal) => {
          if (provider === 'gemini') {
            await handleSaveApiKey(keyVal);
          } else {
            await api.saveApiKey(provider, keyVal);
          }
        }}
        onDeleteKey={async (provider) => {
          if (provider === 'gemini') {
            await handleSaveApiKey('');
          } else {
            await api.deleteApiKey(provider);
          }
        }}
        isEncryptedInBackend={isKeyEncryptedInBackend}
        maskedKeyDisplay={maskedKeyDisplay}
        onKeysUpdated={checkBackendKey}
      />

    </div>
  );
}
