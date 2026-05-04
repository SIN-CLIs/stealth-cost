import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

OPCODE_DB = Path.home() / ".local/share/opencode/opencode.db"


class CodeBurnMonitor:
    def __init__(self, db_path: Path = OPCODE_DB):
        self.db_path = db_path
        self.budget_limit = self._load_budget()
        self._cached_stats = {}
        self._cached_yield = {}

    def _load_budget(self) -> float:
        cfg_path = Path.home() / ".stealth" / "config.yaml"
        if cfg_path.exists():
            try:
                import json as j
                with open(cfg_path) as f:
                    cfg = j.load(f)
                return float(cfg.get("codeburn", {}).get("budget_usd", 10.0))
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return 10.0

    def _run(self, cmd: list, timeout: int = 30) -> Dict[str, Any]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode != 0:
                return {"error": r.stderr.strip()}
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except subprocess.TimeoutExpired:
            return {"error": "codeburn-timeout"}
        except FileNotFoundError:
            return {"error": "codeburn-not-installed"}
        except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
            return {"error": str(e)}

    def status(self) -> Dict[str, Any]:
        return self._run([
            "npx", "codeburn", "status",
            "--provider", "opencode",
            "--db-path", str(self.db_path),
            "--format", "json",
        ], timeout=60)

    def yield_report(self, period: str = "week") -> Dict[str, Any]:
        return self._run([
            "npx", "codeburn", "yield",
            "--period", period,
        ], timeout=60)

    def optimize(self, period: str = "30days") -> list:
        r = self._run([
            "npx", "codeburn", "optimize",
            "--provider", "opencode",
            "--period", period,
        ], timeout=60)
        return r.get("suggestions", [])

    def budget_ok(self) -> bool:
        s = self.status()
        cost = s.get("total_cost_usd", 0)
        return cost < self.budget_limit

    def budget_pct(self) -> float:
        s = self.status()
        cost = s.get("total_cost_usd", 0)
        if self.budget_limit <= 0:
            return 0.0
        return min(100.0, round(cost / self.budget_limit * 100, 1))

    def productive_ratio(self) -> float:
        r = self.yield_report()
        return r.get("productive_ratio", 0.5)

    def is_yield_sufficient(self, threshold: float = 0.7) -> bool:
        return self.productive_ratio() >= threshold


monitor = CodeBurnMonitor()
