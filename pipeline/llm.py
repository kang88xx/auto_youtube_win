"""헤드리스 LLM 호출 공통부: claude -p (구독) 와 codex exec (구독). 둘 다 JSON 스키마로 출력을 강제한다.

claude_json(prompt, schema, tools=[...]) → (data, env)   env: claude -p 의 결과 봉투 (usage, total_cost_usd, ...)
codex_json(prompt, schema)               → (data, meta)  meta: {"engine": "codex", "model": ..., "duration_ms": ...}

- claude: MCP 서버·설정(CLAUDE.md, 훅)을 끈다. 안 끄면 Figma·Gmail 등 도구 스키마가 호출마다 9만 토큰씩 붙는다.
- codex:  사용자 config(oh-my-codex 지시문)를 무시하고 read-only 샌드박스, 세션 저장 없이 돌린다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

CLAUDE_SYSTEM = "You write and edit Korean short-form news video scripts. Output only what is asked."
CODEX_MODEL = os.environ.get("CODEX_MODEL", "gpt-6-astra")
CODEX_EFFORT = os.environ.get("CODEX_EFFORT", "high")


class LLMError(RuntimeError):
    pass


def extract_json(txt: str) -> dict:
    try:
        return json.loads(txt)
    except Exception:
        pass
    try:
        return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception as e:
        raise LLMError(f"JSON 추출 실패: {e}\n{txt[:1500]}")


def have_codex() -> bool:
    return shutil.which("codex") is not None


def _run(cmd: list[str], *, cwd: Path, stdin: str, timeout: int, name: str) -> subprocess.CompletedProcess:
    """프롬프트는 stdin 으로 넘긴다 (인자 한 개 128KB 제한 회피). 실행 오류는 전부 LLMError 로."""
    try:
        r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=str(cwd), timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LLMError(f"{name}: {timeout}s 시간 초과")
    except OSError as e:
        raise LLMError(f"{name}: 실행 못 함 ({e})")
    if r.returncode != 0:
        raise LLMError(f"{name} 실패 ({r.returncode}):\n{r.stderr[-2000:]}\n{r.stdout[-2000:]}")
    return r


def claude_json(prompt: str, schema: dict, *, cwd: Path, tools: list[str] | None = None,
                max_turns: int = 20, model: str | None = None, system: str = CLAUDE_SYSTEM,
                timeout: int = 1800) -> tuple[dict, dict]:
    cmd = ["claude", "-p", "--output-format", "json",
           "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--max-turns", str(max_turns), "--system-prompt", system,
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", ""]
    if model:
        cmd += ["--model", model]
    # --tools 로 도구 목록 자체를 좁히고(--allowedTools 만으로는 Bash·Edit 가 보여서 턴을 낭비), 같은 것을 사전 허용
    cmd += ["--tools", *tools, "--allowedTools", *tools] if tools else ["--tools", ""]
    r = _run(cmd, cwd=cwd, stdin=prompt, timeout=timeout, name="claude -p")
    try:
        env = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise LLMError(f"claude -p 출력이 JSON 이 아님:\n{r.stdout[-1500:]}")
    if env.get("is_error") or env.get("subtype") not in (None, "success"):
        raise LLMError(f"claude -p 오류 ({env.get('subtype')}): {str(env.get('result', ''))[:800]}")
    data = env.get("structured_output")
    if data is None:
        data = extract_json(env.get("result", ""))
    if not isinstance(data, dict):
        raise LLMError(f"claude -p 결과가 객체가 아님: {str(data)[:300]}")
    return data, env


def codex_json(prompt: str, schema: dict, *, cwd: Path, model: str = CODEX_MODEL,
               effort: str = CODEX_EFFORT, timeout: int = 1800) -> tuple[dict, dict]:
    cwd.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-", dir=str(cwd)) as td:
        sf = Path(td) / "schema.json"
        of = Path(td) / "last.json"
        sf.write_text(json.dumps(schema, ensure_ascii=False))
        cmd = ["codex", "exec", "--ignore-user-config", "-m", model,
               "-c", f'model_reasoning_effort="{effort}"',
               "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", str(cwd),
               "--output-schema", str(sf), "-o", str(of), "-"]
        t0 = time.time()
        r = _run(cmd, cwd=cwd, stdin=prompt, timeout=timeout, name="codex exec")
        if not of.exists():
            raise LLMError(f"codex exec: 결과 파일 없음\n{r.stderr[-1500:]}")
        data = extract_json(of.read_text())
    if not isinstance(data, dict):
        raise LLMError(f"codex 결과가 객체가 아님: {str(data)[:300]}")
    return data, {"engine": "codex", "model": model, "duration_ms": int((time.time() - t0) * 1000)}


def validate_script(data: dict) -> None:
    """script.json 계약 검사 (tts·render 가 기대하는 것). 어기면 LLMError."""
    for k in ("title", "titles", "description", "tags", "sentences"):
        if k not in data:
            raise LLMError(f"script: '{k}' 없음")
    if not isinstance(data["sentences"], list) or not data["sentences"]:
        raise LLMError("script: sentences 비어 있음")
    for i, s in enumerate(data["sentences"], 1):
        if not isinstance(s, dict) or not str(s.get("text", "")).strip():
            raise LLMError(f"script: {i}번째 문장 text 없음")
        if s.get("speaker") not in ("main", "quote"):
            raise LLMError(f"script: {i}번째 문장 speaker={s.get('speaker')!r}")


def cost_of(env: dict) -> float | None:
    """claude 봉투의 API 환산 비용(구독이면 참고값)."""
    return env.get("total_cost_usd")
