"""FastAPI entry point for the local single-user application."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from research_agent.app.service import JobService
from research_agent.app.storage import AppStorage, QueueFull
from research_agent.config import OllamaSettings
from research_agent.rag.documents import MAX_FILE_BYTES
from research_agent.security import exclusive_lock

JobID = Annotated[str, PathParam(pattern=r"^[a-f0-9]{32}$")]


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1, max_length=300)
    documents: list[str] = Field(default_factory=list, max_length=8)
    online: bool = False
    query: str | None = Field(default=None, min_length=1, max_length=256)
    parent_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    reuse_documents: bool = True
    include_previous_topic: bool = False


def create_app(root: Path | None = None, settings: OllamaSettings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        state_root = (root or Path(os.getenv("RESEARCH_APP_DIR", ".research-agent/app"))).resolve()
        with exclusive_lock(state_root / ".worker.lock", "Another API worker is using this state directory"):
            service = JobService(AppStorage(state_root), settings or OllamaSettings.from_env())
            application.state.service = service
            try:
                yield
            finally:
                service.close()

    application = FastAPI(title="Research Agent", version="0.1.0", lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @application.middleware("http")
    async def require_same_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method == "POST" and origin is not None and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin changes are disabled"}, status_code=403)
        return await call_next(request)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.post("/documents", status_code=201)
    async def upload_document(request: Request, name: Annotated[str, Query(min_length=1, max_length=100)]):
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/octet-stream":
            raise HTTPException(415, "Send the raw document as application/octet-stream")
        service: JobService = request.app.state.service
        size = 0
        try:
            with service.storage.upload(name) as (key, handle):
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise HTTPException(413, "The document exceeds 12 MiB")
                    handle.write(chunk)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {"id": key, "name": name, "bytes": size}

    @application.post("/jobs", status_code=202)
    def create_job(request: Request, job: JobRequest):
        service: JobService = request.app.state.service
        try:
            return service.create(job.topic, job.documents, job.online, job.query, job.parent_id,
                                  reuse_documents=job.reuse_documents,
                                  include_previous_topic=job.include_previous_topic)
        except QueueFull as error:
            raise HTTPException(429, str(error)) from error
        except KeyError as error:
            raise HTTPException(404, "Parent job not found") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @application.get("/jobs")
    def list_jobs(request: Request):
        return request.app.state.service.storage.list_jobs()

    @application.get("/jobs/{job_id}")
    def show_job(request: Request, job_id: JobID):
        try:
            return request.app.state.service.describe(job_id)
        except KeyError as error:
            raise HTTPException(404, "Job not found") from error

    @application.post("/jobs/{job_id}/resume", status_code=202)
    def resume_job(request: Request, job_id: JobID):
        try:
            return request.app.state.service.resume(job_id)
        except QueueFull as error:
            raise HTTPException(429, str(error)) from error
        except KeyError as error:
            raise HTTPException(404, "Job not found") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.get("/jobs/{job_id}/report", response_class=Response, responses={
        200: {"content": {"text/markdown": {}}, "description": "UTF-8 Markdown report"},
    })
    def report(request: Request, job_id: JobID, download: bool = False):
        try:
            job = request.app.state.service.storage.get(job_id)
        except KeyError as error:
            raise HTTPException(404, "Job not found") from error
        if job["report"] is None:
            raise HTTPException(409, "Report is not ready")
        headers = {"Content-Disposition": f'attachment; filename="{job_id}.md"'} if download else {}
        return Response(job["report"], media_type="text/markdown", headers=headers)

    return application


app = create_app()
