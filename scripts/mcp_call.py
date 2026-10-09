# -*- coding: utf-8 -*-
"""最小 MCP stdio 客户端：不用等宿主加载 MCP，直接调用 AOCI 的工具。

用法：
  python mcp_call.py tools                          # 列工具
  python mcp_call.py call aoci_rules '{}'
  python mcp_call.py call aoci_maintain '{}'
  python mcp_call.py call aoci_search '{"query":"退款"}'

要点：MCP 握手必须先 initialize，再发 notifications/initialized，否则 tools/call 会被拒。
"""
import json, subprocess, sys, os

EXE = r"D:\tools\aoci\bin\aoci.exe"
REPO = r"D:\Workspace\dylan\FeifeiAI"
PROTOCOL = "2025-11-25"


def rpc(proc, payload, expect_id=None):
    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def call(method, arguments=None, raw=False):
    proc = subprocess.Popen(
        [EXE, "mcp", "--repo", REPO],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1,
    )
    def send(p):
        proc.stdin.write(json.dumps(p, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    send({"jsonrpc": "2.0", "id": 0, "method": "initialize",
          "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                     "clientInfo": {"name": "wb-mcp-client", "version": "1"}}})
    init = json.loads(proc.stdout.readline())
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    if method == "tools/list":
        send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        line = proc.stdout.readline()
        proc.stdin.close()
        proc.wait(timeout=10)
        return line

    send({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": method, "arguments": arguments or {}}})
    line = proc.stdout.readline()
    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    return line


def main():
    cmd = sys.argv[1]
    if cmd == "tools":
        print(call("tools/list"))
        return
    if cmd == "call":
        name = sys.argv[2]
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        out = call(name, args)
        try:
            d = json.loads(out)
        except Exception:
            print(out)
            return
        if "result" in d and isinstance(d["result"], dict) and "content" in d["result"]:
            for c in d["result"]["content"]:
                print(c.get("text", ""))
        else:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
