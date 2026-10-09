# -*- coding: utf-8 -*-
"""按机器的 Validator 规则修复 FRAS 条目并重新提交。

机器规则（来自 fras_s_too_long / fras_a_too_many_items 等 finding）：
  F ≤160 字；R ≤360 字且 ≤8 项；A ≤400 字且 ≤6 项；
  S 按重要性配额：C9-8 ≤600，C7-4 ≤200，C3-1 ≤50（Unicode 字符计）。
"""
import json, subprocess, sys, io, re, os

EXE = r"D:\tools\aoci\bin\aoci.exe"
REPO = r"D:\Workspace\dylan\FeifeiAI"


def mcp_call(method, arguments):
    proc = subprocess.Popen([EXE, "mcp", "--repo", REPO],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)

    def send(p):
        proc.stdin.write(json.dumps(p, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    send({"jsonrpc": "2.0", "id": 0, "method": "initialize",
          "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                     "clientInfo": {"name": "wb-submit", "version": "1"}}})
    json.loads(proc.stdout.readline())
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": method, "arguments": arguments}})
    line = proc.stdout.readline()
    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except Exception:
        proc.kill()
    try:
        d = json.loads(line)
    except Exception:
        return {"raw": line}
    if "result" in d and "content" in d["result"]:
        return {"text": "\n".join(c.get("text", "") for c in d["result"]["content"])}
    return d


def trim_smart(s, limit):
    """截到 limit 个 Unicode 字符，优先在句读处收尾。"""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    for sep in ("；", ";", "，", ",", "。", "."):
        pos = cut.rfind(sep)
        if pos >= limit * 0.55:
            return cut[:pos]
    return cut[: limit - 1] + "…"


def fix_entry(e):
    m = re.match(r"^([^\[\]:]+)\[([^\]]+)\]:\s*(.*)$", e)
    if not m:
        return e
    name, tag, rest = m.group(1), m.group(2), m.group(3)
    # 标签：compact A+B+C+[D]+E，D 位固定 '-'。
    # worker 常写成 "CUT5T"（D 位误填规模字母且漏了 '-'），统一还原。
    letters = [c for c in tag if c.isalpha()]
    digits = [c for c in tag if c.isdigit()]
    # B 位合法取值（code 字典）：A,B,C,D,E,G,H,I,L,M,N,O,P,Q,R,S,U,V,W,Z（注意没有 F）
    VALID_B = set("ABCDEGHILMNOPQRSUVWZ")
    if len(tag) >= 2 and tag[1] not in VALID_B:
        tag = tag[0] + "Z" + tag[2:]
        letters = [c for c in tag if c.isalpha()]
    if len(letters) >= 3 and len(digits) == 1:
        # 官方样例形态 main.go[EG7T]：A+B+C+E 四位，D 位省略。
        # worker 常多写一位（"CUT5T"），这里统一取 头两位+数字+末位字母。
        tag = letters[0] + letters[1] + digits[0] + letters[-1]

    parts = rest.split(" | ")
    seg = {}
    for p in parts:
        mm = re.match(r"^([FRAS]):(.*)$", p)
        if mm:
            seg[mm.group(1)] = mm.group(2)
    if set(seg) != set("FRAS"):
        return e

    importance = int(digits[0]) if digits else 5
    s_limit = 600 if importance >= 8 else (200 if importance >= 4 else 50)

    seg["F"] = seg["F"][:160]
    seg["R"] = ",".join(seg["R"].split(",")[:8])[:360]
    seg["A"] = ",".join(seg["A"].split(",")[:6])[:400]
    seg["S"] = trim_smart(seg["S"], s_limit)

    return f"{name}[{tag}]: F:{seg['F']} | R:{seg['R']} | A:{seg['A']} | S:{seg['S']}"


def main():
    maint = json.load(io.open(sys.argv[1], encoding="utf-8"))
    cands = {c["path"]: c for c in maint.get("candidates", [])}
    code_batch_id = maint.get("code_plan", {}).get("batch_id")

    entries = []
    for f in sys.argv[2:]:
        if not os.path.exists(f):
            print("缺文件:", f)
            continue
        data = json.load(io.open(f, encoding="utf-8"))
        for it in data.get("items", []):
            p = it["path"]
            if "error" in it or "new_entry" not in it:
                continue
            c = cands.get(p)
            if not c:
                continue
            entries.append({
                "path": p,
                "source_sha256": c["source_sha256"],
                "candidate_id": c["candidate_id"],
                "new_entry": fix_entry(it["new_entry"]),
            })

    print(f"提交 {len(entries)} 条 → code_batch_id {code_batch_id[:12]}")
    out = mcp_call("aoci_update_entry", {"code_batch_id": code_batch_id, "entries": entries})
    txt = out.get("text", json.dumps(out, ensure_ascii=False))
    io.open(r"D:\tmp\aoci-research\submit1-result.json", "w", encoding="utf-8").write(txt)
    # 摘要
    try:
        d = json.loads(txt)
        print("status:", d.get("status"), "| applied:", d.get("applied"), "/ attempted:", d.get("attempted"),
              "| remaining:", d.get("remaining"), "| findings:", d.get("finding_count"))
        for f_ in (d.get("findings") or [])[:10]:
            print("  ·", f_.get("path"), "|", f_.get("field"), f_.get("rule_code"), "|", f_.get("actual"), "→", f_.get("expected"))
    except Exception:
        print(txt[:1500])


if __name__ == "__main__":
    main()
