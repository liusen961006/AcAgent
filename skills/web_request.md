# 网络请求技能

提供简单的HTTP请求功能。

```json
{
  "TOOLS": [
    {
      "type": "function",
      "function": {
        "name": "http_get",
        "description": "Perform HTTP GET request",
        "parameters": {
          "type": "object",
          "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "headers": {"type": "object", "description": "Optional headers"}
          },
          "required": ["url"]
        }
      }
    }
  ]
}
```

> 注意：此技能需要main.py中实现 `run_http_get` 函数。
