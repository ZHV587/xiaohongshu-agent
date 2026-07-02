import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_has_no_interactive_cli_entrypoint():
    assert not (ROOT / "cli.py").exists()


def test_packaging_does_not_expose_cli_module():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"cli"' not in pyproject


def test_backend_has_no_cli_backend_factory():
    backends = (ROOT / "backends.py").read_text(encoding="utf-8")
    assert "build_cli_backend" not in backends
    assert "CLI" not in backends


def test_web_bridge_uses_web_bridge_runner_name():
    internal_client = (ROOT / "web" / "src" / "lib" / "server" / "internal-client.ts").read_text(
        encoding="utf-8"
    )
    assert "web_bridge_runner.py" in internal_client
    assert "cli_runner" not in internal_client
    assert (ROOT / "tools" / "web_bridge_runner.py").exists()
    assert not (ROOT / "tools" / "cli_runner.py").exists()


def _web_bridge_actions() -> tuple[set[str], set[str]]:
    runner = ROOT / "tools" / "web_bridge_runner.py"
    module = ast.parse(runner.read_text(encoding="utf-8"))
    action_choices: set[str] = set()
    dispatch_actions: set[str] = set()

    for node in ast.walk(module):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr != "add_argument" or not node.args:
                continue
            if not isinstance(node.args[0], ast.Constant) or node.args[0].value != "--action":
                continue
            choices = next((keyword.value for keyword in node.keywords if keyword.arg == "choices"), None)
            if isinstance(choices, (ast.List, ast.Tuple)):
                action_choices = {
                    value.value
                    for value in choices.elts
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                }
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            if not isinstance(node.left, ast.Attribute) or node.left.attr != "action":
                continue
            if len(node.comparators) != 1 or not isinstance(node.comparators[0], ast.Constant):
                continue
            value = node.comparators[0].value
            if isinstance(value, str):
                dispatch_actions.add(value)

    return action_choices, dispatch_actions


def test_web_bridge_runner_excludes_business_write_actions():
    action_choices, dispatch_actions = _web_bridge_actions()

    assert {"sync", "notify"}.isdisjoint(action_choices)
    assert {"sync", "notify"}.isdisjoint(dispatch_actions)


def test_internal_client_excludes_business_write_paths():
    internal_client = (ROOT / "web" / "src" / "lib" / "server" / "internal-client.ts").read_text(
        encoding="utf-8"
    )
    mapped_paths = set(re.findall(r'pathName === "([^"]+)"', internal_client))

    assert {"/_internal/sync", "/_internal/notify"}.isdisjoint(mapped_paths)


def test_web_api_business_write_routes_are_removed():
    assert not (ROOT / "web" / "src" / "app" / "api" / "feishu" / "sync" / "route.ts").exists()
    assert not (ROOT / "web" / "src" / "app" / "api" / "feishu" / "notify" / "route.ts").exists()


def test_thread_ui_submits_feishu_write_intent_to_agent():
    # 思考链重构后,飞书写意图的提交逻辑从已删的 thread/index.tsx 迁到
    # ThreadStateProvider.tsx(handleSyncToFeishu 经 agent 工具 sync_copy_to_feishu 提交,
    # 而非前端直 fetch 飞书写 API)。
    provider = (
        ROOT / "web" / "src" / "components" / "thread" / "ThreadStateProvider.tsx"
    ).read_text(encoding="utf-8")

    assert 'fetch("/api/feishu/sync"' not in provider
    assert 'fetch("/api/feishu/notify"' not in provider
    assert "sync_copy_to_feishu" in provider

