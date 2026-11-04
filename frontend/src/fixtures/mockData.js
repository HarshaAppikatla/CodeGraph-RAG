// Mock demo workspaces and symbol graphs isolated from vector search index

export const INITIAL_WORKSPACES = [
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

export const SYMBOL_GRAPHS = {
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

export const DEMO_REFACTOR_PROMPTS = {
  'ws-study-sync': 'Update JwtService.generateToken signature to accept explicit Claims map and set token expiration to 24 hours.',
  'ws-payment-gw': 'Add idempotency key validation and distributed locking to processPayment endpoint.'
};

export const DEMO_STUDYSYNC_CHAT_FALLBACK = {
  sender: 'assistant',
  text: `Based on Neo4j Graph Traversal & Qdrant Chunk Analysis:

1. Target Symbol: JwtService.generateToken
2. Direct Dependent Services: AuthenticationService.java invokes generateToken inside both authenticate() (line 52) and register() (line 89).
3. Public HTTP Controllers: AuthenticationController.java indirectly relies on this payload via /api/auth/authenticate and /api/auth/refresh.

Refactoring Recommendation: Maintain backward compatibility by keeping the single-parameter generateToken(UserDetails) as an overload calling your updated method signature.`,
  sources: [
    'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java',
    'studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java'
  ]
};

export const DEMO_STUDYSYNC_DIFF_FOLLOWUP = {
  filesChanged: 3,
  turn: 2,
  summary: 'Turn 2: Added null checks, expiration timestamp validation, and IllegalArgumentException guards in AuthenticationController.',
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
};

export const DEMO_STUDYSYNC_DIFF_TURN1 = {
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
};

export const DEMO_INITIAL_QA_MESSAGES = [
  {
    sender: 'assistant',
    text: 'Hello! I am your CodeGraph-RAG Architectural AI. I have indexed Study-Sync into Qdrant vector store (384D) and Neo4j call graph (2,533 nodes). Ask me anything about symbol dependencies or architectural impact!',
    sources: ['JwtService.java', 'AuthenticationService.java']
  }
];
