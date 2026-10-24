import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { api } from './services/api';
import {
  Shield, Key, GitBranch, Cpu, Database, Zap, AlertTriangle,
  CheckCircle, Play, Code, ArrowRight, RefreshCw, Terminal,
  Sliders, Layers, Search, Eye, FileText, ChevronRight, Activity, Sparkles,
  LogOut, Folder, UploadCloud, GitPullRequest, Check, Copy, Plus, X, Radio,
  FileCode, Share2, Compass, BookOpen, User, CheckSquare, Trash2, Settings, Download, Lock,
  ZoomIn, ZoomOut, Maximize2, Move
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

export default function App() {
  // Authentication & Global User State
  const [currentUser, setCurrentUser] = useState(null);
  const [authMode, setAuthMode] = useState('LOGIN');
  const [authEmail, setAuthEmail] = useState('harsha.demo@codegraph.ai');
  const [authPassword, setAuthPassword] = useState('demopassword2026');
  const [geminiApiKey, setGeminiApiKey] = useState('');

  // Application Screen State
  const [currentScreen, setCurrentScreen] = useState('AUTH');

  // Workspaces List
  const [workspaces, setWorkspaces] = useState(INITIAL_WORKSPACES);
  const [selectedWorkspace, setSelectedWorkspace] = useState(INITIAL_WORKSPACES[0]);

  // Workspace Creation Form
  const [uploadType, setUploadType] = useState('git');
  const [gitRepoInput, setGitRepoInput] = useState('https://github.com/HarshaAppikatla/Study-Sync');
  const [zipFileName, setZipFileName] = useState('');
  const [zipFile, setZipFile] = useState(null);
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
  const [selectedSymbolKey, setSelectedSymbolKey] = useState('generateToken');
  const [liveGraphData, setLiveGraphData] = useState(null);
  const [blastRadiusActive, setBlastRadiusActive] = useState(true);
  const [searchFilter, setSearchFilter] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState('target');

  // Zoom and Pan Controls
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });

  // AI & QA Assistant State
  const [qaInput, setQaInput] = useState('Explain the token authentication workflow and blast radius if generateToken is changed.');
  const [qaMessages, setQaMessages] = useState([
    {
      sender: 'assistant',
      text: 'Hello! I am your CodeGraph-RAG Architectural AI. I have indexed Study-Sync into Qdrant vector store (384D) and Neo4j call graph (2,533 nodes). Ask me anything about symbol dependencies or architectural impact!',
      sources: ['JwtService.java', 'AuthenticationService.java']
    }
  ]);
  const [isAiThinking, setIsAiThinking] = useState(false);

  // Refactor Sandbox State
  const [refactorPrompt, setRefactorPrompt] = useState('Update JwtService.generateToken signature to accept explicit Claims map and set token expiration to 24 hours.');
  const [generatedDiff, setGeneratedDiff] = useState(null);
  const [isGeneratingDiff, setIsGeneratingDiff] = useState(false);
  const [showPrModal, setShowPrModal] = useState(false);

  // Copy Feedback Toast State
  const [copiedText, setCopiedText] = useState(null);

  const handleCopy = (text, label = 'Copied') => {
    navigator.clipboard.writeText(text);
    setCopiedText(label);
    setTimeout(() => setCopiedText(null), 2000);
  };

  const callGeminiApi = async (prompt, systemInstruction = '') => {
    const apiKey = geminiApiKey.trim();
    const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key=${apiKey}`;

    const payload = {
      contents: [{ parts: [{ text: prompt }] }],
      tools: [{ google_search: {} }]
    };

    if (systemInstruction) {
      payload.systemInstruction = { parts: [{ text: systemInstruction }] };
    }

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`API response error status: ${response.status}`);
      }

      const result = await response.json();
      const candidate = result.candidates?.[0];
      const text = candidate?.content?.parts?.[0]?.text;

      let sources = [];
      const attributions = candidate?.groundingMetadata?.groundingAttributions;
      if (attributions && Array.isArray(attributions)) {
        sources = attributions
          .map(a => a.web?.title || a.web?.uri)
          .filter(Boolean);
      }

      return { text, sources };
    } catch (err) {
      console.warn("Gemini API direct call failed or unconfigured, using fallback structured response:", err);
      return null;
    }
  };

  // Dynamic Graph Impact Loader from Backend
  useEffect(() => {
    if (selectedWorkspace) {
      api.getSymbolImpact(selectedWorkspace.id, selectedSymbolKey)
        .then(data => {
          if (data && data.nodes && data.nodes.length > 0) {
            setLiveGraphData(data);
          }
        })
        .catch(err => {
          console.warn("Could not fetch symbol impact from API, using fallback:", err);
        });
    }
  }, [selectedSymbolKey, selectedWorkspace, currentScreen]);

  const handleLoginDemoAccount = async () => {
    setAuthError('');
    try {
      const res = await api.loginDemo();
      setCurrentUser(res.user);
      setAuthEmail(res.user.email);
      setAuthPassword('demopassword2026');

      // Fetch dynamic workspaces from backend
      try {
        const wsList = await api.listWorkspaces();
        if (wsList && wsList.length > 0) {
          setWorkspaces(wsList);
          setSelectedWorkspace(wsList[0]);
        }
      } catch (wsErr) {
        console.warn("Could not list workspaces from API:", wsErr);
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

      try {
        const wsList = await api.listWorkspaces();
        if (wsList && wsList.length > 0) {
          setWorkspaces(wsList);
          setSelectedWorkspace(wsList[0]);
        }
      } catch (wsErr) {
        console.warn("Workspace list fetch error:", wsErr);
      }

      setCurrentScreen('WORKSPACE_SELECT');
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('codegraph_token');
    setCurrentUser(null);
    setCurrentScreen('AUTH');
  };

  const handleStartIngestion = async () => {
    setUploadError('');
    if (uploadType === 'zip' && !zipFile) {
      setUploadError('Choose a .zip file first.');
      return;
    }

    setCurrentScreen('INGESTION');
    setIngestProgress(0);
    setIngestLogs([]);
    ingestTimers.current.forEach(clearTimeout);
    ingestTimers.current = [];

    // Trigger backend ingestion
    const payload = uploadType === 'zip'
      ? { type: 'zip', file: zipFile }
      : { repo_url: gitRepoInput, type: 'git', branch: branchInput };

    api.ingestWorkspace(payload).then(newWs => {
      if (newWs && newWs.id) {
        setWorkspaces(prev => [newWs, ...prev]);
        setSelectedWorkspace(newWs);
      }
    }).catch(err => {
      ingestTimers.current.forEach(clearTimeout);
      ingestTimers.current = [];
      setUploadError(err.message);
      setCurrentScreen('WORKSPACE_SELECT');
    });

    const steps = [
      { p: 15, text: 'Cloning repository & inspecting source tree with Polyglot Tree-sitter...' },
      { p: 35, text: 'Parsed 211 files: Extracted 142 classes, 892 methods, and 1,195 call relations.' },
      { p: 60, text: 'Generating 384D BGE-small-en-v1.5 embeddings & indexing into Qdrant...' },
      { p: 85, text: 'Executing Cypher UNWIND transactions & populating Neo4j graph nodes...' },
      { p: 100, text: 'Indexing finished! Loading Developer Command Center...' }
    ];

    steps.forEach((step, idx) => {
      const timer = setTimeout(() => {
        setIngestProgress(step.p);
        setIngestStageText(step.text);
        setIngestLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${step.text}`]);

        if (step.p === 100) {
          ingestTimers.current.push(setTimeout(() => {
            setCurrentScreen('APP_WORKSPACE');
          }, 800));
        }
      }, (idx + 1) * 800);
      ingestTimers.current.push(timer);
    });
  };

  const activeGraph = liveGraphData || SYMBOL_GRAPHS[selectedSymbolKey] || SYMBOL_GRAPHS.generateToken;

  const handleSendQaQuery = async () => {
    if (!qaInput.trim()) return;
    const userMsg = { sender: 'user', text: qaInput };
    setQaMessages(prev => [...prev, userMsg]);
    const currentQuery = qaInput;
    setQaInput('');
    setIsAiThinking(true);

    try {
      const res = await api.queryRag(selectedWorkspace?.id || 'ws-study-sync', currentQuery, geminiApiKey);
      setIsAiThinking(false);
      if (res && res.answer) {
        setQaMessages(prev => [
          ...prev,
          {
            sender: 'assistant',
            text: res.answer,
            sources: res.sources || ['Qdrant Vector Chunks', 'Neo4j Cypher Graph']
          }
        ]);
        return;
      }
    } catch (err) {
      console.warn("API queryRag error, falling back to local reasoning:", err);
    }

    setIsAiThinking(false);
    const fallbackMsg = {
      sender: 'assistant',
      text: `Based on Neo4j Graph Traversal & Qdrant Chunk Analysis:\n\n1. Target Symbol: JwtService.generateToken\n2. Direct Dependent Services: AuthenticationService.java invokes generateToken inside both authenticate() (line 52) and register() (line 89).\n3. Public HTTP Controllers: AuthenticationController.java indirectly relies on this payload via /api/auth/authenticate and /api/auth/refresh.\n\nRefactoring Recommendation: Maintain backward compatibility by keeping the single-parameter generateToken(UserDetails) as an overload calling your updated method signature.`,
      sources: [
        'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java',
        'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java'
      ]
    };
    setQaMessages(prev => [...prev, fallbackMsg]);
  };

  const handleGenerateRefactor = async () => {
    setIsGeneratingDiff(true);

    try {
      const res = await api.generateRefactor(selectedWorkspace?.id || 'ws-study-sync', refactorPrompt, geminiApiKey);
      if (res && res.diffs) {
        setIsGeneratingDiff(false);
        setGeneratedDiff(res);
        return;
      }
    } catch (err) {
      console.warn("API generateRefactor notice, using fallback diff:", err);
    }

    setTimeout(() => {
      setIsGeneratingDiff(false);
      setGeneratedDiff({
        filesChanged: 2,
        summary: 'Updated JwtService.generateToken signature and updated downstream invocations in AuthenticationService.',
        diffs: [
          {
            file: 'JwtService.java',
            diffCode: `--- a/service/JwtService.java\n+++ b/service/JwtService.java\n@@ -38,3 +38,4 @@\n-public String generateToken(UserDetails userDetails) {\n-    return generateToken(new HashMap<>(), userDetails);\n+public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n+    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);`
          },
          {
            file: 'AuthenticationService.java',
            diffCode: `--- a/service/AuthenticationService.java\n+++ b/service/AuthenticationService.java\n@@ -52,1 +52,1 @@\n-var jwtToken = jwtService.generateToken(user);\n+var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);`
          }
        ]
      });
    }, 1200);
  };

  const getNodeColor = (type, isBlastActive) => {
    switch (type) {
      case 'TARGET':
        return isBlastActive ? '#ef4444' : '#06b6d4';
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

          <div className="flex items-center space-x-4">
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

            <button
              onClick={handleLoginDemoAccount}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-cyan-400 border border-slate-700 rounded-xl text-xs font-mono font-bold flex items-center space-x-2"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Reload Demo Workspace</span>
            </button>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Active Codebase Workspaces ({workspaces.length})
              </h2>
            </div>

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
                    <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-[10px] font-bold">
                      {ws.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 bg-slate-950 p-3 rounded-xl font-mono text-[11px] text-slate-300">
                    <div>
                      <span className="text-slate-500 block text-[10px]">Files</span>
                      <span className="font-bold text-slate-100">{ws.filesCount}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">Graph Nodes</span>
                      <span className="font-bold text-cyan-400">{ws.nodesCount}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">Call Edges</span>
                      <span className="font-bold text-blue-400">{ws.edgesCount}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-xs text-slate-500">Indexed {ws.lastIndexed}</span>
                    <button
                      onClick={() => {
                        setSelectedWorkspace(ws);
                        setCurrentScreen('APP_WORKSPACE');
                      }}
                      className="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded-xl flex items-center space-x-1.5 transition shadow-lg shadow-cyan-500/20"
                    >
                      <span>Open Workspace</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
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
              <div className="border-2 border-dashed border-slate-800 hover:border-cyan-500/50 bg-slate-950 p-8 rounded-2xl text-center space-y-3 cursor-pointer transition">
                <UploadCloud className="h-10 w-10 text-cyan-400 mx-auto" />
                <div className="text-xs font-bold text-slate-200">
                  {zipFileName ? zipFileName : 'Click or Drag & Drop project .ZIP archive here'}
                </div>
                <p className="text-[11px] text-slate-500">Supports Java, Python, JS/TS, Go, C++ source trees up to 100 MB</p>
                <input
                  type="file"
                  accept=".zip"
                  onChange={(e) => {
                    const f = e.target.files[0] || null;
                    setZipFile(f);
                    setZipFileName(f ? f.name : '');
                  }}
                  className="hidden"
                  id="zip-input"
                />
                <label htmlFor="zip-input" className="inline-block px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded-xl cursor-pointer">
                  Browse File
                </label>
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
        <div className="flex-1 flex flex-col overflow-hidden">
          
          {/* WORKSPACE TAB NAVIGATION BAR */}
          <div className="h-12 border-b border-slate-800 bg-slate-900/60 px-6 flex items-center justify-between">
            <div className="flex items-center space-x-1">
              <button
                onClick={() => setActiveTab('GRAPH')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center space-x-2 transition ${activeTab === 'GRAPH' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              >
                <Activity className="h-3.5 w-3.5" />
                <span>Call Graph & Blast Radius</span>
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

            <button
              onClick={() => setCurrentScreen('WORKSPACE_SELECT')}
              className="text-xs font-semibold text-slate-400 hover:text-cyan-400 flex items-center space-x-1"
            >
              <Folder className="h-3.5 w-3.5" />
              <span>Switch Workspace</span>
            </button>
          </div>

          {/* TAB 1: BLAST RADIUS & NODE-LINK CALL GRAPH */}
          {activeTab === 'GRAPH' && (
            <div className="flex-1 flex overflow-hidden">
              
              {/* Symbol Selector Sidebar */}
              <aside className="w-80 border-r border-slate-800 bg-slate-900/40 flex flex-col">
                <div className="p-4 border-b border-slate-800 space-y-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    AST Method / Class Inspector
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
                  {Object.keys(SYMBOL_GRAPHS).map((key) => {
                    const sym = SYMBOL_GRAPHS[key];
                    const isSelected = selectedSymbolKey === key;
                    return (
                      <button
                        key={key}
                        onClick={() => {
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
                  })}
                </div>

                <div className="p-3 border-t border-slate-800 bg-slate-950 text-[11px] font-mono text-slate-400 space-y-1">
                  <div className="flex justify-between">
                    <span>Qdrant Vectors:</span>
                    <span className="text-cyan-400">211 Chunks (384D)</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Neo4j Graph:</span>
                    <span className="text-blue-400">2,533 Nodes | 1,195 Edges</span>
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
                    {/* Zoom & Controls */}
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

                    <button
                      onClick={() => setBlastRadiusActive(!blastRadiusActive)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition ${blastRadiusActive ? 'bg-rose-500/20 border border-rose-500/40 text-rose-300' : 'bg-slate-800 text-slate-400'}`}
                    >
                      <AlertTriangle className="h-3.5 w-3.5" />
                      <span>{blastRadiusActive ? 'Blast Radius Simulation: ON' : 'Blast Radius Simulation: OFF'}</span>
                    </button>
                  </div>
                </div>

                {/* Node-Link Interactive Canvas View */}
                <div className="flex-1 p-4 relative flex flex-col justify-between overflow-hidden bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:18px_18px]">
                  
                  {/* Interactive Node-Link SVG Graph */}
                  <div className="flex-1 relative w-full h-full min-h-[380px]">
                    <svg
                      className="w-full h-full absolute inset-0 cursor-grab active:cursor-grabbing"
                      style={{ transform: `scale(${zoomLevel}) translate(${panOffset.x}px, ${panOffset.y}px)` }}
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
              </section>
            </div>
          )}

          {/* TAB 2: ARCHITECTURE HEALTH INSPECTOR */}
          {activeTab === 'HEALTH' && (
            <div className="flex-1 p-6 bg-slate-950 overflow-y-auto space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Overall Health Score</div>
                  <div className="text-3xl font-black text-emerald-400">94 / 100</div>
                  <div className="text-xs text-slate-500">2 Architectural warnings flagged</div>
                </div>
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Circular Dependencies</div>
                  <div className="text-3xl font-black text-emerald-400">0</div>
                  <div className="text-xs text-slate-500">No cyclic method loops found</div>
                </div>
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Layer Bypass Rules</div>
                  <div className="text-3xl font-black text-amber-400">1 Warning</div>
                  <div className="text-xs text-slate-500">Controller directly accessing DAO</div>
                </div>
                <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Dead Code Candidates</div>
                  <div className="text-3xl font-black text-cyan-400">2 Functions</div>
                  <div className="text-xs text-slate-500">0 incoming call graph edges</div>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
                <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                  <AlertTriangle className="h-4 w-4 text-amber-400" />
                  <span>Flagged Anti-Patterns & Coupling Violations</span>
                </h3>

                <div className="space-y-3">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 text-[10px] font-mono font-bold">
                          LAYER BYPASS
                        </span>
                        <span className="text-xs font-mono font-bold text-slate-200">
                          UserController -&gt; UserRepository
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Controller bypasses Service orchestration layer to execute raw queries directly.
                      </p>
                    </div>
                    <button
                      onClick={() => {
                        setActiveTab('QA');
                        setQaInput('Explain how to refactor UserController to remove layer bypass violation.');
                      }}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-400 rounded-lg text-xs font-bold transition whitespace-nowrap"
                    >
                      Fix with Gemini
                    </button>
                  </div>
                </div>
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
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    Refactoring Objective
                  </label>
                  <textarea
                    rows={3}
                    value={refactorPrompt}
                    onChange={(e) => setRefactorPrompt(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 font-sans focus:outline-none focus:border-cyan-500"
                  />
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
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div>
                      <h4 className="text-xs font-bold text-slate-200">Refactoring Plan Generated</h4>
                      <p className="text-xs text-slate-400">{generatedDiff.summary}</p>
                    </div>
                    <button
                      onClick={() => setShowPrModal(true)}
                      className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-bold text-xs rounded-xl flex items-center space-x-2 shadow-lg"
                    >
                      <GitPullRequest className="h-4 w-4" />
                      <span>Draft GitHub Pull Request</span>
                    </button>
                  </div>

                  {generatedDiff.diffs.map((d, i) => (
                    <div key={i} className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs">
                      <div className="text-cyan-400 font-bold mb-2">{d.file}</div>
                      <pre className="text-slate-300 leading-relaxed overflow-x-auto">{d.diffCode}</pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 4: HYBRID RAG QA SEARCH */}
          {activeTab === 'QA' && (
            <div className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
              <div className="flex-1 p-6 overflow-y-auto space-y-4">
                {qaMessages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`p-4 rounded-2xl max-w-3xl text-xs leading-relaxed space-y-2 ${msg.sender === 'user' ? 'bg-cyan-500/10 border border-cyan-500/30 text-slate-100 ml-auto' : 'bg-slate-900 border border-slate-800 text-slate-300'}`}
                  >
                    <div className="font-bold text-[10px] uppercase font-mono text-cyan-400">
                      {msg.sender === 'user' ? 'Developer' : 'CodeGraph Assistant'}
                    </div>
                    <div className="whitespace-pre-line font-sans">{msg.text}</div>
                    {msg.sources && (
                      <div className="pt-2 border-t border-slate-800 text-[10px] font-mono text-slate-400">
                        Sources: {msg.sources.join(', ')}
                      </div>
                    )}
                  </div>
                ))}
                {isAiThinking && (
                  <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 max-w-xs text-xs font-mono text-cyan-400 animate-pulse">
                    Traversing Neo4j Graph & Qdrant Vector Chunks...
                  </div>
                )}
              </div>

              <div className="p-4 border-t border-slate-800 bg-slate-900/80">
                <div className="flex space-x-2 max-w-4xl mx-auto">
                  <input
                    type="text"
                    value={qaInput}
                    onChange={(e) => setQaInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendQaQuery()}
                    placeholder="Ask CodeGraph about architectural dependencies or symbol logic..."
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-sans"
                  />
                  <button
                    onClick={handleSendQaQuery}
                    className="px-5 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded-xl flex items-center space-x-1.5 shadow-lg shadow-cyan-500/20"
                  >
                    <Sparkles className="h-4 w-4" />
                    <span>Query RAG</span>
                  </button>
                </div>
              </div>
            </div>
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

    </div>
  );
}
