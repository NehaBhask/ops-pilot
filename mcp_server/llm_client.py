"""
Bridge between a local Ollama model and the ops-copilot MCP server.

Ollama has no native MCP support, so this script does the translation
by hand:
  1. Connect to mcp_server/server.py as an MCP CLIENT (not server)
  2. Ask it for the list of available tools (repo_health, deploy_status, incident_log)
  3. Convert those tool schemas into the function-calling format Ollama expects
  4. Loop: send the conversation + tools to Ollama -> if it wants to call a
     tool, actually call it via MCP -> feed the result back -> repeat until
     Ollama gives a final answer with no more tool calls

Usage:
    python -m mcp_server.llm_client "is octocat/Hello-World healthy?"
"""

import os
import sys
import asyncio
import ollama
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

MODEL = "qwen2.5:7b"

server_transport = StdioTransport(
    command="python",
    args=["mcp_server/server.py"],
    cwd=os.getcwd(),
    env=dict(os.environ),  # explicitly pass through PYTHONPATH, GITHUB_TOKEN, etc.
)


def mcp_tool_to_ollama_format(mcp_tool) -> dict:
    """
    Convert one MCP tool definition into the JSON-schema shape Ollama's
    chat API expects for the `tools` parameter (same shape OpenAI uses).
    """
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description or "",
            "parameters": mcp_tool.inputSchema,
        },
    }


async def run_conversation(user_question: str):
    async with Client(server_transport) as mcp_client:
        # Step 1: discover what tools this MCP server offers
        mcp_tools = await mcp_client.list_tools()
        ollama_tools = [mcp_tool_to_ollama_format(t) for t in mcp_tools]

        print(f"Discovered {len(ollama_tools)} tools: {[t['function']['name'] for t in ollama_tools]}\n")

        messages = [{"role": "user", "content": user_question}]

        # Step 2: the actual agent loop
        while True:
            response = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
            assistant_message = response["message"]
            messages.append(assistant_message)

            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                # No more tools requested -> this is the final answer
                print("=" * 60)
                print("FINAL ANSWER")
                print("=" * 60)
                print(assistant_message["content"])
                return

            # Step 3: Ollama wants to call one or more tools -> actually call them
            for call in tool_calls:
                tool_name = call["function"]["name"]
                tool_args = call["function"]["arguments"]

                print(f"-> Model called tool: {tool_name}({tool_args})")

                result = await mcp_client.call_tool(tool_name, tool_args)
                result_text = result.content[0].text if result.content else "(no output)"

                # Step 4: feed the tool's result back into the conversation
                # so the model can use it to form its final answer
                messages.append(
                    {
                        "role": "tool",
                        "content": result_text,
                    }
                )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python -m mcp_server.llm_client "your question here"')
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    asyncio.run(run_conversation(question))