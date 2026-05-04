import json
import re
from pathlib import Path
from typing import Dict, Any, List

from .codeburn_daemon import CodeBurnMonitor


class AutoOptimizer:
    def __init__(self):
        self.monitor = CodeBurnMonitor()
        self._applied = []

    def get_suggestions(self) -> list:
        return self.monitor.optimize()

    def apply(self, dry_run: bool = False) -> List[Dict[str, Any]]:
        suggestions = self.get_suggestions()
        results = []
        for s in suggestions:
            stype = s.get("type", "")
            if stype == "reread_file":
                r = self._handle_reread(s, dry_run)
            elif stype == "unused_tool":
                r = self._handle_unused_tool(s, dry_run)
            elif stype == "bash_output":
                r = self._handle_bash_output(s, dry_run)
            else:
                r = {"type": stype, "action": "skipped", "reason": "unknown-type"}
            results.append(r)
            self._applied.append(r)
        return results

    def _handle_reread(self, suggestion: dict, dry: bool) -> dict:
        filepath = suggestion.get("file", "")
        if not filepath:
            return {"type": "reread_file", "action": "skipped", "reason": "no-file"}
        if not dry:
            cfg_path = Path.home() / ".stealth" / "config.yaml"
            if cfg_path.exists() and filepath not in self._get_caveman_cache():
                self._add_to_caveman_cache(filepath)
        return {"type": "reread_file", "file": filepath, "action": "cached" if not dry else "dry-run"}

    def _handle_unused_tool(self, suggestion: dict, dry: bool) -> dict:
        tool_name = suggestion.get("tool_name", "")
        if not tool_name:
            return {"type": "unused_tool", "action": "skipped", "reason": "no-tool-name"}
        return {"type": "unused_tool", "tool": tool_name, "action": "reported"}

    def _handle_bash_output(self, suggestion: dict, dry: bool) -> dict:
        return {"type": "bash_output", "action": "reported-see-config"}

    def _get_caveman_cache(self) -> list:
        cfg_path = Path.home() / ".stealth" / "config.yaml"
        if not cfg_path.exists():
            return []
        with open(cfg_path) as f:
            cfg = json.load(f)
        return cfg.get("caveman", {}).get("cached_files", [])

    def _add_to_caveman_cache(self, filepath: str):
        cfg_path = Path.home() / ".stealth" / "config.yaml"
        if not cfg_path.exists():
            return
        with open(cfg_path) as f:
            cfg = json.load(f)
        cached = cfg.setdefault("caveman", {}).setdefault("cached_files", [])
        if filepath not in cached:
            cached.append(filepath)
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)

    def report(self) -> dict:
        return {
            "total_applied": len(self._applied),
            "actions": self._applied,
        }


auto_optimizer = AutoOptimizer()
