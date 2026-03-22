import os
import json
import subprocess
import sys
import re
from pathlib import Path
from dotenv import load_dotenv
import dashscope
import importlib.util

load_dotenv(override=True)

# 阿里云配置
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    raise ValueError("DASHSCOPE_API_KEY environment variable not set")
dashscope.api_key = DASHSCOPE_API_KEY  # 全局设置

MODEL = os.getenv("MODEL_ID", "qwen-plus")  # 默认使用 qwen-plus，可按需修改

AGENT_NAME = os.getenv("AGENT_NAME", "AcAgent")  # 默认使用 AcAgent，可按需修改

LOG_LEVEL = os.getenv("LOG_LEVEL")

SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."

# 工具定义（阿里云/OpenAI 格式）
BASE_TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"}
            },
            "required": ["command"]
        }
    }
}]

def safe_path(p: str) -> Path:
    path = (Path.cwd() / p).resolve()
    if not path.is_relative_to(Path.cwd()):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_read(path: str, limit: int = None) -> str:
    text = safe_path(path).read_text()
    lines = text.splitlines()
    if limit and len(lines) > limit:
        lines = lines[:limit]
    return "\n".join(lines)[:50000]

def run_write(path: str, content: str):
    safe_path(path).write_text(content)

def run_bash(command: str) -> str:
    # 禁止命令
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=os.getcwd(),
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

def run_grep(pattern: str, path: str = ".", include: str = None) -> str:
    """在文件中搜索模式"""
    import subprocess
    cmd = f"grep -r '{pattern}' {path}"
    if include:
        cmd += f" --include='{include}'"
    try:
        r = subprocess.run(cmd, shell=True, cwd=os.getcwd(),
                          capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no matches)"
    except subprocess.TimeoutExpired:
        return "Error: grep timeout (30s)"

# 基础工具处理器
TOOL_HANDLERS = {
    "bash": run_bash,
    "read": run_read,
    "write": run_write,
    "grep": run_grep,
}

# 动态加载skills
def load_skills():
    """加载skills目录下的所有skill模块，返回合并的TOOLS列表，并自动注册处理器"""
    skills_dir = Path(__file__).parent / "skills"
    all_tools = BASE_TOOLS.copy()

    if not skills_dir.exists():
        return all_tools

    # 支持 .py 和 .md 文件
    patterns = ["*.py", "*.md"]
    
    for pattern in patterns:
        for file_path in skills_dir.glob(pattern):
            if file_path.name.startswith("_") or file_path.name == "__init__.py":
                continue

            module_name = file_path.stem
            tools = []

            if file_path.suffix == ".py":
                # Python模块
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, "TOOLS"):
                        tools = module.TOOLS
            elif file_path.suffix == ".md":
                # Markdown文件 - 解析JSON代码块
                tools = parse_markdown_skills(file_path)

            if tools:
                all_tools.extend(tools)
                
                # 自动注册：查找 main.py 中的 run_<tool_name> 函数
                for tool in tools:
                    tool_name = tool["function"]["name"]
                    handler_name = f"run_{tool_name}"
                    if hasattr(sys.modules[__name__], handler_name):
                        handler = getattr(sys.modules[__name__], handler_name)
                        TOOL_HANDLERS[tool_name] = handler
    
    return all_tools

def parse_markdown_skills(file_path: Path) -> list:
    """从markdown文件中解析TOOLS定义，查找JSON代码块"""
    try:
        content = file_path.read_text()
        # 查找 ```json ... ``` 代码块
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block)
                if "TOOLS" in data and isinstance(data["TOOLS"], list):
                    return data["TOOLS"]
            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"Warning: Failed to parse {file_path}: {e}")
    return []

TOOLS = load_skills()

def execute_tool(tool_name: str, arguments: dict) -> str:
    """执行工具调用"""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return f"Error: Unknown tool '{tool_name}'"
    try:
        return handler(**arguments)
    except Exception as e:
        return f"Error: {str(e)}"

def agent_loop(messages: list):
    """
    messages: list of dict in OpenAI format
        - role: user/assistant/tool
        - content: str (for user/assistant/tool)
        - tool_calls: list (for assistant when calling tools)
        - tool_call_id: str (for tool response)
    """
    step = 0
    while True:
        print(f"[STEP] {step}")
        # 在每次调用前临时插入系统消息（不修改原始 messages）
        temp_messages = [{"role": "system", "content": SYSTEM}] + messages
        
        response = dashscope.Generation.call(
            model=MODEL,
            messages=temp_messages,
            tools=TOOLS,
            result_format='message'  # 必须为 'message' 以获取结构化响应
        )

        if response.status_code != 200:
            print(f"API call failed: {response.code} - {response.message}")
            break

        assistant_msg = response.output.choices[0].message
        # 将 assistant 消息添加到历史
        messages.append(assistant_msg)

        # 检查是否有工具调用
        if assistant_msg.get("tool_calls"):
            # 处理工具调用
            tool_results = []
            for tool_call in assistant_msg["tool_calls"]:
                func = tool_call["function"]
                tool_name = func["name"]
                args = json.loads(func["arguments"])
                print(f"\033[33m$ executing {tool_name}\033[0m")
                output = execute_tool(tool_name, args)
                print(output[:200])
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": output
                })
            messages.extend(tool_results)
            # 继续循环，让模型基于工具结果生成下一步
        else:
            # 没有工具调用，对话结束
            break

if __name__ == "__main__":
    history = []
    print(f"TOOL_HANDLERS: {TOOL_HANDLERS}")
    while True:
        try:
            query = input(f"\033[36m{AGENT_NAME} >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        # 打印最后一条 assistant 消息的文本内容（最终回复）
        if history and history[-1]["role"] == "assistant":
            print(history[-1].get("content", ""))
        print()