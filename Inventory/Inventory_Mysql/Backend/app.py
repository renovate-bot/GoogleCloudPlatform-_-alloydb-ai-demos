from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Depends,
)
from sqlalchemy.engine import Engine
from pydantic import BaseModel
from src.agents.coordinator import recommend_replenishment
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn
from src.db.query import (
    inventory_overview,
    recent_purchase_order,
    add_product,
    edit_product,
    edit_purchase_order_recommedation,
    approve_po_recommendation,
)
import asyncio
import pandas as pd
from src.db.mysql_connect import mysql_client
from src.utils.logger import logger, log_execution


def get_engine():
    """
    Provides a SQLAlchemy `Engine` instance for database access.

    Returns:
        sqlalchemy.engine.Engine: Engine constructed by the shared MySQL client.

    Notes:
        - This function is used as a FastAPI dependency (`Depends(get_engine)`)
          to inject an engine into request handlers.
    """
    return mysql_client.get_engine()


# ---------------------------------------------------------------------------
# FastAPI application setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Inventory Management MySQL API",
    description="An API for Agentic inventory management using MySQL database.",
)

clients = []


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """
    WebSocket endpoint for pushing real-time status updates from agents.

    Workflow:
        1) Accept incoming client connection and register it.
        2) Keep the connection alive with a simple sleep loop.
        3) On disconnect or error, remove the client from the registry.

    Args:
        websocket (WebSocket): FastAPI WebSocket connection object.

    Notes:
        - The `broadcast_status` utility uses `clients` to publish updates.
        - We iterate over a copy in the broadcaster to avoid mutation during send.
    """
    await websocket.accept()
    clients.append(websocket)
    print(f"✅ Client connected. Total clients: {len(clients)}", flush=True)

    try:
        while True:
            await asyncio.sleep(1)  # Keep alive
    except WebSocketDisconnect:
        print("❌ Client disconnected", flush=True)
        if websocket in clients:
            clients.remove(websocket)
    except Exception as e:
        print(f"⚠️ Error in WebSocket loop: {e}", flush=True)
        if websocket in clients:
            clients.remove(websocket)


async def broadcast_status(message: str):
    """
    Broadcasts a JSON status payload to all connected WebSocket clients.

    Args:
        message (str): Human-readable status message emitted by agents.
    """
    # ✅ Iterate over a copy to avoid mutation during iteration

    for client in clients[:]:  # ✅ Iterate over a copy
        try:
            await client.send_json({"status": message})
        except (WebSocketDisconnect, RuntimeError) as e:
            print(f"⚠️ Error sending to client: {e}. Removing client.", flush=True)
            if client in clients:
                clients.remove(client)


# ---------------------------------------------------------------------------
# CORS middleware: allow all origins, methods, and headers for demo convenience.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# ---------------------------------------------------------------------------
# Request models (Pydantic) for typed API payloads
# ---------------------------------------------------------------------------
class EngineSelection(BaseModel):
    """
    Placeholder model for engine selection requests.

    Attributes:
        engine (str): Engine identifier or label.
    """

    engine: str


class ProductStock(BaseModel):
    """
    Request schema for adding/updating product stock details.

    Attributes:
        sku (str): Product SKU.
        name (str): Product name/title.
        category (str): Product category label.
        store_id (int): Store identifier.
        on_hand (int): Units currently available.
        safety_stock (int): Buffer stock target.
        reorder_point (int): Threshold for replenishment.
        in_transit (int): Units expected to arrive.
        location (str): Store location (contextual).
    """

    sku: str
    name: str
    category: str
    store_id: int
    on_hand: int
    safety_stock: int
    reorder_point: int
    in_transit: int
    location: str


class ReplenishmentRecommendation(BaseModel):
    """
    Request schema for generating a replenishment recommendation.

    Attributes:
        sku (str): Product SKU to evaluate.
        store_id (int): Store identifier.
        horizon_days (int): Forecast horizon in days.
    """

    sku: str
    store_id: int
    horizon_days: int


class EditPORecommendation(BaseModel):
    """
    Request schema for editing a purchase order recommendation.

    Attributes:
        po_id (int): Purchase order identifier to modify.
        sku (str): SKU whose line will be changed.
        new_supplier_id (int): New supplier to assign.
        new_quantity (int): Updated line quantity.
    """

    po_id: int
    sku: str
    new_supplier_id: int
    new_quantity: int


