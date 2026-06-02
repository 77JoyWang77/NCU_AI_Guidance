"""Application-wide readiness flags. Set by lifespan; read by routes and health checks."""

pdf_chat_ready: bool = False
rag_ready: bool = False
