import asyncio
import json
import os
import uuid
from fastapi import APIRouter, File, UploadFile, Request, Form
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from orchestrator.master_llm import MasterOrchestrator
from ingestion.document_parser import DocumentParser
from ingestion.web_crawler import WebCrawler
from retrieval.image_analyzer import ImageAnalyzer

router = APIRouter()

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    sources: list[str]

class CrawlRequest(BaseModel):
    url: str
    max_pages: int = 20
    max_depth: int = 2

# Global instances
orchestrator = MasterOrchestrator()
doc_parser = DocumentParser()
web_crawler = WebCrawler()
image_analyzer = ImageAnalyzer()

@router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Main endpoint. In a real system you might return a job ID and stream via SSE.
    For this demo, we'll let the SSE stream handle the generation flow visually, 
    so this endpoint just returns 'started'.
    """
    return QueryResponse(answer="Query started. Listen to SSE for results.", sources=[])

@router.post("/ingest")
async def ingest_document(file: UploadFile = File(...)):
    """
    Endpoint for uploading and indexing documents.
    """
    documents = await doc_parser.parse_upload_file(file)
    for doc in documents:
        doc.metadata["source"] = file.filename
        
    orchestrator.vector_db.add_documents(documents)
    
    return {"filename": file.filename, "status": "Ingested successfully", "chunks": len(documents)}

@router.post("/crawl")
async def crawl_website(request: CrawlRequest):
    """
    Synchronous crawl endpoint. Crawls the website and ingests all content.
    """
    documents = await asyncio.to_thread(
        web_crawler.crawl_sync, request.url, request.max_pages, request.max_depth
    )
    
    if documents:
        orchestrator.vector_db.add_documents(documents)
    
    return {
        "url": request.url,
        "pages_crawled": len(set(d.metadata["source"] for d in documents)),
        "total_chunks": len(documents),
        "status": "Crawled and ingested successfully"
    }

@router.get("/crawl/stream")
async def crawl_stream(url: str, max_pages: int = 20, max_depth: int = 2, request: Request = None):
    """
    SSE streaming crawl endpoint. Streams progress events to the frontend.
    At the end, ingests all crawled documents into the vector database.
    """
    async def event_generator():
        documents = []
        try:
            async for event_json in web_crawler.crawl_stream(url, max_pages, max_depth):
                if request and await request.is_disconnected():
                    break
                
                event_data = json.loads(event_json)
                yield event_json
                
                # If crawl is completed, collect all documents from the crawl
                if event_data["status"] == "completed":
                    # Re-crawl synchronously to get the documents for ingestion
                    docs = await asyncio.to_thread(
                        web_crawler.crawl_sync, url, max_pages, max_depth
                    )
                    if docs:
                        orchestrator.vector_db.add_documents(docs)
                        yield json.dumps({
                            "status": "ingested",
                            "page_url": url,
                            "pages_done": event_data["pages_done"],
                            "total_found": event_data["total_found"],
                            "message": f"Ingested {len(docs)} chunks into vector database",
                            "total_chunks": len(docs),
                        })
        except Exception as e:
            yield json.dumps({
                "status": "error",
                "page_url": url,
                "pages_done": 0,
                "total_found": 0,
                "message": f"Crawl failed: {str(e)}",
            })

    return EventSourceResponse(event_generator())

@router.get("/health")
def health_check():
    """
    Health check.
    """
    return {"status": "ok"}

@router.get("/stream")
async def pipeline_stream(query: str, history: str = "", request: Request = None):
    """
    Server-Sent Events endpoint to stream pipeline status to the frontend.
    Text-only queries.
    """
    async def event_generator():
        try:
            async for event in orchestrator.process_query_stream(query, history):
                if request and await request.is_disconnected():
                    break
                yield event
        except Exception as e:
            yield json.dumps({"model": "System Error", "status": "Failed", "action": str(e)})

    return EventSourceResponse(event_generator())


@router.post("/stream")
async def pipeline_stream_with_image(
    request: Request,
    query: str = Form(...),
    history: str = Form(""),
    image: UploadFile = File(None),
):
    """
    SSE endpoint that also accepts an optional image upload.
    The image is analyzed by a vision model and the description is
    injected into the RAG pipeline as additional context.
    """
    image_context = ""
    
    if image and image.filename:
        # Save uploaded image
        ext = os.path.splitext(image.filename)[1] or ".png"
        img_filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
        img_path = os.path.join("uploads", img_filename)
        
        content = await image.read()
        with open(img_path, "wb") as f:
            f.write(content)
        
        # Analyze image
        image_context = await image_analyzer.analyze(img_path, query)
    
    async def event_generator():
        try:
            # Emit image analysis step if image was provided
            if image_context:
                yield json.dumps({
                    "model": "Image Analyzer",
                    "status": "Completed",
                    "action": "Extracted visual data from uploaded image"
                })
            
            async for event in orchestrator.process_query_stream(query, history, image_context=image_context):
                if await request.is_disconnected():
                    break
                yield event
        except Exception as e:
            yield json.dumps({"model": "System Error", "status": "Failed", "action": str(e)})

    return EventSourceResponse(event_generator())
