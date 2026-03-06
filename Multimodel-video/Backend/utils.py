# ----------------------------
# Server-side query visibility: application_name + pg_stat_activity
# ----------------------------

from typing import Optional, List, Dict, Any, Tuple, Union
from urllib.parse import quote
import requests

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.elements import TextClause

# # ----------------------------
# # GCS helpers
# # ----------------------------

def gcs_uri_to_public_url(gcs_uri: str) -> str:
    """
    Convert gs://bucket/object -> https://storage.googleapis.com/bucket/object
    Encodes the object path safely for HTTP.

    Args:
        gcs_uri: e.g., 'gs://alloydb-multimodel/data/collision_with_motorcycle/clip_15.mp4'

    Returns:
        https public URL usable with st.video()
    """
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri!r}")

    _, rest = gcs_uri.split("gs://", 1)
    # Ensure there is at least one "/" after bucket name
    if "/" not in rest:
        raise ValueError(f"GCS URI missing object path: {gcs_uri!r}")

    bucket, object_name = rest.split("/", 1)

    # Safely encode the object path (spaces, special chars)
    # NOTE: quote keeps forward slashes unencoded by default, so we pass safe="/"
    encoded_object = quote(object_name, safe="/")
    return f"https://storage.googleapis.com/{bucket}/{encoded_object}"



def check_public_url_head(url: str, timeout: int = 8):
    try:
        r = requests.head(url, timeout=timeout)
        ctype = r.headers.get("Content-Type", "")
        return (r.status_code == 200, ctype, r.status_code)
    except requests.RequestException:
        return (False, "", 0)


def preview_sql_for_display(
    statement: Union[str, TextClause],
    params: Dict[str, Any],
    engine: Engine,
) -> str:
    """
    Display-only SQL preview.
    Inlines small params, but masks huge payloads (like base64 images).
    Do NOT execute the returned string.
    """

    def _mask_if_huge(key: str, val: Any) -> Any:
        # Mask only specific keys (recommended)
        HUGE_KEYS = {"image_base64", "image", "content_base64"}

        if key in HUGE_KEYS and isinstance(val, str):
            n = len(val)
            # show prefix/suffix for debugging, but keep it small
            prefix = val[:30]
            suffix = val[-30:] if n > 60 else ""
            return f"<omitted {key}:len={n} '{prefix}...{suffix}'>"

        # Generic safety: if any string is huge, mask it too
        if isinstance(val, str) and len(val) > 2000:
            n = len(val)
            return f"<omitted {key}:len={n}>"

        return val

    # 1) Normalize to TextClause
    stmt: TextClause = statement if isinstance(statement, TextClause) else text(statement)

    # 2) Bind masked parameters
    safe_params = {k: _mask_if_huge(k, v) for k, v in (params or {}).items()}
    stmt = stmt.bindparams(**safe_params)

    # 3) Compile with literal binds (safe_params are small now)
    compiled = stmt.compile(
        dialect=engine.dialect,
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)