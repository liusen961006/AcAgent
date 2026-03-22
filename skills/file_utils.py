"""
文件操作技能：提供文件读写功能
"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read file content with optional line limit",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read (optional)"}
            },
            "required": ["path"]
        }
    }
}, {
    "type": "function",
    "function": {
        "name": "write",
        "description": "Write content to a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["path", "content"]
        }
    }
}]


