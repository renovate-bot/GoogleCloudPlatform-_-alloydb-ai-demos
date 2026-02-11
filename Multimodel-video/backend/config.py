import os
import logging
from functools import wraps
import time
from dotenv import load_dotenv

load_dotenv()

ALLOYDB_INSTANCE_URI = os.getenv("ALLOYDB_INSTANCE_URI")
PROJECT_ID = os.getenv("GCP_PROJECT")
ALLOYDB_USER = os.getenv("ALLOYDB_USER")
ALLOYDB_PASS = os.getenv("ALLOYDB_PASSWORD")
ALLOYDB_DATABASE = os.getenv("ALLOYDB_DATABASE")
ALLOYDB_TABLE_SCHEMA = os.getenv("ALLOYDB_TABLE_SCHEMA")
IP_TYPE = os.getenv("IP_TYPE")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION")
FRAME_SAMPLE_PER_SEC = os.getenv("FRAME_SAMPLE_PER_SEC")
EMBED_DIM = os.getenv("EMBED_DIM")
USE_GCS = os.getenv("USE_GCS") 

# ---------- Embedding model ----------
# Default is intfloat/e5-base (already hard-coded). Override here if you customize.
TEXT_EMBED_MODEL = os.getenv("TEXT_EMBED_MODEL")

# DEFAULT VALUES
TOP_K_DEFAULT = int(os.getenv("TOP_K_DEFAULT"))
SIM_THRESHOLD_DEFAULT = float(os.getenv("SIM_THRESHOLD_DEFAULT"))
IVF_FLAT_PROBES = int(os.getenv("IVF_FLAT_PROBES"))
HNSW_EF_SEARCH = int(os.getenv("HNSW_EF_SEARCH"))

# Configure logger (stdout for Cloud Run)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("Multimodal_video_search")

def log_execution(is_api=False):
    """
    Decorator to log start and end of function execution.
    If is_api=True, logs will have API-specific markers.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = func.__name__.upper()
            start_marker = "===== API STARTED" if is_api else "===== FUNCTION STARTED"
            end_marker = "===== API ENDED" if is_api else "===== FUNCTION ENDED"

            logger.info(f"{start_marker}: {func_name} =====")
            # logger.info(f"Args: {args}, Kwargs: {kwargs}")
            start_time = time.time()

            try:
                # ✅ Await the async function
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(f"{end_marker}: {func_name} | Duration: {duration:.2f}s =====")
                return result
            except Exception as e:
                logger.error(f"❌ ERROR in {func_name}: {e}", exc_info=True)
                raise
        return wrapper
    return decorator
