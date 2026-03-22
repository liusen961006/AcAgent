# Skills 使用指南

AcAgent 支持两种类型的 skills：

## 1. 工具型 Skills（Tool-based）

定义新工具，需要实现对应的处理函数。

### Python 格式 (`skills/*.py`)

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "工具描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数1"}
            },
            "required": ["param1"]
        }
    }
}]
```

在 `main.py` 中实现 `run_my_tool` 函数即可自动绑定。

### Markdown 格式 (`skills/*.md`)

使用 ```json 代码块定义 TOOLS：

````markdown
```json
{
  "TOOLS": [...]
}
```
````

## 2. 提示词型 Skills（Prompt-based）

纯自然语言描述的专家指南，不定义新工具。agent会将其作为 system prompt 的一部分，模型自主理解并执行。

### 格式 (`skills/*.md`)

```markdown
---
name: skill名称
description: 简短描述
---

# 详细指南

当用户请求X时：
1. 使用已有工具执行步骤A
2. 使用已有工具执行步骤B
...

## 检查清单
- [ ] 项目1
- [ ] 项目2
```

### 示例

已内置 `code_review.md`（从 learn-claude-code 项目复制），展示完整的代码审查流程。

## 3. 自动检测规则

- 如果 `.md` 文件包含 ````json``` 代码块且有 `TOOLS` 定义 → 工具型
- 如果 `.md` 文件只有自然语言（或 frontmatter + 正文）→ 提示词型
- 两种模式可以共存

## 4. 当前已加载

- **工具型**：file_utils.py (read, write), text_search.py (grep), web_request.md (http_get - 未实现处理器)
- **提示词型**：code_review.md

## 5. 使用方法

1. 在 `skills/` 目录创建 `.py` 或 `.md` 文件
2. 重启 agent，自动加载
3. 对于工具型 skill，确保在 `main.py` 中有对应的 `run_xxx` 函数
