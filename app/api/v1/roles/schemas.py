from pydantic import BaseModel
from typing import List


class RoleCreate(BaseModel):
    name: str
    permission_ids: List[int]
    level: int = 80
    is_system: bool = False


class RoleResponse(BaseModel):
    id: int
    name: str
