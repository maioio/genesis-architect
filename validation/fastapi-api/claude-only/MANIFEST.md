# Claude Only - FastAPI Task API - Manifest

## Files created
- main.py
- models.py
- tests/test_main.py
- requirements.txt

## Tests written
- test_health: GET /health returns 200
- test_create_task: POST /tasks creates and returns task
- test_list_tasks: GET /tasks returns list
- test_get_task_not_found: GET /tasks/:id returns 404 when missing
- test_update_task: PUT /tasks/:id updates fields
- test_delete_task: DELETE /tasks/:id removes task

## Security measures included
- None

## Error handling included
- 404 on missing task ID
- Pydantic validation on input

## What is NOT present
- No DB session lifecycle management
- No connection pool configuration
- No SQLAlchemy (in-memory dict only)
- No async session handling
- No input size limits
- No rate limiting
- No CORS configuration
- No auth
