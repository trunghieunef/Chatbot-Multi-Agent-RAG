"""
RAG configuration for Google Gemini and vector store.
"""

import os

# Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_EMBEDDING_MODEL = "models/text-embedding-004"

# ChromaDB
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))

# Collection names
COLLECTION_LISTINGS = "real_estate_listings"
COLLECTION_PROJECTS = "real_estate_projects"
COLLECTION_KNOWLEDGE = "legal_knowledge"

# RAG settings
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
TOP_K_RESULTS = 10
