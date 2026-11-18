"""跨文件符号检查器自身的测试。

用一个「调用方有、定义方没有」的假项目，验证检查器能报出来
—— 这正是 GatewayRepo.get_enabled_routes_with_models 那个事故的形态。
"""
import textwrap

import pytest

from app.tools import check_symbols as cs


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


@pytest.fixture
def fake_app(tmp_path, monkeypatch):
    """搭一个最小的 app/repositories + app/services 结构。"""
    repo_dir = tmp_path / "repositories"
    service_dir = tmp_path / "services"

    _write(
        repo_dir / "gateway_repo.py",
        """
        class GatewayRepo:
            def __init__(self, db):
                self.db = db

            async def create_route(self, data):
                return data
        """,
    )
    _write(repo_dir / "__init__.py", "")

    monkeypatch.setattr(cs, "REPO_DIR", str(repo_dir))
    monkeypatch.setattr(cs, "SERVICE_DIR", str(service_dir))
    return tmp_path, repo_dir, service_dir


def test_collects_repo_methods(fake_app):
    _, repo_dir, _ = fake_app
    classes = cs.collect_repo_classes()
    assert "GatewayRepo" in classes
    assert "create_route" in classes["GatewayRepo"]
    assert "get_enabled_routes_with_models" not in classes["GatewayRepo"]


def test_detects_missing_method(fake_app):
    _, _, service_dir = fake_app
    _write(
        service_dir / "gateway_service.py",
        """
        from app.repositories.gateway_repo import GatewayRepo


        class GatewayService:
            def __init__(self, db):
                self.repo = GatewayRepo(db)

            async def route_model_for(self, path, name):
                routes = await self.repo.get_enabled_routes_with_models()
                return routes
        """,
    )

    classes = cs.collect_repo_classes()
    problems = cs.analyze_service(str(service_dir / "gateway_service.py"), classes)

    assert len(problems) == 1
    assert "get_enabled_routes_with_models" in problems[0]
    assert "GatewayRepo" in problems[0]


def test_no_false_positive_when_method_exists(fake_app):
    _, _, service_dir = fake_app
    _write(
        service_dir / "gateway_service.py",
        """
        from app.repositories.gateway_repo import GatewayRepo


        class GatewayService:
            def __init__(self, db):
                self.repo = GatewayRepo(db)

            async def do(self, data):
                return await self.repo.create_route(data)
        """,
    )

    classes = cs.collect_repo_classes()
    assert cs.analyze_service(str(service_dir / "gateway_service.py"), classes) == []


def test_attribute_access_not_treated_as_method_call(fake_app):
    """self.repo.db.refresh(...) 里的 db 是属性，不该被当成方法校验。"""
    _, _, service_dir = fake_app
    _write(
        service_dir / "gateway_service.py",
        """
        from app.repositories.gateway_repo import GatewayRepo


        class GatewayService:
            def __init__(self, db):
                self.repo = GatewayRepo(db)

            async def do(self, route):
                await self.repo.db.refresh(route, ['targets'])
        """,
    )

    classes = cs.collect_repo_classes()
    assert cs.analyze_service(str(service_dir / "gateway_service.py"), classes) == []


def test_service_without_repo_attr_is_skipped(fake_app):
    """没有 self.XxxRepo(...) 赋值时，不做任何校验（避免误报）。"""
    _, _, service_dir = fake_app
    _write(
        service_dir / "plain_service.py",
        """
        class PlainService:
            def __init__(self, db):
                self.db = db

            async def do(self):
                return self.db.execute('x')
        """,
    )

    classes = cs.collect_repo_classes()
    assert cs.analyze_service(str(service_dir / "plain_service.py"), classes) == []


def test_syntax_error_is_reported(fake_app):
    _, _, service_dir = fake_app
    bad = service_dir / "broken_service.py"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("class X(:\n", encoding="utf-8")

    classes = cs.collect_repo_classes()
    problems = cs.analyze_service(str(bad), classes)
    assert problems and "语法错误" in problems[0]


def test_real_project_is_consistent():
    """真实项目本身必须通过（回归保护）。"""
    classes = cs.collect_repo_classes()
    assert classes, "没有扫到任何 Repo 类"

    import os

    problems = []
    for fname in sorted(os.listdir(cs.SERVICE_DIR)):
        if not fname.endswith(".py") or fname == "__init__.py":
            continue
        problems.extend(
            cs.analyze_service(os.path.join(cs.SERVICE_DIR, fname), classes)
        )
    assert problems == [], f"真实项目存在符号缺失: {problems}"
