import asyncio
import json
import os
import uuid
from fastapi import APIRouter, File, UploadFile, Request, Form, HTTPException
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

class ContactRequest(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None

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


# ─── Contacts (also the recipient allowlist) ──────────────────────────────────
@router.get("/contacts")
def list_contacts():
    return {"contacts": orchestrator.contacts.list_contacts()}


@router.post("/contacts")
def upsert_contact(req: ContactRequest):
    try:
        contact = orchestrator.contacts.upsert(req.name, req.email, req.phone, req.telegram)
        return {"status": "saved", "contact": contact}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/contacts/{name}")
def delete_contact(name: str):
    if orchestrator.contacts.delete(name):
        return {"status": "deleted", "name": name}
    raise HTTPException(status_code=404, detail=f"No contact named '{name}'.")


@router.get("/telegram/chats")
def telegram_chats():
    """
    Discovery helper: list everyone who has recently messaged the bot, with their
    chat_id — so you can save them as a contact without hunting through the API.
    """
    if not orchestrator.telegram.available:
        raise HTTPException(status_code=400, detail=orchestrator.telegram._init_error)
    try:
        return {"chats": orchestrator.telegram.recent_chats(), "bot": orchestrator.telegram.bot_username}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─── Actions: approve / reject a draft ────────────────────────────────────────
# The send lives here and nowhere else. The LLM can only ever create a draft; the
# transition from draft to actually-sent requires this explicit human call.
@router.get("/actions/pending")
def list_pending_actions():
    return {"pending": orchestrator.actions.list_pending()}


@router.post("/actions/{action_id}/approve")
def approve_action(action_id: str):
    draft = orchestrator.actions.get(action_id)
    if not draft:
        raise HTTPException(status_code=404, detail="That draft no longer exists.")

    payload = draft["payload"]
    kind = draft["kind"]

    # Re-check the allowlist at send time. The draft could have been sitting around, and
    # this is the last gate before something irreversible happens.
    if kind == "email":
        if not orchestrator.contacts.is_allowed_email(payload["to"]):
            orchestrator.actions.resolve(action_id, "failed", "Recipient is not a saved contact.")
            raise HTTPException(status_code=403, detail=f"{payload['to']} is not a saved contact.")
        try:
            msg_id = orchestrator.gmail.send(payload["to"], payload["subject"], payload["body"])
            resolved = orchestrator.actions.resolve(action_id, "sent", msg_id)
            return {"status": "sent", "action": resolved}
        except Exception as e:
            orchestrator.actions.resolve(action_id, "failed", str(e))
            raise HTTPException(status_code=502, detail=f"Failed to send email: {e}")

    if kind == "whatsapp":
        if not orchestrator.contacts.is_allowed_phone(payload["to"]):
            orchestrator.actions.resolve(action_id, "failed", "Recipient is not a saved contact.")
            raise HTTPException(status_code=403, detail=f"{payload['to']} is not a saved contact.")
        try:
            sid = orchestrator.whatsapp.send(payload["to"], payload["body"])
            resolved = orchestrator.actions.resolve(action_id, "sent", sid)
            return {"status": "sent", "action": resolved}
        except Exception as e:
            orchestrator.actions.resolve(action_id, "failed", str(e))
            raise HTTPException(status_code=502, detail=str(e))

    if kind == "telegram":
        if not orchestrator.contacts.is_allowed_telegram(payload["to"]):
            orchestrator.actions.resolve(action_id, "failed", "Recipient is not a saved contact.")
            raise HTTPException(status_code=403, detail="That recipient is not a saved contact.")
        try:
            msg_id = orchestrator.telegram.send(payload["to"], payload["body"])
            resolved = orchestrator.actions.resolve(action_id, "sent", msg_id)
            return {"status": "sent", "action": resolved}
        except Exception as e:
            orchestrator.actions.resolve(action_id, "failed", str(e))
            raise HTTPException(status_code=502, detail=str(e))

    raise HTTPException(status_code=400, detail=f"Unknown action kind '{kind}'.")


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: str):
    resolved = orchestrator.actions.resolve(action_id, "rejected")
    if not resolved:
        raise HTTPException(status_code=404, detail="That draft no longer exists.")
    return {"status": "rejected", "action": resolved}


@router.get("/actions/audit")
def action_audit(limit: int = 100):
    """Every action attempted — sent, rejected, and blocked."""
    return {"audit": orchestrator.actions.read_audit(limit)}


@router.get("/integrations/status")
def integrations_status():
    return {
        "gmail": {
            "available": orchestrator.gmail.available,
            "account": orchestrator.gmail.email_address,
            "error": orchestrator.gmail._init_error,
        },
        "whatsapp": {
            "available": orchestrator.whatsapp.available,
            "error": orchestrator.whatsapp._init_error,
        },
        "telegram": {
            "available": orchestrator.telegram.available,
            "bot": orchestrator.telegram.bot_username,
            "error": orchestrator.telegram._init_error,
        },
        "contacts": len(orchestrator.contacts.contacts),
    }

@router.get("/stream")
async def pipeline_stream(query: str, history: str = "", model_choice: str = "auto", request: Request = None):
    """
    Server-Sent Events endpoint to stream pipeline status to the frontend.
    Text-only queries. Accepts model_choice: 'auto', 'local', or 'api'.
    """
    async def event_generator():
        try:
            async for event in orchestrator.process_query_stream(query, history, model_choice=model_choice):
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
    model_choice: str = Form("auto"),
    images: list[UploadFile] = File(default=[]),
):
    """
    SSE endpoint that also accepts multiple optional image uploads.
    The images are analyzed by a vision model and their descriptions are
    injected into the RAG pipeline as additional context.
    Accepts model_choice: 'auto', 'local', or 'api'.
    """
    image_context = ""
    img_paths = []
    
    if images and len(images) > 0 and images[0].filename:
        # Save uploaded images
        for image in images:
            if not image.filename:
                continue
            ext = os.path.splitext(image.filename)[1] or ".png"
            img_filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
            img_path = os.path.join("uploads", img_filename)
            
            content = await image.read()
            with open(img_path, "wb") as f:
                f.write(content)
            img_paths.append(img_path)
        
        # Analyze images
        if img_paths:
            image_context = await image_analyzer.analyze(img_paths, query)
    
    async def event_generator():
        try:
            # Emit image analysis step if images were provided
            if image_context:
                yield json.dumps({
                    "model": "Image Analyzer",
                    "status": "Completed",
                    "action": f"Extracted visual data from {len(img_paths)} uploaded image(s)"
                })
            
            async for event in orchestrator.process_query_stream(query, history, image_context=image_context, model_choice=model_choice):
                if await request.is_disconnected():
                    break
                yield event
        except Exception as e:
            yield json.dumps({"model": "System Error", "status": "Failed", "action": str(e)})

    return EventSourceResponse(event_generator())
