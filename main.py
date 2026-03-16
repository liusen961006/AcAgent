import os
import json
import subprocess
from dotenv import load_dotenv
import dashscope

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
TOOLS = [{
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
                if tool_call["function"]["name"] == "bash":
                    args = json.loads(tool_call["function"]["arguments"])
                    command = args["command"]
                    print(f"\033[33m$ {command}\033[0m")
                    output = run_bash(command)
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