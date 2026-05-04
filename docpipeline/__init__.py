"""
docpipeline — AI document processing pipeline.

Architecture: 4 bricks × N format pipelines.
  - parsing    : Standardized DataFrame extraction per format
  - retrieval  : DataFrame filtering (keyword → regex → embeddings → SQL)
  - generation : Unified LLM orchestration
  - translation: Style-preserving document translation
  - excel_agent: Natural-language SQL agent for spreadsheets
"""

__version__ = "0.1.0"
