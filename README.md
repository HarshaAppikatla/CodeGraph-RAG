# CodeGraph-RAG: Autonomous AST & Code-Dependency Agent 🚀

**CodeGraph-RAG** is an advanced, production-grade Retrieval-Augmented Generation (RAG) system built to parse, index, and reason over complex codebases. By combining **AST (Abstract Syntax Tree) structural graph dependencies** with **dense vector embeddings**, it performs hybrid context expansion to answer deep technical questions about software architecture.

---

## 🌟 Key Features

- **AST Structural Parsing**: Native Python `ast` parsing to extract functions, classes, methods, docstrings, and import relationships.
- **Knowledge Graph Ingestion**: Models file-function containment and class hierarchies in **Neo4j AuraDB**.
- **Dense Vector Indexing**: Generates semantic embeddings with **Google Gemini (`gemini-embedding-001`)** and stores them in a local **Qdrant** vector database.
- **Hybrid Context Expansion**: Merges top-$k$ semantic similarity search with graph dependency traversal for dual-stream context.
- **LLM Reasoning**: Synthesizes technical answers using **Gemini (`gemini-3.8-flash`)**.
- **Automated Benchmark Evaluation**: Evaluates response quality (Faithfulness & Relevancy) with backoff retry handling.

---

## 🏗️ Architecture Overview

                    +----------------------+
                    |   Python Source Code |
                    +----------+-----------+
                               |
                     [AST Parser Engine]
                               |
             +-----------------+-----------------+
             |                                   |
  [Neo4j Graph Store]                  [Qdrant Vector Store]
(File-Function Dependency)               (3072d Gemini Embeddings)|                                   |+-----------------+-----------------+|[Hybrid RAG Agent]|[Gemini 3.8 Flash Synthesis]
---

## 🚀 Quickstart Guide

### 1. Requirements
- Python 3.14+
- Neo4j AuraDB (Cloud Instance)
- Google Gemini API Key

### 2. Environment Setup
Create a `.env` file in the root directory:

```env
GEMINI_API_KEY="your_gemini_api_key"
NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="your_password"
3. Run Pipeline & Interactive CLIBashpython main.py
4. Run Benchmark Evaluation SuiteBashpython -m evaluation.evaluator
📊 Evaluation ResultsAcross standard benchmark evaluation tests using automated LLM-as-a-Judge scoring:MetricScoreFaithfulness5 / 5Relevancy5 / 5Avg. Query Latency15 - 18 seconds🛠️ Tech StackLanguage: Python 3.14+Graph Database: Neo4j AuraDBVector Database: QdrantLLM & Embeddings: Google Gemini API (gemini-3.8-flash, gemini-embedding-001)Environment: GitHub Codespaces
---

### Step 3: Run Interactive Mode

Execute:

```bash
python main.py