"""
Skills: 每个skill文件定义一组工具函数
格式: 导出 TOOLS 列表，每个工具包含 name, description, parameters
"""

# 示例：文件读取skill（增强版）
TOOLS = [{
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read file content with optional line limit",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "limit": {"type": "integer", "description": "Max lines to read"}
            },
            "required": ["path"]
        }
    }
}]
