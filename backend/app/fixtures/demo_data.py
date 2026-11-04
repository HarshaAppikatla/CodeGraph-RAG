from typing import Dict, Any, Optional, List, Tuple
from backend.app.services.ast_validator import validate_code_syntax
from backend.app.services.ast_metrics import calculate_health_delta

# Mock demo architecture graphs isolated from vector search index

CANONICAL_ARCHITECTURE_GRAPHS = {
    "ws-study-sync": {
        "workspace_id": "ws-study-sync",
        "title": "Study-Sync Backend Architecture Map",
        "summary": "Full Codebase Architecture & Knowledge Graph: 30 connected entities across classes, interfaces, methods, calls, and file containment.",
        "nodes": [
            # Classes & Interfaces
            {"id": "cls_AuthService", "label": "AuthenticationService", "name": "AuthenticationService", "type": "CLASS", "file": "service/AuthenticationService.java", "scope": "Service Orchestrator", "signature": "public class AuthenticationService extends BaseService implements AuthService"},
            {"id": "cls_BaseService", "label": "BaseService", "name": "BaseService", "type": "CLASS", "file": "service/BaseService.java", "scope": "Abstract Base", "signature": "public abstract class BaseService"},
            {"id": "iface_AuthService", "label": "AuthService", "name": "AuthService", "type": "INTERFACE", "file": "service/AuthService.java", "scope": "Contract Interface", "signature": "public interface AuthService"},
            {"id": "cls_JwtService", "label": "JwtService", "name": "JwtService", "type": "CLASS", "file": "service/JwtService.java", "scope": "Token Engine", "signature": "public class JwtService"},
            {"id": "cls_AuthController", "label": "AuthenticationController", "name": "AuthenticationController", "type": "CLASS", "file": "controller/AuthenticationController.java", "scope": "REST Controller", "signature": "@RestController public class AuthenticationController"},
            {"id": "cls_JwtFilter", "label": "JwtAuthenticationFilter", "name": "JwtAuthenticationFilter", "type": "CLASS", "file": "config/JwtAuthenticationFilter.java", "scope": "Security Filter", "signature": "public class JwtAuthenticationFilter extends OncePerRequestFilter"},
            {"id": "cls_OncePerRequest", "label": "OncePerRequestFilter", "name": "OncePerRequestFilter", "type": "CLASS", "file": "org.springframework.web.filter", "scope": "Framework Base", "signature": "public abstract class OncePerRequestFilter"},
            {"id": "iface_UserRepo", "label": "UserRepository", "name": "UserRepository", "type": "INTERFACE", "file": "repository/UserRepository.java", "scope": "JPA Repository", "signature": "public interface UserRepository extends JpaRepository<User, Long>"},
            {"id": "iface_JpaRepo", "label": "JpaRepository", "name": "JpaRepository", "type": "INTERFACE", "file": "org.springframework.data.jpa", "scope": "Spring Data Base", "signature": "public interface JpaRepository<T, ID>"},
            {"id": "cls_User", "label": "User", "name": "User", "type": "CLASS", "file": "model/User.java", "scope": "JPA Entity", "signature": "public class User implements UserDetails"},
            {"id": "iface_UserDetails", "label": "UserDetails", "name": "UserDetails", "type": "INTERFACE", "file": "org.springframework.security.core", "scope": "Security Principal", "signature": "public interface UserDetails"},
            {"id": "cls_SecConfig", "label": "SecurityConfig", "name": "SecurityConfig", "type": "CLASS", "file": "config/SecurityConfig.java", "scope": "Security Setup", "signature": "@Configuration public class SecurityConfig"},
            {"id": "cls_WsConfig", "label": "WebSocketConfig", "name": "WebSocketConfig", "type": "CLASS", "file": "config/WebSocketConfig.java", "scope": "STOMP WebSocket Setup", "signature": "@Configuration public class WebSocketConfig implements WebSocketMessageBrokerConfigurer"},
            {"id": "iface_WsConfigurer", "label": "WebSocketMessageBrokerConfigurer", "name": "WebSocketMessageBrokerConfigurer", "type": "INTERFACE", "file": "org.springframework.web.socket", "scope": "Broker Contract", "signature": "public interface WebSocketMessageBrokerConfigurer"},

            # Methods
            {"id": "fn_authenticate", "label": "authenticate", "name": "AuthenticationService.authenticate", "type": "METHOD", "file": "service/AuthenticationService.java", "scope": "Method", "signature": "public AuthenticationResponse authenticate(AuthenticationRequest request)"},
            {"id": "fn_register", "label": "register", "name": "AuthenticationService.register", "type": "METHOD", "file": "service/AuthenticationService.java", "scope": "Method", "signature": "public AuthenticationResponse register(RegisterRequest request)"},
            {"id": "fn_generateToken", "label": "generateToken", "name": "JwtService.generateToken", "type": "METHOD", "file": "service/JwtService.java", "scope": "Method", "signature": "public String generateToken(UserDetails userDetails)"},
            {"id": "fn_extractUsername", "label": "extractUsername", "name": "JwtService.extractUsername", "type": "METHOD", "file": "service/JwtService.java", "scope": "Method", "signature": "public String extractUsername(String token)"},
            {"id": "fn_isTokenValid", "label": "isTokenValid", "name": "JwtService.isTokenValid", "type": "METHOD", "file": "service/JwtService.java", "scope": "Method", "signature": "public boolean isTokenValid(String token, UserDetails userDetails)"},
            {"id": "fn_login", "label": "login", "name": "AuthenticationController.login", "type": "METHOD", "file": "controller/AuthenticationController.java", "scope": "Method", "signature": "@PostMapping('/login') public ResponseEntity<AuthenticationResponse> login()"},
            {"id": "fn_refreshToken", "label": "refreshToken", "name": "AuthenticationController.refreshToken", "type": "METHOD", "file": "controller/AuthenticationController.java", "scope": "Method", "signature": "@PostMapping('/refresh') public void refreshToken()"},
            {"id": "fn_doFilterInternal", "label": "doFilterInternal", "name": "JwtAuthenticationFilter.doFilterInternal", "type": "METHOD", "file": "config/JwtAuthenticationFilter.java", "scope": "Method", "signature": "protected void doFilterInternal(HttpServletRequest request...)"},
            {"id": "fn_findByEmail", "label": "findByEmail", "name": "UserRepository.findByEmail", "type": "METHOD", "file": "repository/UserRepository.java", "scope": "Method", "signature": "Optional<User> findByEmail(String email)"},
            {"id": "fn_regStomp", "label": "registerStompEndpoints", "name": "WebSocketConfig.registerStompEndpoints", "type": "METHOD", "file": "config/WebSocketConfig.java", "scope": "Method", "signature": "public void registerStompEndpoints(StompEndpointRegistry registry)"},

            # Files
            {"id": "file_AuthService_java", "label": "AuthenticationService.java", "name": "AuthenticationService.java", "type": "FILE", "file": "service/AuthenticationService.java", "scope": "Source File", "signature": "package com.studysync.service"},
            {"id": "file_JwtService_java", "label": "JwtService.java", "name": "JwtService.java", "type": "FILE", "file": "service/JwtService.java", "scope": "Source File", "signature": "package com.studysync.service"},
            {"id": "file_AuthController_java", "label": "AuthenticationController.java", "name": "AuthenticationController.java", "type": "FILE", "file": "controller/AuthenticationController.java", "scope": "Source File", "signature": "package com.studysync.controller"},
            {"id": "file_JwtFilter_java", "label": "JwtAuthenticationFilter.java", "name": "JwtAuthenticationFilter.java", "type": "FILE", "file": "config/JwtAuthenticationFilter.java", "scope": "Source File", "signature": "package com.studysync.config"},
            {"id": "file_UserRepo_java", "label": "UserRepository.java", "name": "UserRepository.java", "type": "FILE", "file": "repository/UserRepository.java", "scope": "Source File", "signature": "package com.studysync.repository"},
            {"id": "file_SecConfig_java", "label": "SecurityConfig.java", "name": "SecurityConfig.java", "type": "FILE", "file": "config/SecurityConfig.java", "scope": "Source File", "signature": "package com.studysync.config"},
        ],
        "edges": [
            # Inheritance & Contract Relationships ([:EXTENDS] & [:IMPLEMENTS])
            {"from": "cls_AuthService", "to": "cls_BaseService", "label": "[:EXTENDS]", "relationType": "EXTENDS"},
            {"from": "cls_AuthService", "to": "iface_AuthService", "label": "[:IMPLEMENTS]", "relationType": "IMPLEMENTS"},
            {"from": "cls_JwtFilter", "to": "cls_OncePerRequest", "label": "[:EXTENDS]", "relationType": "EXTENDS"},
            {"from": "iface_UserRepo", "to": "iface_JpaRepo", "label": "[:EXTENDS]", "relationType": "EXTENDS"},
            {"from": "cls_User", "to": "iface_UserDetails", "label": "[:IMPLEMENTS]", "relationType": "IMPLEMENTS"},
            {"from": "cls_WsConfig", "to": "iface_WsConfigurer", "label": "[:IMPLEMENTS]", "relationType": "IMPLEMENTS"},

            # Class Methods ([:HAS_METHOD])
            {"from": "cls_AuthService", "to": "fn_authenticate", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_AuthService", "to": "fn_register", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_JwtService", "to": "fn_generateToken", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_JwtService", "to": "fn_extractUsername", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_JwtService", "to": "fn_isTokenValid", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_AuthController", "to": "fn_login", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_AuthController", "to": "fn_refreshToken", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_JwtFilter", "to": "fn_doFilterInternal", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "iface_UserRepo", "to": "fn_findByEmail", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_WsConfig", "to": "fn_regStomp", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},

            # Cross-Module Invocations ([:CALLS])
            {"from": "fn_login", "to": "fn_authenticate", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_refreshToken", "to": "fn_generateToken", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_authenticate", "to": "fn_generateToken", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_authenticate", "to": "fn_findByEmail", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_register", "to": "fn_generateToken", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_doFilterInternal", "to": "fn_extractUsername", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_doFilterInternal", "to": "fn_isTokenValid", "label": "[:CALLS]", "relationType": "CALLS"},

            # File Containment ([:CONTAINS_CLASS])
            {"from": "file_AuthService_java", "to": "cls_AuthService", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
            {"from": "file_JwtService_java", "to": "cls_JwtService", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
            {"from": "file_AuthController_java", "to": "cls_AuthController", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
            {"from": "file_JwtFilter_java", "to": "cls_JwtFilter", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
            {"from": "file_UserRepo_java", "to": "iface_UserRepo", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
            {"from": "file_SecConfig_java", "to": "cls_SecConfig", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
        ]
    },
    "ws-payment-gw": {
        "workspace_id": "ws-payment-gw",
        "title": "Payment-Gateway Microservice Architecture Map",
        "summary": "Full Codebase Architecture & Knowledge Graph: 16 connected entities spanning gRPC services, adapters, interfaces, and methods.",
        "nodes": [
            {"id": "cls_PaymentService", "label": "PaymentService", "name": "PaymentService", "type": "CLASS", "file": "service/payment.go", "scope": "Core Domain Struct", "signature": "type PaymentService struct"},
            {"id": "iface_Gateway", "label": "IPaymentGateway", "name": "IPaymentGateway", "type": "INTERFACE", "file": "adapter/gateway.go", "scope": "Payment Contract", "signature": "type IPaymentGateway interface"},
            {"id": "cls_StripeAdapter", "label": "StripeAdapter", "name": "StripeAdapter", "type": "CLASS", "file": "adapter/stripe.go", "scope": "Third-Party Adapter", "signature": "type StripeAdapter struct"},
            {"id": "cls_PayPalAdapter", "label": "PayPalAdapter", "name": "PayPalAdapter", "type": "CLASS", "file": "adapter/paypal.go", "scope": "Third-Party Adapter", "signature": "type PayPalAdapter struct"},
            {"id": "iface_TxRepo", "label": "TransactionRepository", "name": "TransactionRepository", "type": "INTERFACE", "file": "repository/tx.go", "scope": "DAO Contract", "signature": "type TransactionRepository interface"},
            {"id": "cls_Handler", "label": "PaymentHandler", "name": "PaymentHandler", "type": "CLASS", "file": "handler/grpc_handler.go", "scope": "gRPC Handler", "signature": "type PaymentHandler struct"},

            {"id": "fn_ProcessPayment", "label": "ProcessPayment", "name": "PaymentService.ProcessPayment", "type": "METHOD", "file": "service/payment.go", "scope": "Method", "signature": "func (s *PaymentService) ProcessPayment(ctx context.Context, req *PaymentRequest)"},
            {"id": "fn_RefundPayment", "label": "RefundPayment", "name": "PaymentService.RefundPayment", "type": "METHOD", "file": "service/payment.go", "scope": "Method", "signature": "func (s *PaymentService) RefundPayment(ctx context.Context, req *RefundRequest)"},
            {"id": "fn_StripeCharge", "label": "Charge", "name": "StripeAdapter.Charge", "type": "METHOD", "file": "adapter/stripe.go", "scope": "Method", "signature": "func (a *StripeAdapter) Charge(amount int64, currency string)"},
            {"id": "fn_PayPalExec", "label": "ExecutePayment", "name": "PayPalAdapter.ExecutePayment", "type": "METHOD", "file": "adapter/paypal.go", "scope": "Method", "signature": "func (p *PayPalAdapter) ExecutePayment(payerID string, token string)"},
            {"id": "fn_HandleWebhook", "label": "HandleWebhook", "name": "PaymentHandler.HandleWebhook", "type": "METHOD", "file": "handler/grpc_handler.go", "scope": "Method", "signature": "func (h *PaymentHandler) HandleWebhook(w http.ResponseWriter, r *http.Request)"},
            {"id": "fn_SaveRecord", "label": "SaveRecord", "name": "TransactionRepository.SaveRecord", "type": "METHOD", "file": "repository/tx.go", "scope": "Method", "signature": "func (r *TransactionRepository) SaveRecord(tx *Transaction)"},

            {"id": "file_payment_go", "label": "payment.go", "name": "payment.go", "type": "FILE", "file": "service/payment.go", "scope": "File", "signature": "package service"},
            {"id": "file_stripe_go", "label": "stripe.go", "name": "stripe.go", "type": "FILE", "file": "adapter/stripe.go", "scope": "File", "signature": "package adapter"},
            {"id": "file_handler_go", "label": "grpc_handler.go", "name": "grpc_handler.go", "type": "FILE", "file": "handler/grpc_handler.go", "scope": "File", "signature": "package handler"},
        ],
        "edges": [
            {"from": "cls_StripeAdapter", "to": "iface_Gateway", "label": "[:IMPLEMENTS]", "relationType": "IMPLEMENTS"},
            {"from": "cls_PayPalAdapter", "to": "iface_Gateway", "label": "[:IMPLEMENTS]", "relationType": "IMPLEMENTS"},
            {"from": "cls_PaymentService", "to": "fn_ProcessPayment", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_PaymentService", "to": "fn_RefundPayment", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_StripeAdapter", "to": "fn_StripeCharge", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_PayPalAdapter", "to": "fn_PayPalExec", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "cls_Handler", "to": "fn_HandleWebhook", "label": "[:HAS_METHOD]", "relationType": "HAS_METHOD"},
            {"from": "fn_HandleWebhook", "to": "fn_ProcessPayment", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_ProcessPayment", "to": "fn_StripeCharge", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "fn_ProcessPayment", "to": "fn_SaveRecord", "label": "[:CALLS]", "relationType": "CALLS"},
            {"from": "file_payment_go", "to": "cls_PaymentService", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
            {"from": "file_stripe_go", "to": "cls_StripeAdapter", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
            {"from": "file_handler_go", "to": "cls_Handler", "label": "[:CONTAINS_CLASS]", "relationType": "CONTAINS"},
        ]
    }
}


# Pre-computed structural graphs for instant, flawless UI inspection
CANONICAL_SYMBOLS = {
    "generateToken": {
        "name": "generateToken",
        "scope": "JwtService",
        "type": "Method",
        "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java",
        "line": 38,
        "signature": "public String generateToken(UserDetails userDetails)",
        "riskLevel": "HIGH",
        "riskScore": "8.8 / 10",
        "blastRadiusHops": 3,
        "affected_files": [
            "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java",
            "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java",
            "studysync-backend/src/main/java/com/studysync/studysyncbackend/controller/AuthenticationController.java",
        ],
        "nodes": [
            {"id": "target", "label": "JwtService.generateToken", "file": "JwtService.java", "type": "TARGET", "x": 400, "y": 220, "scope": "Service Method"},
            {"id": "caller_1", "label": "AuthenticationService.authenticate", "file": "AuthenticationService.java", "type": "DIRECT_CALLER", "x": 180, "y": 100, "scope": "Direct Caller (Line 52)"},
            {"id": "caller_2", "label": "AuthenticationService.register", "file": "AuthenticationService.java", "type": "DIRECT_CALLER", "x": 620, "y": 100, "scope": "Direct Caller (Line 89)"},
            {"id": "transitive_1", "label": "AuthenticationController.refreshToken", "file": "AuthenticationController.java", "type": "TRANSITIVE_CALLER", "x": 680, "y": 280, "scope": "Transitive Caller (Line 41)"},
            {"id": "callee_1", "label": "buildToken", "file": "JwtService.java", "type": "CALLEE", "x": 220, "y": 350, "scope": "Internal Helper"},
            {"id": "callee_2", "label": "Jwts.builder", "file": "io.jsonwebtoken", "type": "CALLEE", "x": 520, "y": 360, "scope": "Library Dependency"}
        ],
        "edges": [
            {"from": "caller_1", "to": "target", "label": "[:CALLS]", "hop": "1st Hop"},
            {"from": "caller_2", "to": "target", "label": "[:CALLS]", "hop": "1st Hop"},
            {"from": "transitive_1", "to": "caller_2", "label": "[:CALLS]", "hop": "2nd Hop"},
            {"from": "target", "to": "callee_1", "label": "[:CALLS]", "hop": "Internal"},
            {"from": "callee_1", "to": "callee_2", "label": "[:EXTENDS]", "hop": "Library"}
        ],
        "codeSnippet": "public String generateToken(UserDetails userDetails) {\n    return generateToken(new HashMap<>(), userDetails);\n}\n\npublic String generateToken(Map<String, Object> extraClaims, UserDetails userDetails) {\n    return buildToken(extraClaims, userDetails, jwtExpiration);\n}"
    },
    "authenticate": {
        "name": "authenticate",
        "scope": "AuthenticationService",
        "type": "Method",
        "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java",
        "line": 45,
        "signature": "public AuthenticationResponse authenticate(AuthenticationRequest request)",
        "riskLevel": "MEDIUM",
        "riskScore": "5.2 / 10",
        "blastRadiusHops": 2,
        "affected_files": [
            "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java",
            "studysync-backend/src/main/java/com/studysync/studysyncbackend/controller/AuthenticationController.java"
        ],
        "nodes": [
            {"id": "target", "label": "AuthenticationService.authenticate", "file": "AuthenticationService.java", "type": "TARGET", "x": 400, "y": 200, "scope": "Service Orchestrator"},
            {"id": "caller_1", "label": "AuthenticationController.authenticate", "file": "AuthenticationController.java", "type": "DIRECT_CALLER", "x": 220, "y": 100, "scope": "REST Endpoint"},
            {"id": "callee_1", "label": "jwtService.generateToken", "file": "JwtService.java", "type": "CALLEE", "x": 200, "y": 340, "scope": "Token Issuer"},
            {"id": "callee_2", "label": "userRepository.findByEmail", "file": "UserRepository.java", "type": "CALLEE", "x": 600, "y": 340, "scope": "DAO Access"}
        ],
        "edges": [
            {"from": "caller_1", "to": "target", "label": "[:CALLS]", "hop": "1st Hop"},
            {"from": "target", "to": "callee_1", "label": "[:CALLS]", "hop": "Internal"},
            {"from": "target", "to": "callee_2", "label": "[:CALLS]", "hop": "Internal"}
        ],
        "codeSnippet": "public AuthenticationResponse authenticate(AuthenticationRequest request) {\n    authenticationManager.authenticate(\n        new UsernamePasswordAuthenticationToken(request.getEmail(), request.getPassword())\n    );\n    var user = repository.findByEmail(request.getEmail()).orElseThrow();\n    var jwtToken = jwtService.generateToken(user);\n    return AuthenticationResponse.builder().token(jwtToken).build();\n}"
    }
}

DEMO_WORKSPACES = [
    {
        "id": "ws-study-sync",
        "name": "Study-Sync Backend",
        "repoUrl": "https://github.com/HarshaAppikatla/Study-Sync",
        "type": "git",
        "branch": "main",
        "filesCount": 211,
        "nodesCount": 2533,
        "edgesCount": 1195,
        "lastIndexed": "Just now",
        "status": "READY",
        "language": "Java / Spring Boot",
    },
    {
        "id": "ws-payment-gw",
        "name": "Payment-Gateway Microservice",
        "repoUrl": "payment-gateway-service.zip",
        "type": "zip",
        "branch": "release/v2.1",
        "filesCount": 148,
        "nodesCount": 1820,
        "edgesCount": 840,
        "lastIndexed": "2 hours ago",
        "status": "READY",
        "language": "Go / gRPC",
    },
]


DEMO_SYMBOLS_LIST = [
    {"name": "generateToken", "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java"},
    {"name": "authenticate", "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java"},
    {"name": "registerStompEndpoints", "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/config/WebSocketConfig.java"},
]



def _demo_answer(query: str, model_alias: str = "gemini-3.8-flash", execution_time: float = 0.04) -> Dict[str, Any]:
    q_lower = query.lower()
    is_code_query = any(k in q_lower for k in [
        "token", "jwt", "auth", "login", "register", "service", "blast", "radius",
        "method", "class", "caller", "code", "syntax", "refactor", "studysync", "spring"
    ])

    if is_code_query:
        text = (
            f"Based on Neo4j Graph Traversal & Qdrant Chunk Analysis for '{query}':\n\n"
            "• Target Scope Identified: JwtService.java & AuthenticationService.java\n"
            "• Direct Dependent Services: AuthenticationService.java invokes token generation inside both authenticate() (line 52) and register() (line 89).\n"
            "• Public HTTP Controllers: AuthenticationController.java relies on this payload via /api/auth/authenticate.\n\n"
            "💡 Note: To run unconstrained live AI queries, enter your Gemini or Groq API key in the Key Vault (🔑) in the top toolbar."
        )
    else:
        text = (
            f"⚠️ **Live AI Key Required**\n\n"
            f"You asked: *\"{query}\"\n\n"
            "CodeGraph is running in **Demo Mode** with mock responses because no LLM API key is configured.\n\n"
            "To chat with real AI models (Gemini 2.0 Flash, Groq LLaMA 3.3, Claude, etc.):\n"
            "1. Click the **Key Vault (🔑 Key icon)** in the top navigation bar.\n"
            "2. Paste your free **Gemini API Key** (from https://aistudio.google.com/app/apikey) or Groq key.\n"
            "3. Click **Save** and retry your question!"
        )

    return {
        "answer": text,
        "response": text,
        "model": model_alias,
        "execution_time": execution_time,
        "sources": [
            "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java",
            "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java",
        ] if is_code_query else [],
        "telemetry": {
            "model": model_alias,
            "demo_fallback": True,
            "latency_ms": int(execution_time * 1000)
        }
    }


def _extract_snippets_from_diff(diff_code: str) -> Tuple[str, str]:
    """Extracts original (removed) and refactored (added) snippets from a unified diff."""
    old_lines = []
    new_lines = []
    for line in diff_code.splitlines():
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("-"):
            old_lines.append(line[1:])
        elif line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith(" "):
            old_lines.append(line[1:])
            new_lines.append(line[1:])
    return "\n".join(old_lines).strip(), "\n".join(new_lines).strip()


def _demo_refactor(prompt: str, previous_diffs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    p_lower = prompt.lower()
    is_followup = bool(previous_diffs) or any(k in p_lower for k in ["controller", "caller", "propagate", "downstream", "null", "check", "validation"])

    if is_followup:
        diff_list = [
            {
                "file": "AuthenticationController.java",
                "old_code": "public ResponseEntity<AuthenticationResponse> authenticate(@RequestBody AuthenticationRequest request) {\n    return ResponseEntity.ok(service.authenticate(request));\n}",
                "new_code": "public ResponseEntity<AuthenticationResponse> authenticate(@RequestBody AuthenticationRequest request) {\n    if (request == null || request.getEmail() == null) {\n        throw new IllegalArgumentException(\"Authentication request cannot be null\");\n    }\n    return ResponseEntity.ok(service.authenticate(request));\n}",
                "diffCode": "--- a/controller/AuthenticationController.java\n+++ b/controller/AuthenticationController.java\n@@ -40,3 +40,6 @@\n public ResponseEntity<AuthenticationResponse> authenticate(@RequestBody AuthenticationRequest request) {\n+    if (request == null || request.getEmail() == null) {\n+        throw new IllegalArgumentException(\"Authentication request cannot be null\");\n+    }\n     return ResponseEntity.ok(service.authenticate(request));\n }",
            },
            {
                "file": "JwtService.java",
                "old_code": "public String generateToken(UserDetails userDetails) {\n    return generateToken(new HashMap<>(), userDetails);\n}",
                "new_code": "public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);\n}",
                "diffCode": "--- a/service/JwtService.java\n+++ b/service/JwtService.java\n@@ -38,3 +38,4 @@\n-public String generateToken(UserDetails userDetails) {\n-    return generateToken(new HashMap<>(), userDetails);\n+public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n+    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);",
            },
            {
                "file": "AuthenticationService.java",
                "old_code": "var jwtToken = jwtService.generateToken(user);",
                "new_code": "var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
                "diffCode": "--- a/service/AuthenticationService.java\n+++ b/service/AuthenticationService.java\n@@ -52,1 +52,1 @@\n-var jwtToken = jwtService.generateToken(user);\n+var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
            },
        ]
        for d in diff_list:
            syn = validate_code_syntax(d["file"], d.get("new_code", ""))
            d["syntax_validation"] = syn
            d["status"] = "warning" if not syn.get("is_valid", True) else "success"
        return {
            "filesChanged": len(diff_list),
            "turn": 2,
            "summary": f"Iterative refactoring turn: Propagated signature change to AuthenticationController and added input validation.",
            "diffs": diff_list,
        }

    diff_list = [
        {
            "file": "JwtService.java",
            "old_code": "public String generateToken(UserDetails userDetails) {\n    return generateToken(new HashMap<>(), userDetails);\n}",
            "new_code": "public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);\n}",
            "diffCode": "--- a/service/JwtService.java\n+++ b/service/JwtService.java\n@@ -38,3 +38,4 @@\n-public String generateToken(UserDetails userDetails) {\n-    return generateToken(new HashMap<>(), userDetails);\n+public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails, long expirationMs) {\n+    return buildToken(extraClaims, userDetails, expirationMs > 0 ? expirationMs : jwtExpiration);",
        },
        {
            "file": "AuthenticationService.java",
            "old_code": "var jwtToken = jwtService.generateToken(user);",
            "new_code": "var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
            "diffCode": "--- a/service/AuthenticationService.java\n+++ b/service/AuthenticationService.java\n@@ -52,1 +52,1 @@\n-var jwtToken = jwtService.generateToken(user);\n+var jwtToken = jwtService.generateToken(new HashMap<>(), user, 86400000L);",
        },
    ]
    for d in diff_list:
        syn = validate_code_syntax(d["file"], d.get("new_code", ""))
        d["syntax_validation"] = syn
        d["metrics_delta"] = calculate_health_delta(d.get("old_code", ""), d.get("new_code", ""), d["file"])
        d["status"] = "warning" if not syn.get("is_valid", True) else "success"
    return {
        "filesChanged": len(diff_list),
        "turn": 1,
        "summary": f"Refactoring plan applied for: '{prompt}'. Updated JwtService signature and downstream caller invocations.",
        "diffs": diff_list,
    }