class ApprovePORecommendation(BaseModel):
    """
    Request schema for approving a purchase order recommendation.

    Attributes:
        po_id (int): Purchase order identifier to approve.
    """

    po_id: int


@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
def root(request: Request):
    """
    Serves a small HTML page with a link to the interactive API docs.

    Args:
        request (Request): FastAPI request object, used to compute base URL.

    Returns:
        str: HTML string containing a welcome message and docs link.
    """
    base_url = str(request.base_url).rstrip("/")
    docs_url = f"{base_url}/docs"
    return f"""
    <!DOCTYPE html>
    <html>
        <head><title>Welcome</title></head>
        <body>
            <h2>Welcome to the Inventory Management MySQL FastAPI Service!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """


@app.get(
    "/dashboard/inventory/overview",
    summary="To provide the high level metrics of inventory overview",
    description="Returns the JSON which has the data total_skus, low_stock_items, overstock_items, critical_items ",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_inventory_overview(engine: Engine = Depends(get_engine)):
    """
    Computes and returns high-level inventory metrics for dashboard use.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        Dict[str, Dict[str, int]]: A dictionary with a `metrics` object containing:
            - total_skus
            - low_stock_items
            - overstock_items
            - critical_items
        Returns zeros when the DataFrame is empty or invalid.
    """
    inventory_df = await inventory_overview(engine)

    # Validate type and emptiness before using DataFrame-specific attributes.
    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

        return {
            "metrics": {
                "total_skus": 0,
                "low_stock_items": 0,
                "overstock_items": 0,
                "critical_items": 0,
            }
        }

    # Validate type before using .empty
    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        return {
            "metrics": {
                "total_skus": 0,
                "low_stock_items": 0,
                "overstock_items": 0,
                "critical_items": 0,
            }
        }

    # Calculate high-level metrics
    metrics = {
        "total_skus": int(inventory_df["sku"].nunique()),
        "low_stock_items": int((inventory_df["Status"] == "Low Stock").sum()),
        "overstock_items": int((inventory_df["Status"] == "Over Stock").sum()),
        "critical_items": int((inventory_df["Status"] == "Critical Stock").sum()),
    }

    # Return the data in a JSON format for the Angular frontend
    return {"metrics": metrics}


@app.get(
    "/dashboard/inventory/overview/low_stock",
    summary="To provide the data for low stock",
    description="Returns the JSON which has the data for low_stock_items",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_low_stock(engine: Engine = Depends(get_engine)):
    """
    Returns detailed records for SKUs classified as 'Low Stock'.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        List[Dict[str, Any]]: Records including product and inventory fields for low stock items.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    display_cols = [
        "product_name",
        "image_data",
        "sku",
        "category",
        "store_id",
        "location",
        "on_hand",
        "in_transit",
        "safety_stock",
    ]

    low_stock = inventory_df[inventory_df["Status"] == "Low Stock"][display_cols]
    return low_stock.to_dict(orient="records")


@app.get(
    "/dashboard/inventory/overview/over_stock",
    summary="To provide the data for over stock",
    description="Returns the JSON which has the data for Over Stock items",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_over_stock(engine: Engine = Depends(get_engine)):
    """
    Returns detailed records for SKUs classified as 'Over Stock'.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        List[Dict[str, Any]]: Records including product and inventory fields for over stock items.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    display_cols = [
        "product_name",
        "image_data",
        "sku",
        "category",
        "store_id",
        "location",
        "on_hand",
        "in_transit",
        "safety_stock",
    ]
    over_stock = inventory_df[inventory_df["Status"] == "Over Stock"][display_cols]
    return over_stock.to_dict(orient="records")


@app.get(
    "/dashboard/inventory/overview/critical_stock",
    summary="To provide the data for critical stock",
    description="Returns the JSON which has the data for Critical Stock items",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_critical_stock(engine: Engine = Depends(get_engine)):
    """
    Returns detailed records for SKUs classified as 'Critical Stock'.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        List[Dict[str, Any]]: Records including product and inventory fields for critical stock items.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    display_cols = [
        "product_name",
        "image_data",
        "sku",
        "category",
        "store_id",
        "location",
        "on_hand",
        "in_transit",
        "safety_stock",
    ]
    critical_stock = inventory_df[inventory_df["Status"] == "Critical Stock"][
        display_cols
    ]
    return critical_stock.to_dict(orient="records")


@app.get(
    "/dashboard/inventory/status_distribution",
    description="Provides data for inventory status distribution",
    summary="Provides data to create the donut chart for on the status distribution",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_inventory_status_dist(engine: Engine = Depends(get_engine)):
    """
    Computes the percentage distribution of inventory statuses for charting.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        Dict[str, int]: Map of status label → percentage (integer).
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    status_percentage = (
        inventory_df["Status"].value_counts(normalize=True) * 100
    ).astype(int)
    return status_percentage.to_dict()


@app.get(
    "/dashboard/inventory/by_location",
    description="Provides data for inventory by location",
    summary="Provides data to create the bar chart for on the status distribution based on location",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_inventory_by_loc(engine: Engine = Depends(get_engine)):
    """
    Aggregates inventory status counts grouped by location for charting.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        Dict[str, List[Dict[str, Any]]]: For each location, a list of {Status, Count} dicts.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    df_by_loc = (
        inventory_df.groupby(["location", "Status"]).size().reset_index(name="Count")
    )

    # Group by location and convert to desired format
    inv_by_loc = (
        df_by_loc.groupby("location")
        .apply(lambda x: x[["Status", "Count"]].to_dict(orient="records"))
        .to_dict()
    )
    return inv_by_loc


@app.get(
    "/dashboard/inventory/all_sku_inventory",
    description="Provides data for all sku inventory details",
    summary="Provides data on all sku inventory to show the data entries in the tabular format",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_po_recomm(engine: Engine = Depends(get_engine)):
    """
    Returns the full inventory overview records for display in a tabular UI.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        List[Dict[str, Any]]: Records for all SKUs with product and inventory fields.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    return inventory_df.to_dict(orient="records")


@app.post(
    "/dashboard/inventory/po_recommendation/add_product",
    description="To add products for PO Recommendation",
    summary="Adds data on PO recommendation for the post request sent by the add product button",
    responses={
        200: {"description": "Recommendation generated successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def add_product_data(request: ProductStock, engine: Engine = Depends(get_engine)):
    """
    Adds a product and upserts stock levels based on the posted payload.

    Args:
        request (ProductStock): Product and stock details to be inserted/updated.
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        str | Dict[str, str]: Success message or error payload.

    Raises:
        HTTPException: 400 for validation/duplicate errors; 500 for unexpected failures.
    """

    try:
        result = await add_product(
            engine,
            sku=request.sku,
            name=request.name,
            category=request.category,
            store_id=request.store_id,
            on_hand=request.on_hand,
            safety_stock=request.safety_stock,
            reorder_point=request.reorder_point,
            in_transit=request.in_transit,
            location=request.location,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        else:
            return result
    except HTTPException:
        logger.error("HTTPException occurred !!")
        raise
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.put(
    "/dashboard/inventory/po_recommendation/edit_product",
    description="To add products for PO Recommendation",
    summary="Adds data on PO recommendation for the post request sent by the add product button",
)
@log_execution(is_api=True)
async def edit_product_data(
    request: ProductStock, engine: Engine = Depends(get_engine)
):
    """
    Edits product stock attributes for a given SKU and store.

    Args:
        request (ProductStock): Product and stock details to be updated.
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        str: Status text indicating the outcome of the update.
    """
    status = await edit_product(
        engine,
        sku=request.sku,
        name=request.name,
        category=request.category,
        store_id=request.store_id,
        on_hand=request.on_hand,
        safety_stock=request.safety_stock,
        reorder_point=request.reorder_point,
        in_transit=request.in_transit,
        location=request.location,
    )
    return status


@app.post(
    "/dashboard/replrecommendation/create_recommendations",
    description="To get the recommendation for replenishment",
    summary="Generates recommendations based on SKU and store_id",
    responses={
        200: {"description": "Recommendation generated successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def retrive_recommendation(
    request: ReplenishmentRecommendation, engine: Engine = Depends(get_engine)
):
    """
    Generates a replenishment recommendation and formats the response for UI.

    Args:
        request (ReplenishmentRecommendation): SKU, store, horizon for forecasting.
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        Dict[str, Any]: Structured recommendation fields for display.

    Raises:
        HTTPException: 400 if no viable replenishment; 500 on unexpected errors.
    """
    try:
        result = await recommend_replenishment(
            broadcast_status,
            engine,
            request.store_id,
            request.sku,
            request.horizon_days,
        )

        # Error routing: differentiate between 'no_replenishment' and other failures.
        if "error" in result:
            if result["error"].get("status") == "no_replenishment":
                raise HTTPException(status_code=400, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result["error"])

        # Safely format the CI pair for display.
        forecast_ci = result.get("forecast_ci", (0, 0))
        ci_values = (
            forecast_ci
            if isinstance(forecast_ci, tuple) and len(forecast_ci) == 2
            else (0, 0)
        )

        return {
            "Store ID": result.get("store_id"),
            "SKU": result.get("sku"),
            "Horizon (Days)": result.get("horizon_days"),
            "Forecast Mean": round(result.get("forecast_mean", 0), 2),
            "Forecast CI": f"[{round(ci_values[0], 2)}, {round(ci_values[1], 2)}]",
            "Method": result.get("method"),
            "Net Position": result.get("net_position"),
            "Safety Stock": result.get("safety_stock"),
            "Recommended Qty": result.get("recommended_qty"),
            "Supplier": result.get("supplier_choice", {}).get("supplier"),
            "Unit Cost": result.get("supplier_choice", {}).get("unit_cost"),
            "Status": result.get("status"),
            "PO ID": result.get("po_id"),
        }
    except HTTPException:
        # Preserve the intended HTTP status (e.g., 400) instead of converting to 500
        logger.error("HTTPException occurred !!")
        raise
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post(
    "/dashboard/replrecommendation/editpo",
    description="To edit the recommendation for replenishment",
    summary="Editable fields: Recommended quantity and supplier",
    responses={
        200: {"description": "Purchase order updated successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def edit_purchase_order(
    request: EditPORecommendation, engine: Engine = Depends(get_engine)
):
    """
    Modifies a purchase order’s supplier and/or line quantity, and recalculates totals.

    Args:
        request (EditPORecommendation): PO id, target SKU, new supplier id, new quantity.
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        Dict[str, Any]: Success payload or error dictionary.

    Raises:
        HTTPException: 400 for invalid inputs; 500 for unexpected failures.
    """
    try:
        result = await edit_purchase_order_recommedation(
            engine,
            request.po_id,
            request.sku,
            request.new_supplier_id,
            request.new_quantity,
        )
        if "error" in result:
            logger.error("HTTPException occurred !!")
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post(
    "/dashboard/replrecommendation/approvepo",
    description="To approve the recommendation for replenishment",
    summary="Approves purchase orders and changes status from draft to approved",
    responses={
        200: {"description": "Purchase order approved successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def approve_purchase_order(
    request: ApprovePORecommendation, engine: Engine = Depends(get_engine)
):
    """
    Approves a purchase order (status set to 'approved').

    Args:
        request (ApprovePORecommendation): PO identifier to approve.
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        Dict[str, Any]: Success payload or error dictionary.

    Raises:
        HTTPException: 400 for invalid inputs; 500 for unexpected failures.
    """
    try:
        result = await approve_po_recommendation(engine, request.po_id)
        if "error" in result:
            logger.error("HTTPException occurred !!")
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get(
    "/dashboard/replrecommendation/recent_po",
    description="Provides data for recent po",
    summary="Provides data on recent PO to show the data entries in the tabular format",
)
@log_execution(is_api=True)
async def get_recent_po(engine: Engine = Depends(get_engine)):
    """
    Returns the 50 most recently created purchase orders for display.

    Args:
        engine (Engine): SQLAlchemy engine injected via dependency.

    Returns:
        List[Dict[str, Any]]: Recent PO records serialized to dictionaries.
    """
    df = await recent_purchase_order(engine)
    return df.to_dict(orient="records")


if __name__ == "__main__":
    """
    Application entry point: runs the FastAPI app via Uvicorn.

    Notes:
        - Host `0.0.0.0` exposes the service externally (container/VM).
        - Port `8080` chosen for typical Cloud Run/containers; adjust if needed.
    """
    uvicorn.run(app, host="0.0.0.0", port=8080)
