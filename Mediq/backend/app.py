from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager
from service import mediq_search
from db import AlloyDBClient
from typing import List, Dict, Any, AsyncIterator, Generator
from config import INSTANCE_URI, DB_USER, DB_PASSWORD, DB_NAME , log_execution, logger

engine: Engine | None = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Asynchronous context manager to handle the application's lifespan events.

    This function is executed when the application starts up and shuts down.
    It creates and disposes of the AlloyDB database engine.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    global engine
    logger.info("Starting up and creating database engine...")
    # alloydb_client = AlloyDBClient(ALLOYDB_INSTANCE_URI, ALLOYDB_USER, ALLOYDB_PASS, ALLOYDB_DATABASE, IP_TYPE)
    alloydb_client = AlloyDBClient(INSTANCE_URI, DB_USER, DB_PASSWORD, DB_NAME)
    engine = alloydb_client.create_engine()
    yield
    logger.info("Shutting down and disposing database engine...")
    if engine:
        engine.dispose()

def get_db() -> Generator[Engine, None, None]:
    """
    FastAPI dependency to provide a database engine session.

    Yields:
        Engine: The SQLAlchemy engine instance.

    Raises:
        HTTPException: If the database engine is not initialized.
    """
    if not engine:
        raise HTTPException(status_code=500, detail="Database connection not initialized.")
    yield engine


app = FastAPI(title="Medical IQ Alloydb API",
    description="An API for Smart Medical Intelligence Platform using Alloydb database.",
    lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class MedIQSearch(BaseModel):
    question: str

@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
def root(request: Request):
    base_url = str(request.base_url).rstrip("/")
    docs_url = f"{base_url}/docs"
    return f"""
    <!DOCTYPE html>
    <html>
        <head><title>Welcome</title></head>
        <body>
            <h2>Welcome to the MedIQ Smart Medical Intelligence Platform FastAPI Service!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """


@app.post(
    "/medIqSearch",
    summary="Provides the results for medical search",
    description="Searches the medical related query and gives the details realated to the search query")
@log_execution(is_api=True)
async def perform_mediq_search(request: MedIQSearch, engine: Engine = Depends(get_db)) -> dict:
    """
    Handles medical query search and returns relevant results.

    Args:
        request (MedIQSearch): The request object containing the search question.

    Returns:
        dict: A dictionary containing the search results or error details.
    """
    # alloydb_client = AlloyDBClient(INSTANCE_URI, DB_USER, DB_PASSWORD, DB_NAME)
    # engine = alloydb_client.create_engine()
    result = await mediq_search(engine,request.question)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
