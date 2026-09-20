# 🔐 Cybersecurity RAG System

A production-oriented **Retrieval-Augmented Generation (RAG)** system for answering cybersecurity questions using trusted NIST security documents.

The system combines **dense retrieval, keyword retrieval, Reciprocal Rank Fusion (RRF), cross-encoder reranking, and an LLM** to generate grounded answers with source references.

---

## 🚀 Project Overview

Large Language Models can generate useful answers, but they may hallucinate information or lack access to domain-specific knowledge.

This project addresses that problem by building a cybersecurity-focused RAG pipeline that retrieves relevant information from NIST publications before generating an answer.

### Core Pipeline

```text
User Question
      │
      ▼
Query Processing
      │
      ├───────────────┐
      ▼               ▼
Dense Retrieval    BM25 Retrieval
BGE-small          Keyword Search
Top-20             Top-20
      │               │
      └───────┬───────┘
              ▼
        RRF Fusion
         Top-20
              │
              ▼
     Cross-Encoder Reranker
            Top-5
              │
              ▼
       Context Builder
              │
              ▼
          Groq LLM
              │
              ▼
      Grounded Answer
        + Citations