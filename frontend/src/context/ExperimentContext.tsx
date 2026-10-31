import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type {
  BenchmarkProfileResponse,
  Conditions,
  DecisionResponse,
  HandshakeResponse,
  HealthResponse,
  Mode,
  PolicyConfigResponse,
  PolicyOverride,
  ReportRequest,
  ScenariosResponse,
  WorkloadsResponse,
} from "../types/api";

export interface ModeChange {
  mode: Mode;
  net: number;
  at: string;
}

interface Hold {
  held: Mode | null;
  candidate: Mode | null;
  streak: number;
}

interface ExperimentState {
  conditions: Conditions;
  setConditions: (next: Conditions) => void;
  updateConditions: (patch: Partial<Conditions>) => void;
  preset: string;
  applyPreset: (value: string) => void;
  activeWorkloadId: string | undefined;
  decision: DecisionResponse | null;
  decisionError: string;
  displayedMode: Mode | null;
  hysteresisEnabled: boolean;
  setHysteresisEnabled: (on: boolean) => void;
  hold: Hold;
  health: HealthResponse | null;
  healthError: string;
  profile: BenchmarkProfileResponse | null;
  setProfile: (profile: BenchmarkProfileResponse) => void;
  config: PolicyConfigResponse | null;
  policyOverride: PolicyOverride | undefined;
  setPolicyOverride: (override: PolicyOverride | undefined) => void;
  scenarios: ScenariosResponse | null;
  workloads: WorkloadsResponse | null;
  history: ModeChange[];
  handshakeResult: HandshakeResponse | null;
  setHandshakeResult: (result: HandshakeResponse | null) => void;
  reportRequest: ReportRequest;
  refreshBenchmarkViews: () => Promise<void>;
}

const INITIAL: Conditions = {
  sensitivity: "MEDIUM",
  lifetime_years: 5,
  latency_budget_ms: 50,
  bandwidth_kbps: 20_000,
  data_bytes: 10_000,
};
const EMPTY_HOLD: Hold = { held: null, candidate: null, streak: 0 };

const ExperimentContext = createContext<ExperimentState | null>(null);

export function ExperimentProvider({ children }: { children: ReactNode }) {
  const [conditions, setConditionsState] = useState<Conditions>(INITIAL);
  const [preset, setPreset] = useState("custom");
  const [activeWorkloadId, setActiveWorkloadId] = useState<string>();
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState("");
  const [hysteresisEnabled, setHysteresisEnabled] = useState(false);
  const [hold, setHold] = useState<Hold>(EMPTY_HOLD);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState("");
  const [profile, setProfile] = useState<BenchmarkProfileResponse | null>(null);
  const [config, setConfig] = useState<PolicyConfigResponse | null>(null);
  const [policyOverride, setPolicyOverride] = useState<PolicyOverride>();
  const [scenarios, setScenarios] = useState<ScenariosResponse | null>(null);
  const [workloads, setWorkloads] = useState<WorkloadsResponse | null>(null);
  const [history, setHistory] = useState<ModeChange[]>([]);
  const [handshakeResult, setHandshakeResult] = useState<HandshakeResponse | null>(null);
  const lastMode = useRef<Mode | null>(null);

  const loadReference = useCallback(async () => {
    try {
      const [h, c, s, w] = await Promise.all([api.health(), api.policyConfig(), api.scenarios(), api.workloads()]);
      setHealth(h);
      setConfig(c);
      setScenarios(s);
      setWorkloads(w);
      setHealthError("");
      if (h.benchmarks_loaded) setProfile(await api.benchmarks());
    } catch (error) {
      setHealthError((error as Error).message);
    }
  }, []);

  useEffect(() => {
    void loadReference();
  }, [loadReference]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const next = await api.decide(conditions, policyOverride, controller.signal);
        setDecision(next);
        setDecisionError("");
        if (next.mode !== lastMode.current) {
          lastMode.current = next.mode;
          setHistory((old) => [{ mode: next.mode, net: next.net, at: new Date().toLocaleTimeString() }, ...old].slice(0, 8));
        }
        const persistence = config?.hysteresis.persistence_samples ?? 3;
        setHold((old) => {
          if (old.held === null || next.mode === old.held) return { held: next.mode, candidate: null, streak: 0 };
          if (next.floor_applied && old.held === "CLASSICAL") return { held: next.mode, candidate: null, streak: 0 };
          const streak = next.mode === old.candidate ? old.streak + 1 : 1;
          return streak >= persistence
            ? { held: next.mode, candidate: null, streak: 0 }
            : { held: old.held, candidate: next.mode, streak };
        });
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setDecision(null);
          setDecisionError((error as Error).message);
        }
      }
    }, 120);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [conditions, policyOverride, config]);

  const setConditions = useCallback((next: Conditions) => setConditionsState(next), []);

  const updateConditions = useCallback((patch: Partial<Conditions>) => {
    setConditionsState((old) => ({ ...old, ...patch }));
    setPreset("custom");
    setActiveWorkloadId(undefined);
  }, []);

  const applyPreset = useCallback(
    (value: string) => {
      setPreset(value);
      if (value.startsWith("scenario:")) {
        const item = scenarios?.scenarios.find((s) => s.name === value.slice(9));
        if (item) setConditionsState(item.conditions);
        setActiveWorkloadId(undefined);
      } else if (value.startsWith("workload:")) {
        const item = workloads?.workloads.find((w) => w.id === value.slice(9));
        if (item) setConditionsState(item.conditions);
        setActiveWorkloadId(item?.id);
      } else {
        setActiveWorkloadId(undefined);
      }
    },
    [scenarios, workloads],
  );

  const refreshBenchmarkViews = useCallback(async () => {
    await loadReference();
    setConditionsState((old) => ({ ...old })); // re-evaluates the decision with the new profile
  }, [loadReference]);

  const value = useMemo<ExperimentState>(
    () => ({
      conditions,
      setConditions,
      updateConditions,
      preset,
      applyPreset,
      activeWorkloadId,
      decision,
      decisionError,
      displayedMode: decision ? (hysteresisEnabled ? hold.held ?? decision.mode : decision.mode) : null,
      hysteresisEnabled,
      setHysteresisEnabled,
      hold,
      health,
      healthError,
      profile,
      setProfile,
      config,
      policyOverride,
      setPolicyOverride,
      scenarios,
      workloads,
      history,
      handshakeResult,
      setHandshakeResult,
      reportRequest: {
        conditions,
        workload_id: activeWorkloadId,
        handshake_result: handshakeResult ?? undefined,
      },
      refreshBenchmarkViews,
    }),
    [conditions, setConditions, updateConditions, preset, applyPreset, activeWorkloadId, decision, decisionError,
      hysteresisEnabled, hold, health, healthError, profile, config, policyOverride, scenarios, workloads, history,
      handshakeResult, refreshBenchmarkViews],
  );

  return <ExperimentContext.Provider value={value}>{children}</ExperimentContext.Provider>;
}

export function useExperiment(): ExperimentState {
  const context = useContext(ExperimentContext);
  if (!context) throw new Error("useExperiment must be used inside ExperimentProvider");
  return context;
}
