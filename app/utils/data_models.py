import uuid
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class StandardNode(BaseModel):
    reference_code: Optional[str] = None
    title: str
    content: Optional[str] = ""
    node_type: str = Field(..., pattern="^(process|requirement)$")
    children: List['StandardNode'] = []
    def to_flat_list(self, document_id: str, parent_id: Optional[str] = None, counter: List[int] = None) -> List[Dict]:
        if counter is None:
            counter = [0]
        node_id = str(uuid.uuid4())
        current_order = counter[0]
        counter[0] += 1
        current_node = {
            "id": node_id,
            "document_id": document_id,
            "parent_id": parent_id,
            "node_type": self.node_type,
            "reference_code": self.reference_code,
            "display_order": current_order,
            "title": self.title,
            "content": self.content,
            "metadata": {}
        }
        flat_list = [current_node]
        for child in self.children:
            flat_list.extend(child.to_flat_list(document_id, node_id, counter))
        return flat_list

class TocItem:
    def __init__(self, level: int, title: str, page: int):
        self.level = level
        self.title = title
        self.page = page
        self.page_start = page
        self.page_end = page
        self.content_context: Optional[str] = None # New field for sliced text
        self.children: List['TocItem'] = []
