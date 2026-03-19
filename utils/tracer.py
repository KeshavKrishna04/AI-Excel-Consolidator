import time
from typing import List, Dict, Any


class Trace:
    def __init__(self) -> None:
        self.steps: List[Dict[str, Any]] = []

    def add(self, name: str, start_time: float) -> None:
        duration = time.time() - start_time
        self.steps.append({"step": name, "duration": round(duration, 4)})

    def add_duration(self, name: str, duration_seconds: float) -> None:
        """Convenience for when we already know the duration."""
        self.steps.append({"step": name, "duration": round(duration_seconds, 4)})

    def summary(self) -> List[Dict[str, Any]]:
        return list(self.steps)

