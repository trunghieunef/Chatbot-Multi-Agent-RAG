"""
RAG configuration for Google Gemini and vector store.
"""

import os

# Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "400"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "80"))

COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
RERANK_PROVIDER = os.getenv("RERANK_PROVIDER", "cohere")
RERANK_MODEL = os.getenv("RERANK_MODEL", "rerank-multilingual-v3.0")
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))

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

# Geocoding
GEOCODER_PROVIDER = os.getenv("GEOCODER_PROVIDER", "nominatim")
GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "realestate-chatbot/0.1 (contact@example.com)")
GEOCODER_RATE_LIMIT_SECONDS = float(os.getenv("GEOCODER_RATE_LIMIT_SECONDS", "1.0"))
GOONG_API_KEY = os.getenv("GOONG_API_KEY", "")

# Intent extraction
INTENT_EXTRACTOR = os.getenv("INTENT_EXTRACTOR", "rule")
GEMINI_INTENT_MODEL = os.getenv("GEMINI_INTENT_MODEL", "gemini-2.0-flash")
