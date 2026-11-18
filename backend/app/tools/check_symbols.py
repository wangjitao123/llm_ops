"""跨文件符号完整性检查（CI/部署前自检）。

针对的问题：**只更新了调用方、忘了更新定义方**导致的运行时 `AttributeError`。
典型案例（真实发生过的）：
  * services/gateway_service.py 调 self.repo.get_enabled_routes_with_models()
    但 repositories/gateway_repo.py 里没有这个方法 → 只在运行时才炸，
    import 能过、healthcheck 也正常。

检查逻辑：
  1. 扫描 app/repositories/*.py，收集 `class XxxRepo` → 方法名集合
  2. 扫描 app/services/*.py，从 `__init__` 里 `self.<attr> = XxxRepo(...)` 建立 attr → Repo 类映射
  3. 找出所有 `self.<attr>.<method>(...)` 调用，校验 method 是否在对应 Repo 类里定义
  4. 输出缺失清单，有缺失时退出码 1

用法（容器内）：
    python -m app.tools.check_symbols
本地：
    cd backend && python -m app.tools.check_symbols
"""
from __future__ import annotations

import ast
import os
import sys
from typing import Dict, Set

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPO_DIR = os.path.join(APP_DIR, "repositories")
SERVICE_DIR = os.path.join(APP_DIR, "services")


# ============================================================
# 收集仓库类的方法
# ============================================================

def collect_repo_classes() -> Dict[str, Set[str]]:
    """返回 {RepoClassName: {method, ...}}。"""
    result: Dict[str, Set[str]] = {}
    if not os.path.isdir(REPO_DIR):
        return result

    for fname in sorted(os.listdir(REPO_DIR)):
        if not fname.endswith(".py") or fname == "__init__.py":
            continue
        path = os.path.join(REPO_DIR, fname)
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        except SyntaxError as e:
            print(f"[WARN] 语法错误跳过 {fname}: {e}")
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            methods: Set[str] = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(item.name)
            result[node.name] = methods
    return result


# ============================================================
# 分析服务类：self.<attr> = XxxRepo(...)  +  self.<attr>.<method>()
# ============================================================

def analyze_service(path: str, repo_classes: Dict[str, Set[str]]) -> list[str]:
    """返回该服务文件的缺失符号提示列表。"""
    problems: list[str] = []
    try:
        rel = os.path.relpath(path, APP_DIR)
    except ValueError:
        # Windows 下跨盘符时 relpath 会抛 ValueError，退回绝对路径
        rel = path

    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    except SyntaxError as e:
        return [f"{rel}: 语法错误 {e}"]

    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue

        # attr -> Repo 类名（从 __init__ 的赋值里推导）
        attr_to_repo: Dict[str, str] = {}
        for item in cls.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "__init__":
                continue
            for stmt in ast.walk(item):
                if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
                    continue
                target = stmt.targets[0]
                # self.xxx = Yyy(...)
                if not (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    continue
                call = stmt.value
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if isinstance(func, ast.Name) and func.id in repo_classes:
                    attr_to_repo[target.attr] = func.id

        if not attr_to_repo:
            continue

        # 检查 self.<attr>.<method>() 调用
        for node in ast.walk(cls):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            inner = func.value
            if not (
                isinstance(inner, ast.Attribute)
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "self"
            ):
                continue

            attr = inner.attr
            repo_cls = attr_to_repo.get(attr)
            if repo_cls is None:
                continue

            method = func.attr
            if method not in repo_classes[repo_cls]:
                line = getattr(node, "lineno", "?")
                problems.append(
                    f"{rel}:{line}  {cls.name}.self.{attr}.{method}()  "
                    f"未在 {repo_cls} 中定义"
                )

    return problems


def main() -> int:
    repo_classes = collect_repo_classes()
    if not repo_classes:
        print("[ERROR] 没有找到任何 Repo 类，检查路径是否正确")
        return 2

    print(f"已扫描 {len(repo_classes)} 个 Repo 类：")
    for name in sorted(repo_classes):
        print(f"  - {name}: {len(repo_classes[name])} 个方法")

    problems: list[str] = []
    if os.path.isdir(SERVICE_DIR):
        for fname in sorted(os.listdir(SERVICE_DIR)):
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            problems.extend(
                analyze_service(os.path.join(SERVICE_DIR, fname), repo_classes)
            )

    print()
    if problems:
        print(f"[FAIL] 发现 {len(problems)} 个跨文件符号缺失：")
        for p in problems:
            print("  ", p)
        print()
        print("这些调用在运行时才会抛 AttributeError，import 和 healthcheck 都发现不了。")
        return 1

    print("[OK] 所有 service → repo 方法调用均有对应定义")
    return 0


if __name__ == "__main__":
    sys.exit(main())
