"""在 perf-worker 内运行 EvalScope 压测的独立入口。

由 `EvalScopeEngine` 以子进程方式拉起：
    python -m app.tasks.perf_entry <args_json> <out_json>

为什么用子进程而不是同进程调用：
  1. **可真正中止** —— 父进程 `terminate()` 即可停下，EvalScope 本身没有取消接口
  2. **崩溃隔离** —— evalscope 内部异常/段错误不会带崩 Celery worker
  3. **输出格式可控** —— 由本脚本把结果规范成 JSON，父进程无需了解 evalscope 内部文件布局

结果走 out_json 文件而不是 stdout：避免与 EvalScope 的大量日志混在一起。
放在 app/ 包内是为了被 `COPY app/ ./app/` 打进镜像（scripts/ 不会进镜像）。
"""
import json
import sys
import traceback

# 结果文件的格式版本，父进程据此判断兼容性
SCHEMA_VERSION = 1


def _jsonable(obj):
    """把 pydantic 模型 / 字典 / 列表递归转成可 JSON 序列化的结构。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            # by_alias=True → key 用展示名（'Avg TTFT (ms)'），与落盘 JSON 一致
            return _jsonable(obj.model_dump(by_alias=True))
        except TypeError:
            return _jsonable(obj.model_dump())

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]

    # numpy 标量等
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:  # noqa: BLE001
            pass

    return str(obj)


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: perf_evalscope_entry.py <args_json> <out_json>", file=sys.stderr)
        return 2

    args_path, out_path = sys.argv[1], sys.argv[2]

    def _dump(payload: dict) -> None:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    try:
        with open(args_path, encoding="utf-8") as f:
            kwargs = json.load(f)
    except Exception as e:  # noqa: BLE001
        _dump({"schema_version": SCHEMA_VERSION, "ok": False, "error": f"读取参数失败: {e}"})
        return 1

    try:
        from evalscope.perf.arguments import Arguments
        from evalscope.perf.main import run_perf_benchmark
    except ImportError as e:
        _dump(
            {
                "schema_version": SCHEMA_VERSION,
                "ok": False,
                "error": f"导入 evalscope 失败: {e}",
            }
        )
        return 1

    try:
        args = Arguments(**kwargs)
        results = run_perf_benchmark(args)
        _dump(
            {
                "schema_version": SCHEMA_VERSION,
                "ok": True,
                "outputs_dir": kwargs.get("outputs_dir"),
                "results": _jsonable(results),
            }
        )
        return 0
    except BaseException as e:  # noqa: BLE001 - 含 KeyboardInterrupt，全部落文件
        _dump(
            {
                "schema_version": SCHEMA_VERSION,
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-4000:],
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
