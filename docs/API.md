# API Reference

## Base URL
```
http://localhost:8000/api
```

## Endpoints

### Health Check
```
GET /health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Query Stream (Text)
```
GET /stream?query=<query>&history=<optional_history>
```

Returns Server-Sent Events stream of pipeline status.

### Query with Image
```
POST /stream
Form Data:
- query: string
- history: string (optional)
- images: file[] (optional)
```

Returns SSE stream with image analysis.

### Upload Document
```
POST /ingest
Form Data:
- file: document file
```

Response:
```json
{
  "filename": "document.pdf",
  "status": "Ingested successfully",
  "chunks": 42
}
```

### Crawl Website
```
GET /crawl/stream?url=<url>&max_pages=20&max_depth=2
```

Returns SSE stream of crawl progress.

## Response Format

All SSE responses follow this format:
```json
{
  "model": "Component Name",
  "status": "Processing|Completed|Failed",
  "action": "Description of action",
  "details": {"optional": "data"}
}
```

## Error Handling

Errors are returned as:
```json
{
  "model": "System Error",
  "status": "Failed",
  "action": "Error message details"
}
```
