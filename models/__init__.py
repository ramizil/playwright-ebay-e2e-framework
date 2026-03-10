"""
Models Package
===============

Data transfer objects (DTOs) and state classes used across the framework.
Follows the same pattern as the Java CES project where DTOs live in
dedicated ``dto`` packages separate from business logic and test code.

Usage::

    from models import ShoppingFlowState, SmokeFlowState
"""

from models.flow_state import ShoppingFlowState, SmokeFlowState

__all__ = [
    "ShoppingFlowState",
    "SmokeFlowState",
]
