"""The four canonical demo scenarios (Cypher.pdf, p. 13)."""
from decision_engine.policy import Conditions

SCENARIOS = {
    "1. Speed priority": Conditions("LOW", 0.1, 10, 10_000, 10_000),
    "2. Maximum security": Conditions("CRITICAL", 25, 200, 100_000, 10_000),
    "3. Balanced workload": Conditions("MEDIUM", 5, 50, 20_000, 10_000),
    "4. Network constrained (after #3)": Conditions("MEDIUM", 5, 20, 300, 10_000),
}
TIMELINE = list(SCENARIOS.keys())
