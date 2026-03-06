from __future__ import annotations
from typing import Dict, Any, Tuple, List
from src.utils.broadcast_decorator import status_broadcast


@status_broadcast("Policy Agent is working")
async def policy_check(
    broadcast, query: str
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    citations = [
        {"source": "N/A", "doc_type": "Policy", "snippet": "Policy check simulated"}
    ]
    constraints = {
        "max_single_po": 25000.0,
        "allow_substitution": True,
        "substitution_scope": "same_category",
    }
    return constraints, citations
