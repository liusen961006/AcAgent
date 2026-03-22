"""
文本搜索技能：提供grep搜索功能
"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "grep",
        "description": "Search for patterns in files",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search"},
                "path": {"type": "string", "description": "File or directory path (default: current directory)"},
                "include": {"type": "string", "description": "File pattern to include (e.g., '*.py')"}
            },
            "required": ["pattern"]
        }
    }
}]
