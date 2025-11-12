from openai import AsyncAzureOpenAI
from app.core.config import settings
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self):
        self.client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
        self.deployment = settings.AZURE_OPENAI_DEPLOYMENT
        self.embedding_deployment = settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using Azure OpenAI.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector as list of floats
        """
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_deployment,
                input=text
            )

            embedding = response.data[0].embedding
            logger.info(f"Generated embedding vector of dimension {len(embedding)}")

            return embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

    async def generate_response(
        self,
        query: str,
        context: List[Dict[str, Any]],
        max_tokens: int = 1000
    ) -> str:
        """
        Generate a response using Azure OpenAI with RAG context.

        Args:
            query: The user's question
            context: List of relevant document chunks from search
            max_tokens: Maximum tokens in response

        Returns:
            Generated response text
        """
        try:
            # Format context from search results
            context_text = self._format_context(context)

            # Create the system message
            system_message = """You are a helpful AI assistant that answers questions based on the provided documents.
            Use the context provided to answer questions accurately. If the context doesn't contain relevant information
            to answer the question, say so clearly. Always cite which document your information comes from."""

            # Create the user message with context
            user_message = f"""Context from documents:
{context_text}

Question: {query}

Please provide a detailed answer based on the context above."""

            # Call Azure OpenAI
            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )

            answer = response.choices[0].message.content
            logger.info("Generated response from Azure OpenAI")

            return answer

        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise

    def _format_context(self, context: List[Dict[str, Any]]) -> str:
        """
        Format search results into context for the prompt.

        Context now comes from semantic chunks with metadata.
        """
        if not context:
            return "No relevant documents found."

        formatted_parts = []
        for i, chunk in enumerate(context, 1):
            title = chunk.get("title", "Unknown")
            content = chunk.get("content", "")
            score = chunk.get("score", 0)
            page_number = chunk.get("page_number")

            # Truncate very long content (chunks are already ~2000 chars from Text Split skill)
            if len(content) > 2000:
                content = content[:2000] + "..."

            # Include page number if available
            page_info = f", Page: {page_number}" if page_number else ""

            formatted_parts.append(
                f"Chunk {i} (File: {title}{page_info}, Relevance: {score:.2f}):\n{content}\n"
            )

        return "\n".join(formatted_parts)


# Singleton instance
openai_service = OpenAIService()
