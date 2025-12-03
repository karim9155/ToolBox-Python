import uuid
import re
import json

class TreeFlattener:
    def __init__(self, root_node):
        self.root = root_node
        self.flat_nodes = []
        self.global_order = 1

    def run(self):
        # The root node from HierarchyBuilder is a dummy "Document Root".
        # We skip the root node itself and process its children.
        # However, if the root has content (Front Matter), we might want to capture it?
        # For now, assuming we start from the main sections as per the example "1. Client".
        
        for child in self.root.get("children", []):
            self._process_node(child, parent_id=None)
            
        return self.flat_nodes

    def _process_node(self, node, parent_id):
        node_id = str(uuid.uuid4())
        
        title = node.get("title", "")
        reference_code = self._extract_reference_code(title)
        
        # Handle content
        # Content in tree is a list of strings or dicts (tables)
        content_list = node.get("content", [])
        content_str = ""
        if content_list:
            processed_content = []
            for item in content_list:
                if isinstance(item, str):
                    processed_content.append(item)
                else:
                    # It's a table or other object
                    # Serialize to JSON string for now so it fits in the "content" string field
                    processed_content.append(json.dumps(item, ensure_ascii=False))
            content_str = "\n\n".join(processed_content)

        # Determine node_type based on content presence
        # Rule: No content => process, Has content => requirement
        node_type = "requirement" if content_str.strip() else "process"

        flat_node = {
            "id": node_id,
            "parent_id": parent_id,
            "node_type": node_type,
            "reference_code": reference_code,
            "display_order": self.global_order,
            "title": title,
            "content": content_str,
            "metadata": {}
        }
        
        self.flat_nodes.append(flat_node)
        self.global_order += 1
        
        # Process children
        for child in node.get("children", []):
            self._process_node(child, parent_id=node_id)

    def _extract_reference_code(self, title):
        # Matches "1. ", "1.1 ", "25-001 ", "A. "
        # We want to capture the code part.
        match = re.match(r'^([\w\d\.\-]+)', title)
        if match:
            code = match.group(1)
            # Remove trailing dot if it exists (e.g. "1." -> "1")
            if code.endswith('.'):
                code = code[:-1]
            return code
        return None
