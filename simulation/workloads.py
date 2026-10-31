"""Five HPC/QC workload profiles (Round 2 Upgrade C).

Domain parameters are prototype assumptions informed by the cited sources, not values measured
from a real facility. Singamaneni et al. (2025) is used only for domain parameterization: its
NTRUEncrypt-SIDH primitive is excluded because SIDH has known cryptanalytic breaks and is outside
the NIST FIPS 203/204 scope of this project.
"""
from dataclasses import dataclass

from decision_engine.policy import Conditions


@dataclass(frozen=True)
class WorkloadProfile:
    id: str
    name: str
    description: str
    citation: str
    conditions: Conditions
    num_messages: int
    rekey_interval_messages: int


WORKLOADS = [
    WorkloadProfile(
        "hpc_bulk", "HPC Bulk Transfer",
        "Checkpoint and QaaS state dump: large messages over a fast link.",
        "Rallis et al., 2025, Item 8, p. 2",
        Conditions("MEDIUM", 5.0, 100.0, 100_000, 1_000_000), 100, 50),
    WorkloadProfile(
        "financial", "Financial Analytics",
        "Quantum Monte Carlo pricing with high sensitivity and a 10-year lifetime.",
        "Singamaneni et al., 2025, Sec. III-C, p. 10; Ricci et al., 2024, Sec. VII-B, p. 12",
        Conditions("HIGH", 10.0, 40.0, 50_000, 50_000), 200, 50),
    WorkloadProfile(
        "scientific", "Scientific Research",
        "Molecular VQE parameter synchronization between HPC and QPU.",
        "Rallis et al., 2025, Items 2-4, p. 1",
        Conditions("MEDIUM", 5.0, 50.0, 20_000, 25_000), 150, 75),
    WorkloadProfile(
        "healthcare", "Healthcare Sensitive Data",
        "Genomic and HIPAA-regulated QML data with a 25-year confidentiality lifetime.",
        "Singamaneni et al., 2025, Sec. III-C, p. 10; Cypher.pdf, p. 4",
        Conditions("CRITICAL", 25.0, 200.0, 50_000, 500_000), 50, 20),
    WorkloadProfile(
        "control_loop", "Low-Latency Control Loop",
        "Real-time CPU-QPU feedback: many small messages under a tight budget.",
        "Rallis et al., 2025, Item 9, p. 2",
        Conditions("LOW", 0.1, 8.0, 10_000, 512), 500, 250),
]
WORKLOADS_BY_ID = {w.id: w for w in WORKLOADS}
