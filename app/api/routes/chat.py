from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.folder import Folder
from app.schemas.document import ChatRequest, ChatResponse
from app.services.indexer_service import indexer_service
from app.services.openai_service import openai_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    chat_request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ask a question and get an AI-generated answer based on documents in the folder.
    This implements the RAG (Retrieval Augmented Generation) pattern.

    Uses Azure AI Search Integrated Vectorization with folder isolation via filtering.
    """
    # Verify folder ownership
    result = await db.execute(
        select(Folder).where(
            Folder.id == chat_request.folder_id,
            Folder.user_id == current_user.id
        )
    )
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found"
        )

    try:
        # Step 1: Generate embedding for the query
        logger.info(f"Generating embedding for query: {chat_request.query}")
        query_embedding = await openai_service.generate_embedding(chat_request.query)

        # Step 2: Search with folder isolation
        # The indexer service uses a single index with folder_id filtering
        # This ensures users only see their own folder's documents
        logger.info(f"Searching folder {folder.id} for relevant chunks")
        search_results = await indexer_service.search_with_folder_filter(
            query=chat_request.query,
            query_vector=query_embedding,
            folder_id=folder.id,
            top=5
        )

        if not search_results:
            return ChatResponse(
                answer="I couldn't find any relevant information in the documents to answer your question.",
                sources=[]
            )

        # Step 3: Generate response using Azure OpenAI with retrieved context
        logger.info("Generating response with Azure OpenAI")
        answer = await openai_service.generate_response(
            query=chat_request.query,
            context=search_results
        )

        # Format sources from chunks
        sources = [
            {
                "filename": result.get("title"),
                "relevance_score": result.get("score"),
                "document_id": result.get("document_id"),
                "page_number": result.get("page_number")
            }
            for result in search_results
        ]

        return ChatResponse(
            answer=answer,
            sources=sources
        )

    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process chat request"
        )
