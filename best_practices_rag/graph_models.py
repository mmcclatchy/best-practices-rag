from typing import Any

from pydantic import BaseModel


class EntityNode(BaseModel):
    label: str
    name: str
    properties: dict[str, Any] = {}


class Relation(BaseModel):
    label: str
    source_id: str
    target_id: str
