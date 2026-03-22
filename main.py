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

WORKDIR = Path.cwd()
BASE_SYSTEM = f"You are a coding agent at {WORKDIR}. Use bash to solve tasks. Act, don't explain."

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
    """
    加载skills目录下的所有skill模块和markdown文件
    返回: (TOOLS列表, SKILL_PROMPTS列表)
    """
    skills_dir = Path(__file__).parent / "skills"
    all_tools = BASE_TOOLS.copy()
    skill_prompts = []
    
    if not skills_dir.exists():
        return all_tools, skill_prompts
    
    # 处理 .py 文件（工具型skill）
    for file_path in skills_dir.glob("*.py"):
        if file_path.name.startswith("_") or file_path.name == "__init__.py":
            continue
        
        module_name = file_path.stem
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "TOOLS"):
                all_tools.extend(module.TOOLS)
                
                # 自动注册：查找 main.py 中的 run_<tool_name> 函数
                for tool in module.TOOLS:
                    tool_name = tool["function"]["name"]
                    handler_name = f"run_{tool_name}"
                    if hasattr(sys.modules[__name__], handler_name):
                        handler = getattr(sys.modules[__name__], handler_name)
                        TOOL_HANDLERS[tool_name] = handler
    
    # 处理 .md 文件（prompt型skill）
    for file_path in skills_dir.glob("*.md"):
        if file_path.name.startswith("_"):
            continue
        
        prompt_data = extract_skill_prompt(file_path)
        if prompt_data:
            skill_prompts.append(prompt_data)
    
    return all_tools, skill_prompts

def extract_skill_prompt(file_path: Path) -> dict:
    """从markdown文件中提取skill信息，返回 {'name': ..., 'description': ..., 'content': ...}"""
    try:
        content = file_path.read_text()
        
        # 解析 frontmatter (--- 包裹的YAML部分)
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        name = file_path.stem
        description = ""
        
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            # 简单解析 name 和 description
            for line in frontmatter.split('\n'):
                line = line.strip()
                if line.startswith('name:'):
                    name = line.split(':', 1)[1].strip()
                elif line.startswith('description:'):
                    description = line.split(':', 1)[1].strip()
            
            # 去掉frontmatter，得到body
            body = content[frontmatter_match.end():]
        else:
            body = content
        
        # 检查是否有JSON代码块定义的工具
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', body, re.DOTALL)
        tools = []
        for block in json_blocks:
            try:
                data = json.loads(block)
                if "TOOLS" in data and isinstance(data["TOOLS"], list):
                    tools.extend(data["TOOLS"])
            except json.JSONDecodeError:
                continue
        
        # 如果有JSON工具定义，这是工具型skill，不返回prompt
        if tools:
            return None
        
        # 否则是prompt型skill，返回提取的信息
        return {
            "name": name,
            "description": description,
            "content": body.strip()
        }
    except Exception as e:
        print(f"Warning: Failed to parse skill {file_path}: {e}")
    return None

def get_system_message() -> str:
    """构建包含所有skill prompts的系统消息"""
    system = BASE_SYSTEM
    
    if SKILL_PROMPTS:
        system += "\n\n# Available Skills\n"
        for prompt in SKILL_PROMPTS:
            system += f"\n## {prompt['name']}\n"
            if prompt['description']:
                system += f"{prompt['description']}\n\n"
            system += f"{prompt['content']}\n"
    
    return system

# 加载skills
TOOLS, SKILL_PROMPTS = load_skills()

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
        # 在每次调用前临时插入系统消息（不修改原始 messages），使用动态构建的system
        temp_messages = [{"role": "system", "content": get_system_message()}] + messages
        
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
