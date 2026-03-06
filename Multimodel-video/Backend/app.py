from fastapi import FastAPI, Request, HTTPException, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from db import AlloyDBClient
from config import ALLOYDB_INSTANCE_URI, ALLOYDB_USER, ALLOYDB_PASS, ALLOYDB_DATABASE, IP_TYPE, logger, log_execution
from service import multimodal_video_search, categories_duration
from typing import List, Dict, Any, AsyncIterator, Generator
import uvicorn

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
    alloydb_client = AlloyDBClient(ALLOYDB_INSTANCE_URI, ALLOYDB_USER, ALLOYDB_PASS, ALLOYDB_DATABASE, IP_TYPE)
    engine = alloydb_client.create_engine()
    yield
    logger.info("Shutting down and disposing database engine...")
    if engine:
        engine.dispose()

app = FastAPI(
    title="Multimodal Video Search API",
    description="An API for Multimodal Video Search using AlloyDB database.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CategoriesDurationResponse(BaseModel):
    categories_duration : Dict[str, Dict[str, Any]]

class VideoSearch(BaseModel):
    query : str
    categories : str
    duration : int
    input_type : str

    
class VideoSearchResponse(BaseModel):
    video_details : Dict[str, Any]
    
@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
def root(request: Request) -> HTMLResponse:
    """
    Serves the root endpoint with a welcome message and a link to the API docs.

    Args:
        request (Request): The incoming request object.

    Returns:
        HTMLResponse: An HTML page with a welcome message.
    """
    base_url = str(request.base_url).rstrip("/")
    docs_url = f"{base_url}/docs"
    return f"""
    <!DOCTYPE html>
    <html>
        <head><title>Welcome</title></head>
        <body>
            <h2>Welcome to the Multimodal Video FastAPI Service!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """

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


@app.get(
    "/categories_duration",
    response_model=CategoriesDurationResponse,
    responses={
        404: {"description": "Problem fetching details"},
    },
    summary="Provides details for the All categories and duration dropdown",
    description="Returns the dictionary of min and max duration for the All categories.")
@log_execution(is_api=True)
async def get_categories_duration(db_engine: Engine = Depends(get_db)) -> dict:
    """
    Retrieves available video categories and the min/max video duration.

    Args:
        db_engine (Engine): The database engine dependency.

    Returns:
        CategoriesDurationResponse: An object containing lists of categories and duration range.
    """
    categories_duration_result = categories_duration(db_engine)
    if "error" in categories_duration_result:
        raise HTTPException(status_code=404, detail=categories_duration_result["error"])
    else:
        return {"categories_duration":categories_duration_result}

@app.post(
    "/video_search",
    response_model=VideoSearchResponse,
    responses={
        404: {"description": "Invalid input"},
    },
    summary="Provides the results for multimodal video search",
    description="Returns a list of video data for the given query.")
@log_execution(is_api=True)
async def search_video(request: VideoSearch, db_engine: Engine = Depends(get_db)) -> dict:
    """
    Performs a multimodal search for videos based on a query, categories, and duration.

    Args:
        request (VideoSearch): The search criteria from the request body.
        db_engine (Engine): The database engine dependency.

    Returns:
        VideoSearchResponse: A dictionary containing a list of video details matching the search.
    """
    video_details = multimodal_video_search(db_engine, request.query, request.categories, request.duration,request.input_type)
    if "error" in video_details:
        raise HTTPException(status_code=404, detail=video_details["error"])
    else:
        return {"video_details": video_details}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
