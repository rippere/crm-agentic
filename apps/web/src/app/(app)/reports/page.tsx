"use client";

import { useMemo, useState, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { useDeals } from "@/hooks/useDeals";
import { cn, formatCurrency, stageConfig, dealStageOrder } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import {
  BarChart, Bar, LineChart, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ComposedChart, Line, ReferenceLine,
  AreaChart, Area,
} from "recharts";
import Link from "next/link";
import {
  TrendingUp, TrendingDown, DollarSign, Target, BarChart2, AlertTriangle, Trophy, Clock, Timer, Filter, Bot, CalendarOff, Activity, MessageSquare, Sparkles, RefreshCw, ChevronDown, ChevronUp, Users, CheckSquare, CloudDownload, ArrowRight, UserX, ExternalLink, Zap, CheckCircle2, ShieldAlert, BookOpen, ClipboardList, Route, Shield,
} from "lucide-react";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

const STAGE_COLORS: Record<string, string> = {
  discovery:   "#52525B",
  qualified:   "#6366F1",
  proposal:    "#FBBF24",
  negotiation: "#A78BFA",
  closed_won:  "#00C896",
  closed_lost: "#F43F5E",
};

const HEALTH_DIST_CONFIG: Record<string, { label: string; color: string }> = {
  critical: { label: "Critical (<40)",    color: "#F43F5E" },
  at_risk:  { label: "At Risk (40–69)",   color: "#FBBF24" },
  healthy:  { label: "Healthy (70–100)",  color: "#00C896" },
};

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
      <p className="font-mono text-zinc-400 mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="text-zinc-200">{p.name}: {formatCurrency(p.value)}</div>
      ))}
    </div>
  );
};

const VelocityTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; payload: { deal_count: number } }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
      <p className="font-mono text-zinc-400 mb-1">{label}</p>
      <p className="text-zinc-200">Avg: <span className="font-mono text-indigo-300">{payload[0].value}d</span></p>
      <p className="text-zinc-500">{payload[0].payload.deal_count} deal{payload[0].payload.deal_count !== 1 ? "s" : ""}</p>
    </div>
  );
};

type FunnelRow = { stage: string; deal_count: number; conversion_rate: number | null; label: string };

type OutcomeReasonRow = { reason: string; label: string; won: number; lost: number };

export default function ReportsPage() {
  const { deals, loading } = useDeals();
  const [velocityData, setVelocityData] = useState<{ stage: string; avg_days: number; deal_count: number; label: string }[]>([]);
  const [funnelData, setFunnelData] = useState<FunnelRow[]>([]);
  const [outcomeReasons, setOutcomeReasons] = useState<OutcomeReasonRow[]>([]);
  const [agentRunStats, setAgentRunStats] = useState<{ agent_name: string; success: number; failure: number }[]>([]);
  const [slippedDeals, setSlippedDeals] = useState<Array<{ id: string; title: string | null; company: string | null; stage: string; value: number; expected_close: string | null; days_overdue: number }>>([]);
  const [healthDist, setHealthDist] = useState<Array<{ bucket: string; count: number; total_value: number }>>([]);
  const [dealsByAgent, setDealsByAgent] = useState<Array<{ agent_name: string; count: number; total_value: number }>>([]);
  const [revenueForecast, setRevenueForecast] = useState<Array<{ month: string; expected_revenue: number; deal_count: number; total_value: number }>>([]);
  const [stageAging, setStageAging] = useState<Array<{ id: string; title: string | null; company: string | null; stage: string; value: number; days_in_stage: number }>>([]);
  const [winProbByStage, setWinProbByStage] = useState<Array<{ stage: string; avg_probability: number; deal_count: number; total_value: number }>>([]);
  const [pipelineContribution, setPipelineContribution] = useState<Array<{ contact_id: string; name: string | null; email: string | null; company: string | null; pipeline_value: number; closed_won_value: number; deal_count: number; win_rate: number }>>([]);
  const [concentrationRisk, setConcentrationRisk] = useState<{ total_pipeline: number; top_deals: Array<{ id: string; title: string | null; company: string | null; stage: string; value: number; pct_of_pipeline: number }>; top3_pct: number; risk_level: "low" | "medium" | "high" } | null>(null);
  const [closeDateAccuracy, setCloseDateAccuracy] = useState<Array<{ id: string; title: string | null; company: string | null; value: number; expected_close: string; actual_close: string; days_delta: number; outcome: "early" | "on_time" | "late" }>>([]);
  const [activityTrends, setActivityTrends] = useState<Array<{ week_start: string; total: number; deals: number; contacts: number; agents: number; messages: number }>>([]);
  const [reengagementSummary, setReengagementSummary] = useState<Array<{ week_start: string; reengaged: number }>>([]);
  const [revenueCohort, setRevenueCohort] = useState<Array<{
    cohort_month: string;
    initial_revenue: number;
    months: Array<{ month_offset: number; revenue: number; deal_count: number; pct_of_initial: number | null }>;
  }>>([]);
  const [velocityTrends, setVelocityTrends] = useState<Array<{
    month: string;
    avg_cycle_days: number | null;
    deal_count: number;
    closed_won: number;
    closed_lost: number;
  }>>([]);
  const [messageVolume, setMessageVolume] = useState<Array<{ week_start: string; gmail: number; slack: number; teams: number; unknown: number; total: number }>>([]);
  const [pipelineHealth, setPipelineHealth] = useState<{
    health_score: number;
    rating: 'strong' | 'healthy' | 'at_risk' | 'critical';
    briefing: string;
    priorities: string[];
    generated_at: string;
  } | null>(null);
  const [pipelineHealthLoading, setPipelineHealthLoading] = useState(false);
  const [pipelineHealthOpen, setPipelineHealthOpen] = useState(true);
  const [teamPerf, setTeamPerf] = useState<{
    performance_rating: 'excellent' | 'good' | 'needs_improvement' | 'critical';
    highlights: string[];
    areas_for_improvement: string[];
    summary_sentence: string;
    metrics: {
      agent_runs: number;
      task_completion_rate: number;
      messages_processed: number;
      deals_moved: number;
      active_contacts: number;
    };
    generated_at: string;
  } | null>(null);
  const [teamPerfLoading, setTeamPerfLoading] = useState(false);
  const [teamPerfOpen, setTeamPerfOpen] = useState(true);
  const [competitiveLandscape, setCompetitiveLandscape] = useState<{
    top_competitors: Array<{ name: string; deal_count: number; stages_present: string[]; threat_level: 'low' | 'medium' | 'high'; positioning_note: string }>
    competitive_summary: string
    win_strategies: string[]
    generated_at: string
  } | null>(null);
  const [competitiveLandscapeLoading, setCompetitiveLandscapeLoading] = useState(false);
  const [competitiveLandscapeOpen, setCompetitiveLandscapeOpen] = useState(true);

  type AgentStat = { agent_name: string; run_count: number; success_count: number; failure_count: number; success_rate: number };
  type AgentPerfReport = {
    agent_stats: AgentStat[]
    overall_success_rate: number
    most_active_agent: string | null
    least_reliable_agent: string | null
    narrative: string
    recommendations: string[]
    generated_at: string
  };
  const [agentPerfReport, setAgentPerfReport] = useState<AgentPerfReport | null>(null);
  const [agentPerfReportLoading, setAgentPerfReportLoading] = useState(false);
  const [agentPerfReportOpen, setAgentPerfReportOpen] = useState(true);

  type CalibrationBucket = { bucket_label: string; predicted_avg: number; actual_win_rate: number | null; deal_count: number };
  type CalibrationData = {
    calibration_buckets: CalibrationBucket[]
    calibration_score: number | null
    overall_bias: 'optimistic' | 'pessimistic' | 'well_calibrated'
    narrative: string
    recommendations: string[]
    generated_at: string
  };
  const [calibrationData, setCalibrationData] = useState<CalibrationData | null>(null);
  const [calibrationLoading, setCalibrationLoading] = useState(false);
  const [calibrationOpen, setCalibrationOpen] = useState(true);

  type FunnelStage = { stage: string; count: number; conversion_rate: number | null };
  type AcquisitionFunnel = {
    funnel_stages: FunnelStage[]
    top_insight: string
    recommendations: string[]
    generated_at: string
  };
  const [acquisitionFunnel, setAcquisitionFunnel] = useState<AcquisitionFunnel | null>(null);
  const [acquisitionFunnelLoading, setAcquisitionFunnelLoading] = useState(false);
  const [acquisitionFunnelOpen, setAcquisitionFunnelOpen] = useState(true);

  type SourceAttribution = {
    sources: Array<{ source_label: string; contact_count: number; pipeline_value: number; won_revenue: number; win_rate: number }>
    top_source: string | null
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [sourceAttribution, setSourceAttribution] = useState<SourceAttribution | null>(null);
  const [sourceAttributionLoading, setSourceAttributionLoading] = useState(false);
  const [sourceAttributionOpen, setSourceAttributionOpen] = useState(true);

  type TaskWeek = { week_start: string; created: number; completed: number; overdue: number; completion_rate: number };
  type TaskCompletionTrends = {
    weeks: TaskWeek[]
    avg_completion_rate: number
    trend: 'improving' | 'stable' | 'declining'
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [taskCompletionTrends, setTaskCompletionTrends] = useState<TaskCompletionTrends | null>(null);
  const [taskCompletionTrendsLoading, setTaskCompletionTrendsLoading] = useState(false);
  const [taskCompletionTrendsOpen, setTaskCompletionTrendsOpen] = useState(true);

  type MsgBenchmarkRow = { service: string; avg_hours: number; p50_hours: number; p90_hours: number; message_count: number };
  type MsgResponseBenchmark = {
    benchmark: MsgBenchmarkRow[]
    overall_avg_hours: number | null
    rating: 'excellent' | 'good' | 'fair' | 'slow'
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [msgBenchmark, setMsgBenchmark] = useState<MsgResponseBenchmark | null>(null);
  const [msgBenchmarkLoading, setMsgBenchmarkLoading] = useState(false);
  const [msgBenchmarkOpen, setMsgBenchmarkOpen] = useState(true);

  type EngagementBenchmarkContact = { id: string; name: string | null; email: string | null; score: number };
  type EngagementBenchmark = {
    buckets: Array<{ label: string; count: number; avg_score: number }>
    top_contacts: EngagementBenchmarkContact[]
    bottom_contacts: EngagementBenchmarkContact[]
    avg_score: number
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [engagementBenchmark, setEngagementBenchmark] = useState<EngagementBenchmark | null>(null);
  const [engagementBenchmarkLoading, setEngagementBenchmarkLoading] = useState(false);
  const [engagementBenchmarkOpen, setEngagementBenchmarkOpen] = useState(true);

  type NegotiationDeal = {
    id: string; title: string; company: string; stage: string;
    readiness: 'ready' | 'needs_work' | 'not_ready'; blockers: string[]; next_steps: string[];
  };
  type NegotiationReadiness = {
    total_deals: number; ready_count: number; not_ready_count: number;
    deals: NegotiationDeal[]; summary: string; generated_at: string;
  };
  const [negotiationReadiness, setNegotiationReadiness] = useState<NegotiationReadiness | null>(null);
  const [negotiationReadinessLoading, setNegotiationReadinessLoading] = useState(false);
  const [negotiationReadinessOpen, setNegotiationReadinessOpen] = useState(true);

  type MsgSourceRow = { service: string; total_messages: number; processed_rate: number; weekly_trend: number[] };
  type MsgSourceReliability = {
    sources: MsgSourceRow[]
    most_reliable_source: string | null
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [msgSourceReliability, setMsgSourceReliability] = useState<MsgSourceReliability | null>(null);
  const [msgSourceReliabilityLoading, setMsgSourceReliabilityLoading] = useState(false);
  const [msgSourceReliabilityOpen, setMsgSourceReliabilityOpen] = useState(true);

  type StageTransition = { from_stage: string; to_stage: string; count: number; avg_days: number };
  type StageTransitionAnalysis = {
    transitions: StageTransition[]
    bottleneck_stage: string | null
    fastest_transition: string | null
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [stageTransitionAnalysis, setStageTransitionAnalysis] = useState<StageTransitionAnalysis | null>(null);
  const [stageTransitionLoading, setStageTransitionLoading] = useState(false);
  const [stageTransitionOpen, setStageTransitionOpen] = useState(true);

  type RevenueTrendMonth = { month: string; revenue: number; deal_count: number; avg_deal_size: number };
  type RevenueTrendAnalysis = {
    monthly_trend: RevenueTrendMonth[]
    growth_rate: number | null
    best_month: string | null
    trend_direction: 'accelerating' | 'growing' | 'stable' | 'declining'
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [revenueTrend, setRevenueTrend] = useState<RevenueTrendAnalysis | null>(null);
  const [revenueTrendLoading, setRevenueTrendLoading] = useState(false);
  const [revenueTrendOpen, setRevenueTrendOpen] = useState(true);

  type InactivityBucketContact = { id: string; name: string; email: string; company: string; days_since_touch: number };
  type InactivityBucket = { bucket: 'critical' | 'high_risk' | 'watch'; contacts: InactivityBucketContact[] };
  type InactivityRisk = {
    critical_count: number; high_risk_count: number; watch_count: number; total_contacts: number;
    contacts_by_bucket: InactivityBucket[]; insight: string; recommendations: string[]; generated_at: string;
  };
  const [inactivityRisk, setInactivityRisk] = useState<InactivityRisk | null>(null);
  const [inactivityRiskLoading, setInactivityRiskLoading] = useState(false);
  const [inactivityRiskOpen, setInactivityRiskOpen] = useState(true);
  const [inactivityExpandedBuckets, setInactivityExpandedBuckets] = useState<Set<string>>(new Set());

  type PipelineMomentum = {
    momentum_score: number
    momentum_rating: 'accelerating' | 'steady' | 'stalling' | 'declining'
    new_deals_14d: number
    stage_moves_14d: number
    at_risk_count: number
    highlights: string[]
    warnings: string[]
    generated_at: string
  };
  const [pipelineMomentum, setPipelineMomentum] = useState<PipelineMomentum | null>(null);
  const [pipelineMomentumLoading, setPipelineMomentumLoading] = useState(false);
  const [pipelineMomentumOpen, setPipelineMomentumOpen] = useState(true);

  type DealAgeRiskDeal = {
    id: string
    title: string | null
    stage: string
    days_open: number
    expected_days: number
    risk_level: 'overdue' | 'at_risk' | 'on_track'
  };
  type DealAgeRisk = {
    overdue_count: number
    at_risk_count: number
    on_track_count: number
    total_open_deals: number
    deals: DealAgeRiskDeal[]
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [dealAgeRisk, setDealAgeRisk] = useState<DealAgeRisk | null>(null);
  const [dealAgeRiskLoading, setDealAgeRiskLoading] = useState(false);
  const [dealAgeRiskOpen, setDealAgeRiskOpen] = useState(true);

  type TopPerformerDeal = { id: string; title: string | null; company: string | null; value: number; win_probability: number; cycle_days: number | null };
  type TopPerformerDeals = {
    top_by_value: TopPerformerDeal[]
    top_by_speed: TopPerformerDeal[]
    top_by_confidence: TopPerformerDeal[]
    avg_win_rate: number | null
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [topPerformers, setTopPerformers] = useState<TopPerformerDeals | null>(null);
  const [topPerformersLoading, setTopPerformersLoading] = useState(false);
  const [topPerformersOpen, setTopPerformersOpen] = useState(true);
  const [topPerformersTab, setTopPerformersTab] = useState<'value' | 'speed' | 'confidence'>('value');

  type StageConcentrationRow = { stage: string; count: number; total_value: number; avg_health: number | null; pct_of_pipeline: number };
  type StageConcentration = {
    stages: StageConcentrationRow[]
    highest_value_stage: string | null
    most_stalled_stage: string | null
    total_pipeline_value: number
    insight: string
    recommendations: string[]
    generated_at: string
  };
  const [stageConcentration, setStageConcentration] = useState<StageConcentration | null>(null);
  const [stageConcentrationLoading, setStageConcentrationLoading] = useState(false);
  const [stageConcentrationOpen, setStageConcentrationOpen] = useState(true);

  type CloseRateStage = { stage: string; win_count: number; loss_count: number; total: number; win_rate: number };
  type CloseRateByStage = {
    stage_rates: CloseRateStage[];
    best_converting_stage: string | null;
    worst_converting_stage: string | null;
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [closeRateByStage, setCloseRateByStage] = useState<CloseRateByStage | null>(null);
  const [closeRateByStageLoading, setCloseRateByStageLoading] = useState(false);
  const [closeRateByStageOpen, setCloseRateByStageOpen] = useState(true);

  type PipelineChurnStage = { stage: string; total_entered: number; churned_count: number; churn_rate: number };
  type PipelineChurn = {
    stage_churn: PipelineChurnStage[];
    highest_churn_stage: string | null;
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [pipelineChurn, setPipelineChurn] = useState<PipelineChurn | null>(null);
  const [pipelineChurnLoading, setPipelineChurnLoading] = useState(false);
  const [pipelineChurnOpen, setPipelineChurnOpen] = useState(true);

  type ConversionQualityTier = { tier: string; count: number; avg_value: number; avg_cycle_days: number; avg_health: number };
  type ConversionQuality = {
    quality_tiers: ConversionQualityTier[];
    avg_quality_score: number;
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [conversionQuality, setConversionQuality] = useState<ConversionQuality | null>(null);
  const [conversionQualityLoading, setConversionQualityLoading] = useState(false);
  const [conversionQualityOpen, setConversionQualityOpen] = useState(true);

  type WinLossStagePattern = { stage: string; won: number; lost: number; win_rate: number };
  type WinLossPatterns = {
    stage_patterns: WinLossStagePattern[];
    competitor_impact: { with_competitors_win_rate: number; without_competitors_win_rate: number };
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [winLossPatterns, setWinLossPatterns] = useState<WinLossPatterns | null>(null);
  const [winLossPatternsLoading, setWinLossPatternsLoading] = useState(false);
  const [winLossPatternsOpen, setWinLossPatternsOpen] = useState(true);

  type AvgDealSizeMonth = { month: string; avg_value: number; deal_count: number };
  type AvgDealSizeTrend = {
    months: AvgDealSizeMonth[];
    trend_direction: string;
    best_month: string | null;
    pct_change: number;
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [avgDealSizeTrend, setAvgDealSizeTrend] = useState<AvgDealSizeTrend | null>(null);
  const [avgDealSizeTrendLoading, setAvgDealSizeTrendLoading] = useState(false);
  const [avgDealSizeTrendOpen, setAvgDealSizeTrendOpen] = useState(true);

  type FollowupGapDeal = { deal_id: string; title: string; company: string; stage: string; days_since_contact: number };
  type FollowupGaps = {
    overdue: FollowupGapDeal[];
    due_soon: FollowupGapDeal[];
    on_track_count: number;
    avg_days_since_contact: number;
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [followupGaps, setFollowupGaps] = useState<FollowupGaps | null>(null);
  const [followupGapsLoading, setFollowupGapsLoading] = useState(false);
  const [followupGapsOpen, setFollowupGapsOpen] = useState(true);

  type ValueAtRiskDeal = { deal_id: string; title: string; company: string; stage: string; value: number; health_score: number; risk_reason: string };
  type ValueAtRisk = {
    total_pipeline_value: number;
    at_risk_value: number;
    at_risk_pct: number;
    at_risk_deals: ValueAtRiskDeal[];
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [valueAtRisk, setValueAtRisk] = useState<ValueAtRisk | null>(null);
  const [valueAtRiskLoading, setValueAtRiskLoading] = useState(false);
  const [valueAtRiskOpen, setValueAtRiskOpen] = useState(true);

  type NextBestAction = { deal_id: string; priority: 'high' | 'medium' | 'low'; action: string; rationale: string };
  type NextBestActions = {
    actions: NextBestAction[];
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [nextBestActions, setNextBestActions] = useState<NextBestActions | null>(null);
  const [nextBestActionsLoading, setNextBestActionsLoading] = useState(false);
  const [nextBestActionsOpen, setNextBestActionsOpen] = useState(true);

  type CoachedDeal = {
    deal_id: string; title: string; stage: string; value: number;
    what_to_do: string; what_to_avoid: string; talking_points: string[];
  };
  type CoachingDigest = {
    coached_deals: CoachedDeal[];
    weekly_theme: string;
    recommendations: string[];
    generated_at: string;
  };
  const [coachingDigest, setCoachingDigest] = useState<CoachingDigest | null>(null);
  const [coachingDigestLoading, setCoachingDigestLoading] = useState(false);
  const [coachingDigestOpen, setCoachingDigestOpen] = useState(true);
  const [coachingExpandedDeal, setCoachingExpandedDeal] = useState<string | null>(null);

  type QbrTopWin = { id: string; title: string; company: string; value: number; closed_at: string | null };
  type QbrTopRisk = { id: string; title: string; company: string; stage: string; value: number; health_score: number };
  type QbrMetrics = {
    closed_won_count: number; closed_won_revenue: number; closed_lost_count: number;
    win_rate: number; open_deal_count: number; total_pipeline_value: number;
    at_risk_count: number; avg_win_probability: number;
  };
  type QbrSummary = {
    quarter: string;
    wins_summary: string;
    pipeline_status: string;
    top_wins: QbrTopWin[];
    top_risks: QbrTopRisk[];
    strategic_recommendations: string[];
    metrics: QbrMetrics;
    generated_at: string;
  };
  const [qbrSummary, setQbrSummary] = useState<QbrSummary | null>(null);
  const [qbrSummaryLoading, setQbrSummaryLoading] = useState(false);
  const [qbrSummaryOpen, setQbrSummaryOpen] = useState(true);

  type ConversionPath = { stages_sequence: string[]; deal_count: number; win_rate: number; avg_days: number };
  type ConversionPathData = {
    paths: ConversionPath[];
    most_common_path: string[] | null;
    fastest_path: string[] | null;
    insight: string;
    recommendations: string[];
    generated_at: string;
  };
  const [conversionPaths, setConversionPaths] = useState<ConversionPathData | null>(null);
  const [conversionPathsLoading, setConversionPathsLoading] = useState(false);
  const [conversionPathsOpen, setConversionPathsOpen] = useState(true);

  type StagePlaybookEntry = {
    stage: string;
    key_actions: string[];
    success_signals: string[];
    common_mistakes: string[];
  };
  type PlaybookData = {
    playbook_title: string;
    winning_profile: { avg_health: number; avg_cycle_days: number; won_count: number; lost_count: number; win_rate: number };
    key_behaviors: string[];
    stage_playbook: StagePlaybookEntry[];
    recommendations: string[];
    generated_at: string;
  };
  const [playbook, setPlaybook] = useState<PlaybookData | null>(null);
  const [playbookLoading, setPlaybookLoading] = useState(false);
  const [playbookOpen, setPlaybookOpen] = useState(true);
  const [playbookExpandedStage, setPlaybookExpandedStage] = useState<string | null>(null);

  type BattleCard = {
    competitor: string;
    encounter_count: number;
    win_rate: number | null;
    key_differentiators: string[];
    objection_responses: string[];
    positioning: string;
  };
  type BattleCardData = {
    battle_cards: BattleCard[];
    top_competitor: string | null;
    recommendations: string[];
    generated_at: string;
  };
  const [battleCard, setBattleCard] = useState<BattleCardData | null>(null);
  const [battleCardLoading, setBattleCardLoading] = useState(false);
  const [battleCardOpen, setBattleCardOpen] = useState(true);
  const [battleCardExpanded, setBattleCardExpanded] = useState<string | null>(null);

  type RiskEscalation = {
    deal_id: string;
    title: string;
    company: string;
    stage: string;
    value: number;
    health_score: number;
    win_probability: number;
    days_stale: number;
    risk_factors: string[];
    suggested_action: string;
  };
  type RiskEscalationData = {
    escalations: RiskEscalation[];
    total_at_risk_value: number;
    recommendations: string[];
    generated_at: string;
  };
  const [riskEscalation, setRiskEscalation] = useState<RiskEscalationData | null>(null);
  const [riskEscalationLoading, setRiskEscalationLoading] = useState(false);
  const [riskEscalationOpen, setRiskEscalationOpen] = useState(true);
  const [riskEscalationExpanded, setRiskEscalationExpanded] = useState<string | null>(null);

  type MomentumDeal = { deal_id: string; title: string; velocity_score: number; trend_description: string };
  type MomentumData = {
    accelerating: MomentumDeal[]; decelerating: MomentumDeal[]; stalled: MomentumDeal[];
    momentum_index: number; insight: string; recommendations: string[]; generated_at: string;
  };
  const [momentum, setMomentum] = useState<MomentumData | null>(null);
  const [momentumLoading, setMomentumLoading] = useState(false);
  const [momentumOpen, setMomentumOpen] = useState(true);

  useEffect(() => {
    if (DEMO_MODE) {
      apiClient.getDealVelocity("demo-workspace-1", "demo-token").then((data) => {
        setVelocityData(data.map((v) => ({ ...v, label: stageConfig[v.stage as keyof typeof stageConfig]?.label ?? v.stage })));
      }).catch(() => {});
      apiClient.getDealFunnel("demo-workspace-1", "demo-token").then((data) => {
        setFunnelData(data.map((r) => ({ ...r, label: stageConfig[r.stage as keyof typeof stageConfig]?.label ?? r.stage })));
      }).catch(() => {});
      apiClient.getDealOutcomeReasons("demo-workspace-1", "demo-token").then(setOutcomeReasons).catch(() => {});
      apiClient.getAgentRunStats("demo-workspace-1", "demo-token").then(setAgentRunStats).catch(() => {});
      apiClient.getDealCloseDateSlipped("demo-workspace-1", "demo-token").then(setSlippedDeals).catch(() => {});
      apiClient.getDealHealthDistribution("demo-workspace-1", "demo-token").then(setHealthDist).catch(() => {});
      apiClient.getDealsByAgent("demo-workspace-1", "demo-token").then(setDealsByAgent).catch(() => {});
      apiClient.getDealRevenueForecast("demo-workspace-1", "demo-token").then(setRevenueForecast).catch(() => {});
      apiClient.getDealStageAging("demo-workspace-1", "demo-token").then(setStageAging).catch(() => {});
      apiClient.getDealWinProbabilityByStage("demo-workspace-1", "demo-token").then(setWinProbByStage).catch(() => {});
      apiClient.getContactPipelineContribution("demo-workspace-1", "demo-token").then(setPipelineContribution).catch(() => {});
      apiClient.getDealConcentrationRisk("demo-workspace-1", "demo-token").then(setConcentrationRisk).catch(() => {});
      apiClient.getDealCloseDateAccuracy("demo-workspace-1", "demo-token").then(setCloseDateAccuracy).catch(() => {});
      apiClient.getActivityTrends("demo-workspace-1", "demo-token").then(setActivityTrends).catch(() => {});
      apiClient.getContactReengagementSummary("demo-workspace-1", "demo-token").then(setReengagementSummary).catch(() => {});
      apiClient.getRevenueCohort("demo-workspace-1", "demo-token").then(setRevenueCohort).catch(() => {});
      apiClient.getDealVelocityTrends("demo-workspace-1", "demo-token").then(setVelocityTrends).catch(() => {});
      apiClient.getMessageVolumeTrends("demo-workspace-1", "demo-token").then(setMessageVolume).catch(() => {});
      setPipelineHealthLoading(true);
      apiClient.getPipelineHealthBriefing("demo-workspace-1", "demo-token").then(setPipelineHealth).catch(() => {}).finally(() => setPipelineHealthLoading(false));
      setTeamPerfLoading(true);
      apiClient.getTeamPerformance("demo-workspace-1", "demo-token").then(setTeamPerf).catch(() => {}).finally(() => setTeamPerfLoading(false));
      setCompetitiveLandscapeLoading(true);
      apiClient.getCompetitiveLandscape("demo-workspace-1", "demo-token").then(setCompetitiveLandscape).catch(() => {}).finally(() => setCompetitiveLandscapeLoading(false));
      setCalibrationLoading(true);
      apiClient.getWinProbabilityCalibration("demo-workspace-1", "demo-token").then(setCalibrationData).catch(() => {}).finally(() => setCalibrationLoading(false));
      setAgentPerfReportLoading(true);
      apiClient.getAgentPerformanceReport("demo-workspace-1", "demo-token").then(setAgentPerfReport).catch(() => {}).finally(() => setAgentPerfReportLoading(false));
      setAcquisitionFunnelLoading(true);
      apiClient.getContactAcquisitionFunnel("demo-workspace-1", "demo-token").then(setAcquisitionFunnel).catch(() => {}).finally(() => setAcquisitionFunnelLoading(false));
      setSourceAttributionLoading(true);
      apiClient.getContactSourceAttribution("demo-workspace-1", "demo-token").then(setSourceAttribution).catch(() => {}).finally(() => setSourceAttributionLoading(false));
      setTaskCompletionTrendsLoading(true);
      apiClient.getTaskCompletionTrends("demo-workspace-1", "demo-token").then(setTaskCompletionTrends).catch(() => {}).finally(() => setTaskCompletionTrendsLoading(false));
      setMsgBenchmarkLoading(true);
      apiClient.getMessageResponseTimeBenchmark("demo-workspace-1", "demo-token").then(setMsgBenchmark).catch(() => {}).finally(() => setMsgBenchmarkLoading(false));
      setEngagementBenchmarkLoading(true);
      apiClient.getContactEngagementBenchmark("demo-workspace-1", "demo-token").then(setEngagementBenchmark).catch(() => {}).finally(() => setEngagementBenchmarkLoading(false));
      setNegotiationReadinessLoading(true);
      apiClient.getDealsNegotiationReadiness("demo-workspace-1", "demo-token").then(setNegotiationReadiness).catch(() => {}).finally(() => setNegotiationReadinessLoading(false));
      setMsgSourceReliabilityLoading(true);
      apiClient.getMessageSourceReliability("demo-workspace-1", "demo-token").then(setMsgSourceReliability).catch(() => {}).finally(() => setMsgSourceReliabilityLoading(false));
      setStageTransitionLoading(true);
      apiClient.getStageTransitionAnalysis("demo-workspace-1", "demo-token").then(setStageTransitionAnalysis).catch(() => {}).finally(() => setStageTransitionLoading(false));
      setRevenueTrendLoading(true);
      apiClient.getRevenueTrendAnalysis("demo-workspace-1", "demo-token").then(setRevenueTrend).catch(() => {}).finally(() => setRevenueTrendLoading(false));
      setInactivityRiskLoading(true);
      apiClient.getContactInactivityRisk("demo-workspace-1", "demo-token").then(setInactivityRisk).catch(() => {}).finally(() => setInactivityRiskLoading(false));
      setPipelineMomentumLoading(true);
      apiClient.getDealsPipelineMomentum("demo-workspace-1", "demo-token").then(setPipelineMomentum).catch(() => {}).finally(() => setPipelineMomentumLoading(false));
      setDealAgeRiskLoading(true);
      apiClient.getDealAgeRisk("demo-workspace-1", "demo-token").then(setDealAgeRisk).catch(() => {}).finally(() => setDealAgeRiskLoading(false));
      setTopPerformersLoading(true);
      apiClient.getTopPerformerDeals("demo-workspace-1", "demo-token").then(setTopPerformers).catch(() => {}).finally(() => setTopPerformersLoading(false));
      setStageConcentrationLoading(true);
      apiClient.getDealStageConcentration("demo-workspace-1", "demo-token").then(setStageConcentration).catch(() => {}).finally(() => setStageConcentrationLoading(false));
      setCloseRateByStageLoading(true);
      apiClient.getDealCloseRateByStage("demo-workspace-1", "demo-token").then(setCloseRateByStage).catch(() => {}).finally(() => setCloseRateByStageLoading(false));
      setPipelineChurnLoading(true);
      apiClient.getDealPipelineChurn("demo-workspace-1", "demo-token").then(setPipelineChurn).catch(() => {}).finally(() => setPipelineChurnLoading(false));
      setConversionQualityLoading(true);
      apiClient.getDealConversionQuality("demo-workspace-1", "demo-token").then(setConversionQuality).catch(() => {}).finally(() => setConversionQualityLoading(false));
      setWinLossPatternsLoading(true);
      apiClient.getDealWinLossPatterns("demo-workspace-1", "demo-token").then(setWinLossPatterns).catch(() => {}).finally(() => setWinLossPatternsLoading(false));
      setAvgDealSizeTrendLoading(true);
      apiClient.getAvgDealSizeTrend("demo-workspace-1", "demo-token").then(setAvgDealSizeTrend).catch(() => {}).finally(() => setAvgDealSizeTrendLoading(false));
      setFollowupGapsLoading(true);
      apiClient.getDealFollowupGaps("demo-workspace-1", "demo-token").then(setFollowupGaps).catch(() => {}).finally(() => setFollowupGapsLoading(false));
      setValueAtRiskLoading(true);
      apiClient.getDealValueAtRisk("demo-workspace-1", "demo-token").then(setValueAtRisk).catch(() => {}).finally(() => setValueAtRiskLoading(false));
      setNextBestActionsLoading(true);
      apiClient.getDealNextBestActions("demo-workspace-1", "demo-token").then(setNextBestActions).catch(() => {}).finally(() => setNextBestActionsLoading(false));
      setCoachingDigestLoading(true);
      apiClient.getDealCoachingDigest("demo-workspace-1", "demo-token").then(setCoachingDigest).catch(() => {}).finally(() => setCoachingDigestLoading(false));
      setQbrSummaryLoading(true);
      apiClient.getQbrSummary("demo-workspace-1", "demo-token").then(setQbrSummary).catch(() => {}).finally(() => setQbrSummaryLoading(false));
      setConversionPathsLoading(true);
      apiClient.getDealConversionPaths("demo-workspace-1", "demo-token").then(setConversionPaths).catch(() => {}).finally(() => setConversionPathsLoading(false));
      setPlaybookLoading(true);
      apiClient.getDealPlaybook("demo-workspace-1", "demo-token").then(setPlaybook).catch(() => {}).finally(() => setPlaybookLoading(false));
      setBattleCardLoading(true);
      apiClient.getDealBattleCard("demo-workspace-1", "demo-token").then(setBattleCard).catch(() => {}).finally(() => setBattleCardLoading(false));
      setRiskEscalationLoading(true);
      apiClient.getDealRiskEscalation("demo-workspace-1", "demo-token").then(setRiskEscalation).catch(() => {}).finally(() => setRiskEscalationLoading(false));
      setMomentumLoading(true);
      apiClient.getDealMomentum("demo-workspace-1", "demo-token").then(setMomentum).catch(() => {}).finally(() => setMomentumLoading(false));
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      const workspaceId: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
      if (!workspaceId) return;
      apiClient.getDealVelocity(workspaceId, session.access_token).then((data) => {
        setVelocityData(data.map((v) => ({ ...v, label: stageConfig[v.stage as keyof typeof stageConfig]?.label ?? v.stage })));
      }).catch(() => {});
      apiClient.getDealFunnel(workspaceId, session.access_token).then((data) => {
        setFunnelData(data.map((r) => ({ ...r, label: stageConfig[r.stage as keyof typeof stageConfig]?.label ?? r.stage })));
      }).catch(() => {});
      apiClient.getDealOutcomeReasons(workspaceId, session.access_token).then(setOutcomeReasons).catch(() => {});
      apiClient.getAgentRunStats(workspaceId, session.access_token).then(setAgentRunStats).catch(() => {});
      apiClient.getDealCloseDateSlipped(workspaceId, session.access_token).then(setSlippedDeals).catch(() => {});
      apiClient.getDealHealthDistribution(workspaceId, session.access_token).then(setHealthDist).catch(() => {});
      apiClient.getDealsByAgent(workspaceId, session.access_token).then(setDealsByAgent).catch(() => {});
      apiClient.getDealRevenueForecast(workspaceId, session.access_token).then(setRevenueForecast).catch(() => {});
      apiClient.getDealStageAging(workspaceId, session.access_token).then(setStageAging).catch(() => {});
      apiClient.getDealWinProbabilityByStage(workspaceId, session.access_token).then(setWinProbByStage).catch(() => {});
      apiClient.getContactPipelineContribution(workspaceId, session.access_token).then(setPipelineContribution).catch(() => {});
      apiClient.getDealConcentrationRisk(workspaceId, session.access_token).then(setConcentrationRisk).catch(() => {});
      apiClient.getDealCloseDateAccuracy(workspaceId, session.access_token).then(setCloseDateAccuracy).catch(() => {});
      apiClient.getActivityTrends(workspaceId, session.access_token).then(setActivityTrends).catch(() => {});
      apiClient.getContactReengagementSummary(workspaceId, session.access_token).then(setReengagementSummary).catch(() => {});
      apiClient.getRevenueCohort(workspaceId, session.access_token).then(setRevenueCohort).catch(() => {});
      apiClient.getDealVelocityTrends(workspaceId, session.access_token).then(setVelocityTrends).catch(() => {});
      apiClient.getMessageVolumeTrends(workspaceId, session.access_token).then(setMessageVolume).catch(() => {});
      setPipelineHealthLoading(true);
      apiClient.getPipelineHealthBriefing(workspaceId, session.access_token).then(setPipelineHealth).catch(() => {}).finally(() => setPipelineHealthLoading(false));
      setTeamPerfLoading(true);
      apiClient.getTeamPerformance(workspaceId, session.access_token).then(setTeamPerf).catch(() => {}).finally(() => setTeamPerfLoading(false));
      setCompetitiveLandscapeLoading(true);
      apiClient.getCompetitiveLandscape(workspaceId, session.access_token).then(setCompetitiveLandscape).catch(() => {}).finally(() => setCompetitiveLandscapeLoading(false));
      setCalibrationLoading(true);
      apiClient.getWinProbabilityCalibration(workspaceId, session.access_token).then(setCalibrationData).catch(() => {}).finally(() => setCalibrationLoading(false));
      setAgentPerfReportLoading(true);
      apiClient.getAgentPerformanceReport(workspaceId, session.access_token).then(setAgentPerfReport).catch(() => {}).finally(() => setAgentPerfReportLoading(false));
      setAcquisitionFunnelLoading(true);
      apiClient.getContactAcquisitionFunnel(workspaceId, session.access_token).then(setAcquisitionFunnel).catch(() => {}).finally(() => setAcquisitionFunnelLoading(false));
      setSourceAttributionLoading(true);
      apiClient.getContactSourceAttribution(workspaceId, session.access_token).then(setSourceAttribution).catch(() => {}).finally(() => setSourceAttributionLoading(false));
      setTaskCompletionTrendsLoading(true);
      apiClient.getTaskCompletionTrends(workspaceId, session.access_token).then(setTaskCompletionTrends).catch(() => {}).finally(() => setTaskCompletionTrendsLoading(false));
      setMsgBenchmarkLoading(true);
      apiClient.getMessageResponseTimeBenchmark(workspaceId, session.access_token).then(setMsgBenchmark).catch(() => {}).finally(() => setMsgBenchmarkLoading(false));
      setEngagementBenchmarkLoading(true);
      apiClient.getContactEngagementBenchmark(workspaceId, session.access_token).then(setEngagementBenchmark).catch(() => {}).finally(() => setEngagementBenchmarkLoading(false));
      setNegotiationReadinessLoading(true);
      apiClient.getDealsNegotiationReadiness(workspaceId, session.access_token).then(setNegotiationReadiness).catch(() => {}).finally(() => setNegotiationReadinessLoading(false));
      setMsgSourceReliabilityLoading(true);
      apiClient.getMessageSourceReliability(workspaceId, session.access_token).then(setMsgSourceReliability).catch(() => {}).finally(() => setMsgSourceReliabilityLoading(false));
      setStageTransitionLoading(true);
      apiClient.getStageTransitionAnalysis(workspaceId, session.access_token).then(setStageTransitionAnalysis).catch(() => {}).finally(() => setStageTransitionLoading(false));
      setRevenueTrendLoading(true);
      apiClient.getRevenueTrendAnalysis(workspaceId, session.access_token).then(setRevenueTrend).catch(() => {}).finally(() => setRevenueTrendLoading(false));
      setInactivityRiskLoading(true);
      apiClient.getContactInactivityRisk(workspaceId, session.access_token).then(setInactivityRisk).catch(() => {}).finally(() => setInactivityRiskLoading(false));
      setPipelineMomentumLoading(true);
      apiClient.getDealsPipelineMomentum(workspaceId, session.access_token).then(setPipelineMomentum).catch(() => {}).finally(() => setPipelineMomentumLoading(false));
      setDealAgeRiskLoading(true);
      apiClient.getDealAgeRisk(workspaceId, session.access_token).then(setDealAgeRisk).catch(() => {}).finally(() => setDealAgeRiskLoading(false));
      setTopPerformersLoading(true);
      apiClient.getTopPerformerDeals(workspaceId, session.access_token).then(setTopPerformers).catch(() => {}).finally(() => setTopPerformersLoading(false));
      setStageConcentrationLoading(true);
      apiClient.getDealStageConcentration(workspaceId, session.access_token).then(setStageConcentration).catch(() => {}).finally(() => setStageConcentrationLoading(false));
      setCloseRateByStageLoading(true);
      apiClient.getDealCloseRateByStage(workspaceId, session.access_token).then(setCloseRateByStage).catch(() => {}).finally(() => setCloseRateByStageLoading(false));
      setPipelineChurnLoading(true);
      apiClient.getDealPipelineChurn(workspaceId, session.access_token).then(setPipelineChurn).catch(() => {}).finally(() => setPipelineChurnLoading(false));
      setConversionQualityLoading(true);
      apiClient.getDealConversionQuality(workspaceId, session.access_token).then(setConversionQuality).catch(() => {}).finally(() => setConversionQualityLoading(false));
      setWinLossPatternsLoading(true);
      apiClient.getDealWinLossPatterns(workspaceId, session.access_token).then(setWinLossPatterns).catch(() => {}).finally(() => setWinLossPatternsLoading(false));
      setAvgDealSizeTrendLoading(true);
      apiClient.getAvgDealSizeTrend(workspaceId, session.access_token).then(setAvgDealSizeTrend).catch(() => {}).finally(() => setAvgDealSizeTrendLoading(false));
      setFollowupGapsLoading(true);
      apiClient.getDealFollowupGaps(workspaceId, session.access_token).then(setFollowupGaps).catch(() => {}).finally(() => setFollowupGapsLoading(false));
      setValueAtRiskLoading(true);
      apiClient.getDealValueAtRisk(workspaceId, session.access_token).then(setValueAtRisk).catch(() => {}).finally(() => setValueAtRiskLoading(false));
      setNextBestActionsLoading(true);
      apiClient.getDealNextBestActions(workspaceId, session.access_token).then(setNextBestActions).catch(() => {}).finally(() => setNextBestActionsLoading(false));
      setCoachingDigestLoading(true);
      apiClient.getDealCoachingDigest(workspaceId, session.access_token).then(setCoachingDigest).catch(() => {}).finally(() => setCoachingDigestLoading(false));
      setQbrSummaryLoading(true);
      apiClient.getQbrSummary(workspaceId, session.access_token).then(setQbrSummary).catch(() => {}).finally(() => setQbrSummaryLoading(false));
      setConversionPathsLoading(true);
      apiClient.getDealConversionPaths(workspaceId, session.access_token).then(setConversionPaths).catch(() => {}).finally(() => setConversionPathsLoading(false));
      setPlaybookLoading(true);
      apiClient.getDealPlaybook(workspaceId, session.access_token).then(setPlaybook).catch(() => {}).finally(() => setPlaybookLoading(false));
      setBattleCardLoading(true);
      apiClient.getDealBattleCard(workspaceId, session.access_token).then(setBattleCard).catch(() => {}).finally(() => setBattleCardLoading(false));
      setRiskEscalationLoading(true);
      apiClient.getDealRiskEscalation(workspaceId, session.access_token).then(setRiskEscalation).catch(() => {}).finally(() => setRiskEscalationLoading(false));
      setMomentumLoading(true);
      apiClient.getDealMomentum(workspaceId, session.access_token).then(setMomentum).catch(() => {}).finally(() => setMomentumLoading(false));
    });
  }, []);

  const stats = useMemo(() => {
    const won = deals.filter((d) => d.stage === "closed_won");
    const lost = deals.filter((d) => d.stage === "closed_lost");
    const active = deals.filter((d) => d.stage !== "closed_won" && d.stage !== "closed_lost");
    const closed = won.length + lost.length;
    const winRate = closed > 0 ? Math.round((won.length / closed) * 100) : 0;
    const wonValue = won.reduce((s, d) => s + d.value, 0);
    const pipelineValue = active.reduce((s, d) => s + d.value, 0);
    const avgDealSize = won.length > 0 ? wonValue / won.length : 0;
    const stale = active.filter((d) => d.healthScore < 40).length;

    // Avg cycle time: days from deal creation to close (approximated as days since created)
    const now = new Date();
    const cycleTimes = won
      .map((d) => {
        if (!d.createdAt) return null;
        return Math.max(1, Math.round((now.getTime() - new Date(d.createdAt).getTime()) / 86400000));
      })
      .filter((v): v is number => v !== null);
    const avgCycleTime = cycleTimes.length > 0
      ? Math.round(cycleTimes.reduce((s, v) => s + v, 0) / cycleTimes.length)
      : null;

    const byStage = dealStageOrder.map((stage) => {
      const stageDeals = deals.filter((d) => d.stage === stage);
      return {
        name: stageConfig[stage].label,
        value: stageDeals.reduce((s, d) => s + d.value, 0),
        count: stageDeals.length,
        stage,
      };
    }).filter((s) => s.value > 0 || s.count > 0);

    const topDeals = [...won]
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);

    const healthBuckets = [
      { label: "Healthy (70-100)", count: active.filter((d) => d.healthScore >= 70).length, color: "#00C896" },
      { label: "At risk (40-69)",  count: active.filter((d) => d.healthScore >= 40 && d.healthScore < 70).length, color: "#FBBF24" },
      { label: "Critical (<40)",   count: active.filter((d) => d.healthScore < 40).length, color: "#F43F5E" },
    ];

    // Monthly revenue from closed_won deals (last 6 months) — reuses `now` from above
    const abbr = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const historyMonths = 6;
    const monthKeys: string[] = [];
    for (let i = historyMonths - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      monthKeys.push(`${d.getFullYear()}-${d.getMonth()}`);
    }
    const monthBuckets: Record<string, { month: string; actual: number }> = {};
    monthKeys.forEach((key) => {
      const [y, m] = key.split('-').map(Number);
      monthBuckets[key] = { month: abbr[m], actual: 0 };
    });
    won.forEach((d) => {
      const dt = new Date(d.createdAt ?? "");
      const key = `${dt.getFullYear()}-${dt.getMonth()}`;
      if (monthBuckets[key]) monthBuckets[key].actual += d.value;
    });
    const history = monthKeys.map((k) => monthBuckets[k]);

    // Linear regression over history to project 3 forecast months
    const n = history.length;
    const sumX = history.reduce((s, _, i) => s + i, 0);
    const sumY = history.reduce((s, h) => s + h.actual, 0);
    const sumXY = history.reduce((s, h, i) => s + i * h.actual, 0);
    const sumX2 = history.reduce((s, _, i) => s + i * i, 0);
    const denom = n * sumX2 - sumX * sumX;
    const slope = denom !== 0 ? (n * sumXY - sumX * sumY) / denom : 0;
    const intercept = (sumY - slope * sumX) / n;

    const forecastCount = 3;
    const revenueChart = [
      ...history.map((h, i) => ({
        month: h.month,
        actual: Math.round(h.actual),
        forecast: null as number | null,
        trend: Math.max(0, Math.round(intercept + slope * i)),
      })),
      ...Array.from({ length: forecastCount }, (_, i) => {
        const dt = new Date(now.getFullYear(), now.getMonth() + 1 + i, 1);
        return {
          month: abbr[dt.getMonth()],
          actual: null as number | null,
          forecast: Math.max(0, Math.round(intercept + slope * (n + i))),
          trend: null as number | null,
        };
      }),
    ];

    return { won, lost, active, winRate, wonValue, pipelineValue, avgDealSize, stale, byStage, topDeals, healthBuckets, revenueChart, avgCycleTime };
  }, [deals]);

  const regeneratePipelineHealth = () => {
    setPipelineHealthLoading(true);
    const doFetch = (workspaceId: string, token: string) => {
      apiClient.getPipelineHealthBriefing(workspaceId, token)
        .then(setPipelineHealth)
        .catch(() => {})
        .finally(() => setPipelineHealthLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setPipelineHealthLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setPipelineHealthLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateTeamPerf = () => {
    setTeamPerfLoading(true);
    const doFetch = (workspaceId: string, token: string) => {
      apiClient.getTeamPerformance(workspaceId, token)
        .then(setTeamPerf)
        .catch(() => {})
        .finally(() => setTeamPerfLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setTeamPerfLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setTeamPerfLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateCompetitiveLandscape = () => {
    setCompetitiveLandscapeLoading(true);
    const doFetch = (workspaceId: string, token: string) => {
      apiClient.getCompetitiveLandscape(workspaceId, token)
        .then(setCompetitiveLandscape)
        .catch(() => {})
        .finally(() => setCompetitiveLandscapeLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setCompetitiveLandscapeLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setCompetitiveLandscapeLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateCalibration = () => {
    setCalibrationLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getWinProbabilityCalibration(wid, tok)
        .then(setCalibrationData)
        .catch(() => {})
        .finally(() => setCalibrationLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setCalibrationLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setCalibrationLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateAgentPerfReport = () => {
    setAgentPerfReportLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getAgentPerformanceReport(wid, tok)
        .then(setAgentPerfReport)
        .catch(() => {})
        .finally(() => setAgentPerfReportLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setAgentPerfReportLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setAgentPerfReportLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateNegotiationReadiness = () => {
    setNegotiationReadinessLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealsNegotiationReadiness(wid, tok)
        .then(setNegotiationReadiness)
        .catch(() => {})
        .finally(() => setNegotiationReadinessLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setNegotiationReadinessLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setNegotiationReadinessLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateMsgSourceReliability = () => {
    setMsgSourceReliabilityLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getMessageSourceReliability(wid, tok)
        .then(setMsgSourceReliability)
        .catch(() => {})
        .finally(() => setMsgSourceReliabilityLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setMsgSourceReliabilityLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setMsgSourceReliabilityLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateStageTransitionAnalysis = () => {
    setStageTransitionLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getStageTransitionAnalysis(wid, tok)
        .then(setStageTransitionAnalysis)
        .catch(() => {})
        .finally(() => setStageTransitionLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setStageTransitionLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setStageTransitionLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateRevenueTrend = () => {
    setRevenueTrendLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getRevenueTrendAnalysis(wid, tok)
        .then(setRevenueTrend)
        .catch(() => {})
        .finally(() => setRevenueTrendLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setRevenueTrendLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setRevenueTrendLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateInactivityRisk = () => {
    setInactivityRiskLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getContactInactivityRisk(wid, tok)
        .then(setInactivityRisk)
        .catch(() => {})
        .finally(() => setInactivityRiskLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setInactivityRiskLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setInactivityRiskLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regeneratePipelineMomentum = () => {
    setPipelineMomentumLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealsPipelineMomentum(wid, tok)
        .then(setPipelineMomentum)
        .catch(() => {})
        .finally(() => setPipelineMomentumLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setPipelineMomentumLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setPipelineMomentumLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateDealAgeRisk = () => {
    setDealAgeRiskLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealAgeRisk(wid, tok)
        .then(setDealAgeRisk)
        .catch(() => {})
        .finally(() => setDealAgeRiskLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setDealAgeRiskLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setDealAgeRiskLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateTopPerformers = () => {
    setTopPerformersLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getTopPerformerDeals(wid, tok)
        .then(setTopPerformers)
        .catch(() => {})
        .finally(() => setTopPerformersLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setTopPerformersLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setTopPerformersLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateStageConcentration = () => {
    setStageConcentrationLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealStageConcentration(wid, tok)
        .then(setStageConcentration)
        .catch(() => {})
        .finally(() => setStageConcentrationLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setStageConcentrationLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setStageConcentrationLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateCloseRateByStage = () => {
    setCloseRateByStageLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealCloseRateByStage(wid, tok)
        .then(setCloseRateByStage)
        .catch(() => {})
        .finally(() => setCloseRateByStageLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setCloseRateByStageLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setCloseRateByStageLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regeneratePipelineChurn = () => {
    setPipelineChurnLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealPipelineChurn(wid, tok)
        .then(setPipelineChurn)
        .catch(() => {})
        .finally(() => setPipelineChurnLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setPipelineChurnLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setPipelineChurnLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateConversionQuality = () => {
    setConversionQualityLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealConversionQuality(wid, tok)
        .then(setConversionQuality)
        .catch(() => {})
        .finally(() => setConversionQualityLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setConversionQualityLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setConversionQualityLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateWinLossPatterns = () => {
    setWinLossPatternsLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealWinLossPatterns(wid, tok)
        .then(setWinLossPatterns)
        .catch(() => {})
        .finally(() => setWinLossPatternsLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setWinLossPatternsLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setWinLossPatternsLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateAvgDealSizeTrend = () => {
    setAvgDealSizeTrendLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getAvgDealSizeTrend(wid, tok)
        .then(setAvgDealSizeTrend)
        .catch(() => {})
        .finally(() => setAvgDealSizeTrendLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setAvgDealSizeTrendLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setAvgDealSizeTrendLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateFollowupGaps = () => {
    setFollowupGapsLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealFollowupGaps(wid, tok)
        .then(setFollowupGaps)
        .catch(() => {})
        .finally(() => setFollowupGapsLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setFollowupGapsLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setFollowupGapsLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateValueAtRisk = () => {
    setValueAtRiskLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealValueAtRisk(wid, tok)
        .then(setValueAtRisk)
        .catch(() => {})
        .finally(() => setValueAtRiskLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setValueAtRiskLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setValueAtRiskLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateCoachingDigest = () => {
    setCoachingDigestLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealCoachingDigest(wid, tok)
        .then(setCoachingDigest)
        .catch(() => {})
        .finally(() => setCoachingDigestLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setCoachingDigestLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setCoachingDigestLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateMomentum = () => {
    setMomentumLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealMomentum(wid, tok)
        .then(setMomentum)
        .catch(() => {})
        .finally(() => setMomentumLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setMomentumLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setMomentumLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateRiskEscalation = () => {
    setRiskEscalationLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealRiskEscalation(wid, tok)
        .then(setRiskEscalation)
        .catch(() => {})
        .finally(() => setRiskEscalationLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setRiskEscalationLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setRiskEscalationLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateBattleCard = () => {
    setBattleCardLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealBattleCard(wid, tok)
        .then(setBattleCard)
        .catch(() => {})
        .finally(() => setBattleCardLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setBattleCardLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setBattleCardLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regeneratePlaybook = () => {
    setPlaybookLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealPlaybook(wid, tok)
        .then(setPlaybook)
        .catch(() => {})
        .finally(() => setPlaybookLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setPlaybookLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setPlaybookLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateConversionPaths = () => {
    setConversionPathsLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealConversionPaths(wid, tok)
        .then(setConversionPaths)
        .catch(() => {})
        .finally(() => setConversionPathsLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setConversionPathsLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setConversionPathsLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateQbrSummary = () => {
    setQbrSummaryLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getQbrSummary(wid, tok)
        .then(setQbrSummary)
        .catch(() => {})
        .finally(() => setQbrSummaryLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setQbrSummaryLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setQbrSummaryLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const regenerateNextBestActions = () => {
    setNextBestActionsLoading(true);
    const doFetch = (wid: string, tok: string) => {
      apiClient.getDealNextBestActions(wid, tok)
        .then(setNextBestActions)
        .catch(() => {})
        .finally(() => setNextBestActionsLoading(false));
    };
    if (DEMO_MODE) {
      doFetch("demo-workspace-1", "demo-token");
    } else {
      const supabase = createBrowserClient();
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) { setNextBestActionsLoading(false); return; }
        const wid: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!wid) { setNextBestActionsLoading(false); return; }
        doFetch(wid, session.access_token);
      });
    }
  };

  const MOMENTUM_RATING_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
    accelerating: { label: "Accelerating", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
    steady:       { label: "Steady",       color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/20"  },
    stalling:     { label: "Stalling",     color: "text-amber-400",   bg: "bg-amber-500/10 border-amber-500/20"   },
    declining:    { label: "Declining",    color: "text-rose-400",    bg: "bg-rose-500/10 border-rose-500/20"     },
  };

  const RATING_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
    strong:   { label: "Strong",   color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
    healthy:  { label: "Healthy",  color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/20"  },
    at_risk:  { label: "At Risk",  color: "text-amber-400",   bg: "bg-amber-500/10 border-amber-500/20"   },
    critical: { label: "Critical", color: "text-rose-400",    bg: "bg-rose-500/10 border-rose-500/20"     },
  };

  const TREND_DIR_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
    accelerating: { label: "Accelerating", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
    growing:      { label: "Growing",      color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/20"  },
    stable:       { label: "Stable",       color: "text-zinc-400",    bg: "bg-zinc-500/10 border-zinc-500/20"      },
    declining:    { label: "Declining",    color: "text-rose-400",    bg: "bg-rose-500/10 border-rose-500/20"      },
  };

  const TEAM_PERF_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
    excellent:          { label: "Excellent",          color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
    good:               { label: "Good",               color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/20"  },
    needs_improvement:  { label: "Needs Improvement",  color: "text-amber-400",   bg: "bg-amber-500/10 border-amber-500/20"   },
    critical:           { label: "Critical",           color: "text-rose-400",    bg: "bg-rose-500/10 border-rose-500/20"     },
  };

  const BIAS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
    optimistic:      { label: "Optimistic",      color: "text-amber-400",   bg: "bg-amber-500/10 border-amber-500/20"   },
    pessimistic:     { label: "Pessimistic",     color: "text-sky-400",     bg: "bg-sky-500/10 border-sky-500/20"       },
    well_calibrated: { label: "Well Calibrated", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
  };

  if (loading) {
    return (
      <div className="flex flex-col gap-6 p-4 md:p-6">
        <Header title="Reports" subtitle="Pipeline analytics and win rate" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-24 rounded-xl bg-zinc-800/50 animate-pulse" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header title="Reports" subtitle={`${deals.length} total deals · win rate ${stats.winRate}%`} />

      {/* Pipeline Health AI Briefing */}
      <Card className="border-indigo-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            <span className="text-sm font-semibold text-zinc-100">Pipeline Health Briefing</span>
            {pipelineHealth && (
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${RATING_CONFIG[pipelineHealth.rating]?.bg} ${RATING_CONFIG[pipelineHealth.rating]?.color}`}>
                {RATING_CONFIG[pipelineHealth.rating]?.label}
                <span className="font-mono">{pipelineHealth.health_score}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regeneratePipelineHealth}
              disabled={pipelineHealthLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${pipelineHealthLoading ? "animate-spin" : ""}`} />
              {pipelineHealthLoading ? "Generating…" : "Regenerate"}
            </button>
            <button
              onClick={() => setPipelineHealthOpen((o) => !o)}
              className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              {pipelineHealthOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {pipelineHealthOpen && (
          <div className="mt-4">
            {pipelineHealthLoading && !pipelineHealth && (
              <div className="space-y-2">
                <div className="h-4 w-full rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-4/5 rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-3/5 rounded bg-zinc-800 animate-pulse" />
              </div>
            )}
            {pipelineHealth && (
              <div className={`transition-opacity ${pipelineHealthLoading ? "opacity-40" : "opacity-100"}`}>
                <p className="text-sm text-zinc-300 leading-relaxed mb-4">{pipelineHealth.briefing}</p>
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Top Priorities</p>
                  {pipelineHealth.priorities.map((p, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500/15 text-xs font-bold text-indigo-400">{i + 1}</span>
                      <p className="text-sm text-zinc-300">{p}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs text-zinc-600">
                  Generated {new Date(pipelineHealth.generated_at).toLocaleString()} · Claude Haiku
                </p>
              </div>
            )}
            {!pipelineHealth && !pipelineHealthLoading && (
              <p className="text-sm text-zinc-500">Click Regenerate to generate a pipeline health briefing.</p>
            )}
          </div>
        )}
      </Card>

      {/* Win Probability Calibration AI Card */}
      <Card className="border-sky-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-sky-400" />
            <span className="text-sm font-semibold text-zinc-100">Win Probability Calibration</span>
            {calibrationData && calibrationData.calibration_score !== null && (
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${BIAS_CONFIG[calibrationData.overall_bias]?.bg} ${BIAS_CONFIG[calibrationData.overall_bias]?.color}`}>
                {BIAS_CONFIG[calibrationData.overall_bias]?.label}
                <span className="font-mono">{calibrationData.calibration_score}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateCalibration}
              disabled={calibrationLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${calibrationLoading ? "animate-spin" : ""}`} />
              {calibrationLoading ? "Generating…" : "Regenerate"}
            </button>
            <button
              onClick={() => setCalibrationOpen((o) => !o)}
              className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              {calibrationOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {calibrationOpen && (
          <div className="mt-4">
            {calibrationLoading && !calibrationData && (
              <div className="space-y-2">
                <div className="h-4 w-full rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-4/5 rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-3/5 rounded bg-zinc-800 animate-pulse" />
              </div>
            )}
            {calibrationData && (
              <div className={`transition-opacity ${calibrationLoading ? "opacity-40" : "opacity-100"}`}>
                <div className="flex items-start gap-6 mb-4">
                  {calibrationData.calibration_score !== null && (
                    <div className="flex-shrink-0 flex flex-col items-center gap-1">
                      <svg viewBox="0 0 64 64" className="h-16 w-16">
                        <circle cx="32" cy="32" r="26" fill="none" stroke="#27272a" strokeWidth="6" />
                        <circle
                          cx="32" cy="32" r="26" fill="none"
                          stroke={calibrationData.calibration_score >= 80 ? "#34d399" : calibrationData.calibration_score >= 60 ? "#f59e0b" : "#f87171"}
                          strokeWidth="6"
                          strokeDasharray={`${(calibrationData.calibration_score / 100) * 163.4} 163.4`}
                          strokeLinecap="round"
                          transform="rotate(-90 32 32)"
                        />
                        <text x="32" y="36" textAnchor="middle" fontSize="14" fontWeight="bold" fill="#f4f4f5">
                          {calibrationData.calibration_score}
                        </text>
                      </svg>
                      <span className="text-xs text-zinc-500">Cal. Score</span>
                    </div>
                  )}
                  <p className="text-sm text-zinc-300 leading-relaxed">{calibrationData.narrative}</p>
                </div>
                <div className="mb-4 h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={calibrationData.calibration_buckets} barGap={2}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="bucket_label" tick={{ fontSize: 10, fill: "#71717a" }} />
                      <YAxis tick={{ fontSize: 10, fill: "#71717a" }} domain={[0, 100]} unit="%" />
                      <Tooltip
                        contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8 }}
                        labelStyle={{ color: "#a1a1aa" }}
                        itemStyle={{ color: "#f4f4f5" }}
                        formatter={(value) => `${value}%`}
                      />
                      <Bar dataKey="predicted_avg" name="Predicted" fill="#38bdf8" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="actual_win_rate" name="Actual" fill="#818cf8" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Recommendations</p>
                  {calibrationData.recommendations.map((rec, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                      <p className="text-sm text-zinc-300">{rec}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs text-zinc-600">
                  Generated {new Date(calibrationData.generated_at).toLocaleString()} · Claude Haiku
                </p>
              </div>
            )}
            {!calibrationData && !calibrationLoading && (
              <p className="text-sm text-zinc-500">Click Regenerate to generate a win probability calibration report.</p>
            )}
          </div>
        )}
      </Card>

      {/* Agent Performance Report AI Card */}
      <Card className="border-violet-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-violet-400" />
            <span className="text-sm font-semibold text-zinc-100">Agent Performance Report</span>
            {agentPerfReport && (
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${
                agentPerfReport.overall_success_rate >= 80
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : agentPerfReport.overall_success_rate >= 60
                  ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
                  : "bg-rose-500/10 border-rose-500/20 text-rose-400"
              }`}>
                {agentPerfReport.overall_success_rate}% success
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateAgentPerfReport}
              disabled={agentPerfReportLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${agentPerfReportLoading ? "animate-spin" : ""}`} />
              {agentPerfReportLoading ? "Generating…" : "Regenerate"}
            </button>
            <button
              onClick={() => setAgentPerfReportOpen((o) => !o)}
              className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              {agentPerfReportOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {agentPerfReportOpen && (
          <div className="mt-4">
            {agentPerfReportLoading && !agentPerfReport && (
              <div className="space-y-2">
                <div className="h-4 w-full rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-4/5 rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-3/5 rounded bg-zinc-800 animate-pulse" />
              </div>
            )}
            {agentPerfReport && (
              <div className={`transition-opacity ${agentPerfReportLoading ? "opacity-40" : "opacity-100"}`}>
                <p className="text-sm text-zinc-300 leading-relaxed mb-4">{agentPerfReport.narrative}</p>
                {agentPerfReport.agent_stats.length > 0 && (
                  <div className="mb-4 space-y-2">
                    <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Per-Agent Stats (Last 30 Days)</p>
                    {agentPerfReport.agent_stats.map((a) => (
                      <div key={a.agent_name} className="flex items-center gap-3">
                        <span className="w-36 truncate text-xs text-zinc-300">{a.agent_name}</span>
                        <div className="flex-1 flex items-center gap-2">
                          <div className="relative flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                            <div
                              className="absolute inset-y-0 left-0 rounded-full bg-emerald-500"
                              style={{ width: `${a.success_rate}%` }}
                            />
                            {a.failure_count > 0 && (
                              <div
                                className="absolute inset-y-0 rounded-full bg-rose-500"
                                style={{ left: `${a.success_rate}%`, width: `${100 - a.success_rate}%` }}
                              />
                            )}
                          </div>
                          <span className="w-12 text-right text-[10px] font-mono text-zinc-400">{a.success_rate}%</span>
                        </div>
                        <span className="w-14 text-right text-[10px] text-zinc-500">{a.run_count} runs</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Recommendations</p>
                  {agentPerfReport.recommendations.map((rec, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                      <p className="text-sm text-zinc-300">{rec}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs text-zinc-600">
                  Generated {new Date(agentPerfReport.generated_at).toLocaleString()} · Claude Haiku
                </p>
              </div>
            )}
            {!agentPerfReport && !agentPerfReportLoading && (
              <p className="text-sm text-zinc-500">Click Regenerate to generate an agent performance report.</p>
            )}
          </div>
        )}
      </Card>

      {/* Team Performance AI Card */}
      <Card className="border-teal-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-teal-400" />
            <span className="text-sm font-semibold text-zinc-100">Team Performance</span>
            {teamPerf && (
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${TEAM_PERF_CONFIG[teamPerf.performance_rating]?.bg} ${TEAM_PERF_CONFIG[teamPerf.performance_rating]?.color}`}>
                {TEAM_PERF_CONFIG[teamPerf.performance_rating]?.label}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateTeamPerf}
              disabled={teamPerfLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${teamPerfLoading ? "animate-spin" : ""}`} />
              {teamPerfLoading ? "Generating…" : "Regenerate"}
            </button>
            <button
              onClick={() => setTeamPerfOpen((o) => !o)}
              className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              {teamPerfOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {teamPerfOpen && (
          <div className="mt-4">
            {teamPerfLoading && !teamPerf && (
              <div className="space-y-2">
                <div className="h-4 w-full rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-4/5 rounded bg-zinc-800 animate-pulse" />
                <div className="h-4 w-3/5 rounded bg-zinc-800 animate-pulse" />
              </div>
            )}
            {teamPerf && (
              <div className={`transition-opacity ${teamPerfLoading ? "opacity-40" : "opacity-100"}`}>
                {/* Summary */}
                <p className="text-sm text-zinc-300 leading-relaxed mb-4">{teamPerf.summary_sentence}</p>

                {/* Metrics mini-grid */}
                <div className="grid grid-cols-5 gap-2 mb-4">
                  {[
                    { label: "Agent Runs", value: teamPerf.metrics.agent_runs, color: "text-teal-300" },
                    { label: "Task Rate", value: `${teamPerf.metrics.task_completion_rate}%`, color: "text-indigo-300" },
                    { label: "Messages", value: teamPerf.metrics.messages_processed, color: "text-violet-300" },
                    { label: "Deals Moved", value: teamPerf.metrics.deals_moved, color: "text-amber-300" },
                    { label: "Active Contacts", value: teamPerf.metrics.active_contacts, color: "text-emerald-300" },
                  ].map((m) => (
                    <div key={m.label} className="rounded-lg bg-zinc-800/50 border border-zinc-700/50 p-2 text-center">
                      <p className={`text-lg font-mono font-bold ${m.color}`}>{m.value}</p>
                      <p className="text-[10px] text-zinc-500 leading-tight mt-0.5">{m.label}</p>
                    </div>
                  ))}
                </div>

                {/* Highlights + Areas */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Highlights</p>
                    <div className="space-y-1.5">
                      {teamPerf.highlights.map((h, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400" />
                          <p className="text-xs text-zinc-300">{h}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Areas to Improve</p>
                    <div className="space-y-1.5">
                      {teamPerf.areas_for_improvement.map((a, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-400" />
                          <p className="text-xs text-zinc-300">{a}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <p className="mt-3 text-xs text-zinc-600">
                  Generated {new Date(teamPerf.generated_at).toLocaleString()} · Claude Haiku · Last 30 days
                </p>
              </div>
            )}
            {!teamPerf && !teamPerfLoading && (
              <p className="text-sm text-zinc-500">Click Regenerate to generate a team performance summary.</p>
            )}
          </div>
        )}
      </Card>

      {/* Competitive Landscape AI Card */}
      <Card className="gap-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Trophy className="h-4 w-4 text-amber-400" />
            <span className="text-sm font-semibold text-zinc-100">Competitive Landscape</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateCompetitiveLandscape}
              disabled={competitiveLandscapeLoading}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${competitiveLandscapeLoading ? "animate-spin" : ""}`} />
              {competitiveLandscapeLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setCompetitiveLandscapeOpen((o) => !o)} className="text-zinc-500 hover:text-zinc-300 transition-colors">
              {competitiveLandscapeOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {competitiveLandscapeOpen && (
          <div className="p-4 space-y-4">
            {competitiveLandscapeLoading && !competitiveLandscape && (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => <div key={i} className="h-10 rounded-lg bg-zinc-800 animate-pulse" />)}
              </div>
            )}
            {competitiveLandscape && (
              <div className={`space-y-4 transition-opacity ${competitiveLandscapeLoading ? "opacity-40" : "opacity-100"}`}>
                <p className="text-sm text-zinc-300 leading-relaxed">{competitiveLandscape.competitive_summary}</p>
                {competitiveLandscape.top_competitors.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Top Competitors</p>
                    {competitiveLandscape.top_competitors.map((c) => {
                      const threatColor = c.threat_level === 'high' ? 'text-rose-400 bg-rose-500/10 border-rose-500/20' : c.threat_level === 'medium' ? 'text-amber-400 bg-amber-500/10 border-amber-500/20' : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
                      return (
                        <div key={c.name} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-semibold text-zinc-100">{c.name}</span>
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${threatColor}`}>{c.threat_level}</span>
                          </div>
                          <p className="text-xs text-zinc-400">{c.deal_count} deal{c.deal_count !== 1 ? 's' : ''} · stages: {c.stages_present.join(', ')}</p>
                          <p className="text-xs text-zinc-500 italic">{c.positioning_note}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Win Strategies</p>
                  <ol className="space-y-1.5">
                    {competitiveLandscape.win_strategies.map((s, i) => (
                      <li key={i} className="flex gap-2 text-sm text-zinc-300">
                        <span className="flex-shrink-0 font-mono text-xs text-amber-400 mt-0.5">{i + 1}.</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            )}
            {!competitiveLandscape && !competitiveLandscapeLoading && (
              <p className="text-sm text-zinc-500">Click Regenerate to generate a competitive landscape analysis.</p>
            )}
          </div>
        )}
      </Card>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Card compact accent="signal" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#00C896]/10 border border-[#00C896]/20 flex-shrink-0">
            <Trophy className="h-4 w-4 text-[#00C896]" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-[#00C896]">{stats.winRate}%</p>
            <p className="text-xs text-zinc-500">Win Rate</p>
          </div>
        </Card>
        <Card compact accent="violet" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex-shrink-0">
            <DollarSign className="h-4 w-4 text-indigo-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-zinc-100">{formatCurrency(stats.wonValue)}</p>
            <p className="text-xs text-zinc-500">Closed Won</p>
          </div>
        </Card>
        <Card compact className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <TrendingUp className="h-4 w-4 text-amber-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-amber-400">{formatCurrency(stats.pipelineValue)}</p>
            <p className="text-xs text-zinc-500">Pipeline Value</p>
          </div>
        </Card>
        <Card compact className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-700/50 border border-zinc-700 flex-shrink-0">
            <Target className="h-4 w-4 text-zinc-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-zinc-100">{formatCurrency(stats.avgDealSize)}</p>
            <p className="text-xs text-zinc-500">Avg Deal Size</p>
          </div>
        </Card>
        <Card compact className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10 border border-violet-500/20 flex-shrink-0">
            <Clock className="h-4 w-4 text-violet-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-zinc-100">
              {stats.avgCycleTime !== null ? `${stats.avgCycleTime}d` : "—"}
            </p>
            <p className="text-xs text-zinc-500">Avg Cycle Time</p>
          </div>
        </Card>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Pipeline by stage bar chart */}
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Pipeline Value by Stage</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Active + closed deals</p>
            </div>
            <Badge variant="indigo">{deals.length} deals</Badge>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.byStage} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v / 1000}K`} width={40} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" name="Value" radius={[4, 4, 0, 0]}>
                  {stats.byStage.map((entry) => (
                    <Cell key={entry.stage} fill={STAGE_COLORS[entry.stage] ?? "#52525B"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Deal health donut */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-zinc-100">Deal Health</p>
            {stats.stale > 0 && (
              <Badge variant="rose" dot size="sm">{stats.stale} critical</Badge>
            )}
          </div>
          {stats.active.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-xs text-zinc-600">No active deals</div>
          ) : (
            <>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={stats.healthBuckets.filter((b) => b.count > 0)}
                      dataKey="count"
                      nameKey="label"
                      cx="50%"
                      cy="50%"
                      innerRadius={38}
                      outerRadius={58}
                      paddingAngle={3}
                    >
                      {stats.healthBuckets.filter((b) => b.count > 0).map((b) => (
                        <Cell key={b.label} fill={b.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => [`${v} deals`, ""]} contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="space-y-1.5 mt-2">
                {stats.healthBuckets.map((b) => (
                  <div key={b.label} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: b.color }} />
                      <span className="text-zinc-400">{b.label}</span>
                    </div>
                    <span className="font-mono text-zinc-200">{b.count}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Win/Loss summary + Top deals */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Win vs Loss */}
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <BarChart2 className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">Win / Loss Summary</p>
          </div>
          <div className="space-y-3">
            {[
              { label: "Won", count: stats.won.length, value: stats.wonValue, color: "bg-[#00C896]", text: "text-[#00C896]" },
              { label: "Lost", count: stats.lost.length, value: stats.lost.reduce((s, d) => s + d.value, 0), color: "bg-rose-500", text: "text-rose-400" },
              { label: "Active", count: stats.active.length, value: stats.pipelineValue, color: "bg-indigo-500", text: "text-indigo-400" },
            ].map(({ label, count, value, color, text }) => (
              <div key={label} className="flex items-center gap-3">
                <div className="w-16 flex-shrink-0">
                  <span className={cn("text-xs font-medium", text)}>{label}</span>
                </div>
                <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", color)}
                    style={{ width: deals.length > 0 ? `${(count / deals.length) * 100}%` : "0%" }}
                  />
                </div>
                <div className="w-24 text-right flex-shrink-0">
                  <span className="text-xs font-mono text-zinc-400">{count} · {formatCurrency(value)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Top closed-won deals */}
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Trophy className="h-4 w-4 text-[#00C896]" />
            <p className="text-sm font-semibold text-zinc-100">Top Closed Deals</p>
          </div>
          {stats.topDeals.length === 0 ? (
            <div className="flex h-24 items-center justify-center text-xs text-zinc-600">No closed deals yet</div>
          ) : (
            <div className="space-y-2">
              {stats.topDeals.map((deal, i) => (
                <div key={deal.id} className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-zinc-800/40">
                  <span className="text-[10px] font-mono text-zinc-600 w-4 flex-shrink-0">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-200 truncate">{deal.title}</p>
                    <p className="text-[10px] text-zinc-600 truncate">{deal.company}</p>
                  </div>
                  <span className="text-xs font-mono font-bold text-[#00C896] flex-shrink-0">{formatCurrency(deal.value)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Revenue forecast chart */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-semibold text-zinc-100">Revenue Trend &amp; Forecast</p>
            <p className="text-xs text-zinc-500 mt-0.5 font-mono">6-month history · 3-month projection (linear trend)</p>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-4 rounded-sm bg-[#6366F1]" /> Actual
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-[#00C896]" /> Forecast
            </span>
          </div>
        </div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={stats.revenueChart} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v / 1000}K`} width={40} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="actual" name="Actual" fill="#6366F1" radius={[4, 4, 0, 0]} maxBarSize={40} />
              <Bar dataKey="forecast" name="Forecast" fill="#00C896" radius={[4, 4, 0, 0]} maxBarSize={40} opacity={0.35} />
              <Line dataKey="trend" name="Trend" stroke="#00C896" strokeWidth={1.5} strokeDasharray="5 3" dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Pipeline velocity — avg days in stage */}
      {velocityData.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Pipeline Velocity</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Avg days each deal has spent in current stage</p>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500">
              <Timer className="h-3.5 w-3.5" />
              <span>{velocityData.reduce((s, v) => s + v.deal_count, 0)} deals measured</span>
            </div>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={velocityData} layout="vertical" margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: "#71717A", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `${v}d`}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  tick={{ fill: "#71717A", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={80}
                />
                <Tooltip content={<VelocityTooltip />} />
                <Bar dataKey="avg_days" name="Avg days" radius={[0, 4, 4, 0]} maxBarSize={18} label={{ position: "right", fill: "#71717A", fontSize: 10, formatter: (v) => `${v}d` }}>
                  {velocityData.map((entry) => (
                    <Cell key={entry.stage} fill={STAGE_COLORS[entry.stage] ?? "#52525B"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Stage conversion funnel */}
      {funnelData.length > 0 && (() => {
        const maxCount = Math.max(...funnelData.map((r) => r.deal_count), 1);
        return (
          <Card>
            <div className="flex items-center justify-between mb-5">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Stage Conversion Funnel</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Deal count per stage · % converted from previous</p>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                <Filter className="h-3.5 w-3.5" />
                <span>{funnelData.reduce((s, r) => s + r.deal_count, 0)} total deals</span>
              </div>
            </div>
            <div className="space-y-0.5">
              {funnelData.map((row, i) => (
                <div key={row.stage}>
                  {i > 0 && (
                    <div className="flex items-center gap-2 pl-28 py-1">
                      <span className="text-[10px] font-mono text-zinc-600">
                        {row.conversion_rate !== null && row.conversion_rate > 0
                          ? `↓ ${row.conversion_rate.toFixed(1)}% converted`
                          : "↓ 0% converted"}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    <div className="w-24 flex-shrink-0 text-right">
                      <span className="text-[11px] text-zinc-400">{row.label}</span>
                    </div>
                    <div className="flex-1 h-7 bg-zinc-800/40 rounded-md overflow-hidden">
                      <div
                        className="h-full rounded-md flex items-center pl-2 transition-all duration-500"
                        style={{
                          width: row.deal_count > 0 ? `${Math.max(4, (row.deal_count / maxCount) * 100)}%` : "3px",
                          background: STAGE_COLORS[row.stage] ?? "#52525B",
                          opacity: row.deal_count === 0 ? 0.25 : 1,
                        }}
                      >
                        {row.deal_count > 0 && (
                          <span className="text-[10px] font-mono font-bold text-white/80 select-none">
                            {row.deal_count}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="w-8 flex-shrink-0">
                      <span className="text-xs font-mono text-zinc-500">{row.deal_count}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        );
      })()}

      {/* Win/Loss Reason Breakdown */}
      {outcomeReasons.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Win / Loss Reasons</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Closed deal count by tagged outcome reason</p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-[#00C896]">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#00C896]" /> Won
              </span>
              <span className="flex items-center gap-1.5 text-[#F43F5E]">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#F43F5E]" /> Lost
              </span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={outcomeReasons} margin={{ top: 0, right: 8, left: -24, bottom: 0 }} barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-2">{label}</p>
                      {payload.map((p) => (
                        <div key={p.name} className="flex items-center gap-2" style={{ color: p.color }}>
                          <span>{p.name === "won" ? "Won" : "Lost"}:</span>
                          <span className="font-mono font-bold">{p.value}</span>
                        </div>
                      ))}
                    </div>
                  );
                }}
              />
              <Bar dataKey="won" name="won" fill="#00C896" radius={[4, 4, 0, 0]} maxBarSize={28} />
              <Bar dataKey="lost" name="lost" fill="#F43F5E" radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Agent run success/failure chart */}
      {agentRunStats.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Agent Run Success Rate</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Last 30 days · runs per agent</p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Success
              </span>
              <span className="flex items-center gap-1.5 text-rose-400">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-rose-500" /> Failure
              </span>
              <Bot className="h-3.5 w-3.5 text-zinc-500" />
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={agentRunStats.map((r) => ({
                ...r,
                label: r.agent_name.replace(" ", "\n"),
              }))}
              margin={{ top: 0, right: 8, left: -24, bottom: 0 }}
              barCategoryGap="30%"
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis
                dataKey="agent_name"
                tick={{ fill: "#71717A", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: string) => v.split(" ").slice(0, 2).join(" ")}
              />
              <YAxis tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-2">{label}</p>
                      {payload.map((p) => (
                        <div key={p.name} className="flex items-center gap-2" style={{ color: p.color }}>
                          <span className="capitalize">{p.name}:</span>
                          <span className="font-mono font-bold">{p.value}</span>
                        </div>
                      ))}
                      {payload.length === 2 && (
                        <div className="mt-1.5 pt-1.5 border-t border-zinc-700 text-zinc-500">
                          Total: {(payload[0].value as number) + (payload[1].value as number)} runs
                        </div>
                      )}
                    </div>
                  );
                }}
              />
              <Bar dataKey="success" name="success" fill="#10B981" radius={[4, 4, 0, 0]} maxBarSize={28} />
              <Bar dataKey="failure" name="failure" fill="#F43F5E" radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Pipeline health score distribution */}
      {healthDist.some((b) => b.count > 0) && (() => {
        const totalDeals = healthDist.reduce((s, b) => s + b.count, 0);
        const donutData = healthDist.filter((b) => b.count > 0);
        return (
          <Card>
            <div className="flex items-center justify-between mb-5">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Pipeline Health Distribution</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Open deals grouped by health score bucket</p>
              </div>
              <Badge variant="indigo">{totalDeals} open deal{totalDeals !== 1 ? "s" : ""}</Badge>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-6">
              <div className="h-44 w-44 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={donutData}
                      dataKey="count"
                      cx="50%"
                      cy="50%"
                      innerRadius={48}
                      outerRadius={68}
                      paddingAngle={3}
                    >
                      {donutData.map((b) => (
                        <Cell key={b.bucket} fill={HEALTH_DIST_CONFIG[b.bucket]?.color ?? "#52525B"} />
                      ))}
                    </Pie>
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const b = payload[0].payload as { bucket: string; count: number; total_value: number };
                        return (
                          <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                            <p className="font-mono text-zinc-400 mb-1">{HEALTH_DIST_CONFIG[b.bucket]?.label ?? b.bucket}</p>
                            <p className="text-zinc-200">{b.count} deal{b.count !== 1 ? "s" : ""}</p>
                            <p className="text-zinc-400">{formatCurrency(b.total_value)}</p>
                          </div>
                        );
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 w-full space-y-3">
                {healthDist.map((b) => (
                  <div key={b.bucket} className="flex items-center gap-3">
                    <span className="h-2.5 w-2.5 rounded-full flex-shrink-0" style={{ background: HEALTH_DIST_CONFIG[b.bucket]?.color ?? "#52525B" }} />
                    <span className="text-xs text-zinc-400 w-32 flex-shrink-0">{HEALTH_DIST_CONFIG[b.bucket]?.label ?? b.bucket}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: totalDeals > 0 ? `${(b.count / totalDeals) * 100}%` : "0%",
                          background: HEALTH_DIST_CONFIG[b.bucket]?.color ?? "#52525B",
                        }}
                      />
                    </div>
                    <span className="text-xs font-mono text-zinc-300 w-14 text-right tabular-nums">{b.count} deal{b.count !== 1 ? "s" : ""}</span>
                    <span className="text-xs font-mono text-zinc-500 w-24 text-right tabular-nums">{formatCurrency(b.total_value)}</span>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        );
      })()}

      {/* Deals by assigned agent */}
      {dealsByAgent.length > 0 && (() => {
        const maxCount = Math.max(...dealsByAgent.map((b) => b.count), 1);
        return (
          <Card>
            <div className="flex items-center justify-between mb-5">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Open Deals by Agent</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Active pipeline per assigned agent</p>
              </div>
              <Badge variant="indigo">{dealsByAgent.reduce((s, b) => s + b.count, 0)} deals</Badge>
            </div>
            <div className="space-y-3">
              {dealsByAgent.map((b) => (
                <div key={b.agent_name} className="flex items-center gap-3">
                  <span className="text-xs text-zinc-400 w-24 flex-shrink-0 truncate">{b.agent_name}</span>
                  <div className="flex-1 h-6 bg-zinc-800/40 rounded-md overflow-hidden">
                    <div
                      className="h-full rounded-md flex items-center pl-2 transition-all duration-500"
                      style={{
                        width: `${Math.max(4, (b.count / maxCount) * 100)}%`,
                        background: b.agent_name === "Unassigned" ? "#52525B" : "#6366F1",
                      }}
                    >
                      <span className="text-[10px] font-mono font-bold text-white/80 select-none">{b.count}</span>
                    </div>
                  </div>
                  <span className="text-xs font-mono text-zinc-400 w-24 text-right flex-shrink-0">{formatCurrency(b.total_value)}</span>
                </div>
              ))}
            </div>
          </Card>
        );
      })()}

      {/* Expected revenue forecast by close month */}
      {revenueForecast.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Expected Revenue by Close Month</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Open deals weighted by win probability</p>
            </div>
            <Badge variant="indigo">{revenueForecast.reduce((s, r) => s + r.deal_count, 0)} deals</Badge>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={revenueForecast} margin={{ top: 0, right: 8, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const row = payload[0].payload as { month: string; expected_revenue: number; deal_count: number; total_value: number };
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-2">{label}</p>
                      <p className="text-emerald-400 font-mono font-bold">{formatCurrency(row.expected_revenue)} expected</p>
                      <p className="text-zinc-400">{formatCurrency(row.total_value)} total pipeline</p>
                      <p className="text-zinc-500 mt-1">{row.deal_count} deal{row.deal_count !== 1 ? "s" : ""}</p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="expected_revenue" name="Expected Revenue" fill="#00C896" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Deal aging by stage */}
      {stageAging.length > 0 && (() => {
        const AGING_COLOR = (days: number) =>
          days >= 30 ? "#F43F5E" : days >= 14 ? "#FBBF24" : "#00C896";
        const stages = Array.from(new Set(stageAging.map((d) => d.stage)));
        return (
          <Card>
            <div className="flex items-center justify-between mb-5">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Deal Aging by Stage</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Days each open deal has spent in its current stage</p>
              </div>
              <div className="flex items-center gap-3 text-[10px] text-zinc-500">
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-[#00C896]" /> &lt;14d</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" /> 14–30d</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-rose-500" /> 30d+</span>
              </div>
            </div>
            <div className="space-y-4">
              {stages.map((stage) => {
                const deals = stageAging.filter((d) => d.stage === stage);
                return (
                  <div key={stage}>
                    <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-wide mb-1.5">
                      {stageConfig[stage as keyof typeof stageConfig]?.label ?? stage} · {deals.length}
                    </p>
                    <div className="space-y-1">
                      {deals.map((d) => (
                        <div key={d.id} className="flex items-center gap-3 rounded-lg px-3 py-2 bg-zinc-800/30">
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-zinc-200 truncate">{d.title ?? "Untitled"}</p>
                            <p className="text-[10px] text-zinc-600 truncate">{d.company ?? "—"} · {formatCurrency(d.value)}</p>
                          </div>
                          <span
                            className="shrink-0 rounded-md px-2 py-0.5 text-[11px] font-mono tabular-nums font-bold"
                            style={{ color: AGING_COLOR(d.days_in_stage), background: `${AGING_COLOR(d.days_in_stage)}18` }}
                          >
                            {d.days_in_stage}d
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        );
      })()}

      {/* Win probability by stage */}
      {winProbByStage.some((b) => b.deal_count > 0) && (
        <Card>
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Win Probability by Stage</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Average ML win probability for open deals per stage</p>
            </div>
            <Badge variant="indigo">{winProbByStage.reduce((s, b) => s + b.deal_count, 0)} deals</Badge>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={winProbByStage.filter((b) => b.deal_count > 0).map((b) => ({
                ...b,
                label: stageConfig[b.stage as keyof typeof stageConfig]?.label ?? b.stage,
              }))}
              margin={{ top: 4, right: 8, left: -10, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const b = payload[0].payload as { avg_probability: number; deal_count: number; total_value: number };
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-2">{label}</p>
                      <p className="text-violet-400 font-mono font-bold">{b.avg_probability}% avg win prob</p>
                      <p className="text-zinc-400">{b.deal_count} deal{b.deal_count !== 1 ? "s" : ""}</p>
                      <p className="text-zinc-500">{formatCurrency(b.total_value)} pipeline</p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="avg_probability" name="Avg Win Probability" radius={[4, 4, 0, 0]} maxBarSize={48}>
                {winProbByStage.filter((b) => b.deal_count > 0).map((b) => (
                  <Cell key={b.stage} fill={STAGE_COLORS[b.stage] ?? "#52525B"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Contact pipeline contribution */}
      {pipelineContribution.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Contact Pipeline Contribution</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Top contacts by open pipeline value</p>
            </div>
            <Badge variant="indigo">{pipelineContribution.length} contacts</Badge>
          </div>
          <div className="space-y-1">
            {pipelineContribution.slice(0, 8).map((c) => (
              <div key={c.contact_id} className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-zinc-800/30">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-zinc-200 truncate">{c.name ?? c.email ?? "Unknown"}</p>
                  <p className="text-[10px] text-zinc-600 truncate">{c.company ?? "—"} · {c.deal_count} deal{c.deal_count !== 1 ? "s" : ""} · {c.win_rate.toFixed(0)}% win rate</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-xs font-mono font-bold text-indigo-400">{formatCurrency(c.pipeline_value)}</p>
                  {c.closed_won_value > 0 && (
                    <p className="text-[10px] font-mono text-[#00C896]">{formatCurrency(c.closed_won_value)} won</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Pipeline concentration risk */}
      {concentrationRisk && concentrationRisk.total_pipeline > 0 && (() => {
        const RISK_CONFIG = {
          low:    { label: "Low",    color: "#00C896", bg: "#00C89618" },
          medium: { label: "Medium", color: "#FBBF24", bg: "#FBBF2418" },
          high:   { label: "High",   color: "#F43F5E", bg: "#F43F5E18" },
        };
        const cfg = RISK_CONFIG[concentrationRisk.risk_level];
        return (
          <Card>
            <div className="flex items-center justify-between mb-5">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Pipeline Concentration Risk</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Top 3 deals · {concentrationRisk.top3_pct}% of {formatCurrency(concentrationRisk.total_pipeline)} pipeline</p>
              </div>
              <span className="rounded-md px-2.5 py-1 text-xs font-bold" style={{ color: cfg.color, background: cfg.bg }}>
                {cfg.label} risk
              </span>
            </div>
            <div className="space-y-2">
              {concentrationRisk.top_deals.map((d) => (
                <div key={d.id} className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-xs text-zinc-300 truncate">{d.title ?? "Untitled"} · {d.company ?? "—"}</span>
                      <span className="text-xs font-mono text-zinc-400 flex-shrink-0 ml-2">{d.pct_of_pipeline.toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${d.pct_of_pipeline}%`, background: STAGE_COLORS[d.stage] ?? "#52525B" }}
                      />
                    </div>
                  </div>
                  <span className="text-xs font-mono font-bold text-zinc-200 flex-shrink-0 w-20 text-right">{formatCurrency(d.value)}</span>
                </div>
              ))}
            </div>
          </Card>
        );
      })()}

      {/* Close-date slippage */}
      {slippedDeals.length > 0 && (
        <Card className="border-amber-500/20 space-y-3">
          <div className="flex items-center gap-2">
            <CalendarOff className="h-4 w-4 text-amber-400 flex-shrink-0" />
            <p className="text-sm font-semibold text-zinc-100">
              {slippedDeals.length} deal{slippedDeals.length !== 1 ? "s" : ""} past close date
            </p>
          </div>
          <div className="space-y-1.5">
            {slippedDeals.map((d) => (
              <div key={d.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-zinc-200 truncate">{d.title ?? "Untitled"}</p>
                  <p className="text-[11px] text-zinc-500 truncate">{d.company ?? "—"} · {stageConfig[d.stage as keyof typeof stageConfig]?.label ?? d.stage}</p>
                </div>
                <span className="shrink-0 text-xs font-mono text-zinc-400">{formatCurrency(d.value)}</span>
                <span className="shrink-0 rounded-md bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-[11px] font-mono text-amber-400 tabular-nums">
                  {d.days_overdue}d overdue
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Close Date Accuracy — Phase 12z */}
      {closeDateAccuracy.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <CalendarOff className="h-4 w-4 text-zinc-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Close Date Accuracy</h3>
            <span className="ml-auto text-xs text-zinc-500">{closeDateAccuracy.length} closed deal{closeDateAccuracy.length !== 1 ? "s" : ""}</span>
          </div>
          <div className="space-y-2">
            {closeDateAccuracy.slice(0, 8).map((d) => {
              const isLate = d.outcome === "late";
              const isEarly = d.outcome === "early";
              const deltaAbs = Math.abs(d.days_delta);
              const badgeCls = isLate
                ? "bg-rose-500/10 border-rose-500/20 text-rose-400"
                : isEarly
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : "bg-zinc-700/40 border-zinc-600/30 text-zinc-400";
              const label = isLate ? `${deltaAbs}d late` : isEarly ? `${deltaAbs}d early` : "on time";
              return (
                <div key={d.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-200 truncate">{d.title ?? "Untitled"}</p>
                    <p className="text-[11px] text-zinc-500 truncate">{d.company ?? "—"} · exp {d.expected_close} → closed {d.actual_close}</p>
                  </div>
                  <span className="shrink-0 text-xs font-mono text-zinc-400">{formatCurrency(d.value)}</span>
                  <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-mono tabular-nums ${badgeCls}`}>{label}</span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Activity Trends — Phase 13a */}
      {activityTrends.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Activity className="h-4 w-4 text-violet-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Activity Trends</h3>
            <span className="ml-auto text-xs text-zinc-500">Last {activityTrends.length} weeks</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={activityTrends} margin={{ top: 0, right: 8, left: -24, bottom: 0 }} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis
                dataKey="week_start"
                tick={{ fill: "#71717a", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: "#a1a1aa" }}
                itemStyle={{ color: "#e4e4e7" }}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#71717a" }} />
              <Bar dataKey="deals" stackId="a" fill="#6366f1" name="Deals" radius={[0, 0, 0, 0]} />
              <Bar dataKey="contacts" stackId="a" fill="#22d3ee" name="Contacts" radius={[0, 0, 0, 0]} />
              <Bar dataKey="agents" stackId="a" fill="#a78bfa" name="Agents" radius={[0, 0, 0, 0]} />
              <Bar dataKey="messages" stackId="a" fill="#34d399" name="Messages" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Contact Re-engagement Summary — Phase 13b */}
      {reengagementSummary.length > 0 && reengagementSummary.some((r) => r.reengaged > 0) && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Activity className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Contact Re-engagement</h3>
            <span className="ml-auto text-xs text-zinc-500">
              {reengagementSummary.reduce((s, r) => s + r.reengaged, 0)} re-engagements · last {reengagementSummary.length} weeks
            </span>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={reengagementSummary} margin={{ top: 0, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis
                dataKey="week_start"
                tick={{ fill: "#71717a", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-1">Week of {label}</p>
                      <p className="text-emerald-400 font-mono font-bold">{payload[0].value} re-engaged</p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="reengaged" name="Re-engaged" fill="#00C896" radius={[4, 4, 0, 0]} maxBarSize={36} />
            </BarChart>
          </ResponsiveContainer>
          <p className="mt-2 text-[10px] text-zinc-600 font-mono">Contacts that received a touch after 30+ days of silence</p>
        </Card>
      )}

      {/* Revenue Cohort Analysis — Phase 13c */}
      {revenueCohort.length > 0 && revenueCohort.some((c) => c.initial_revenue > 0) && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Revenue Cohort Retention</h3>
            <span className="ml-auto text-xs text-zinc-500">by acquisition month · % of initial revenue</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr>
                  <th className="text-left text-zinc-500 pr-4 pb-2 font-normal">Cohort</th>
                  <th className="text-right text-zinc-500 pr-4 pb-2 font-normal">Initial</th>
                  {revenueCohort[0].months.map((m) => (
                    <th key={m.month_offset} className="text-center text-zinc-500 pb-2 px-1 font-normal min-w-[52px]">
                      {m.month_offset === 0 ? "M+0" : `M+${m.month_offset}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {revenueCohort.map((cohort) => (
                  <tr key={cohort.cohort_month}>
                    <td className="pr-4 py-1 text-zinc-300">{cohort.cohort_month}</td>
                    <td className="pr-4 py-1 text-right text-zinc-300">{formatCurrency(cohort.initial_revenue)}</td>
                    {cohort.months.map((m) => {
                      const pct = m.pct_of_initial;
                      const bg =
                        pct === null ? "bg-zinc-800/30" :
                        pct === 0   ? "bg-zinc-800/50" :
                        pct >= 80   ? "bg-emerald-900/70" :
                        pct >= 50   ? "bg-emerald-900/50" :
                        pct >= 25   ? "bg-emerald-900/30" :
                                      "bg-emerald-900/15";
                      const textColor =
                        pct === null ? "text-zinc-700" :
                        pct === 0   ? "text-zinc-600" :
                        pct >= 50   ? "text-emerald-300" :
                                      "text-emerald-500";
                      return (
                        <td key={m.month_offset} className={`px-1 py-1 text-center rounded ${bg}`}>
                          <span className={textColor}>
                            {pct === null ? "—" : pct === 0 ? "0%" : `${pct}%`}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[10px] text-zinc-600 font-mono">
            Each row = contacts first acquired that month. Later columns show expansion revenue from those contacts as % of initial.
          </p>
        </Card>
      )}

      {/* Deal Velocity Trends — Phase 13d */}
      {velocityTrends.length > 0 && velocityTrends.some((r) => r.avg_cycle_days !== null) && (() => {
        const first = velocityTrends.find((r) => r.avg_cycle_days !== null)?.avg_cycle_days ?? null;
        const last  = [...velocityTrends].reverse().find((r) => r.avg_cycle_days !== null)?.avg_cycle_days ?? null;
        const delta = first !== null && last !== null ? Math.round(last - first) : null;
        const improved = delta !== null && delta < 0;
        return (
          <Card>
            <div className="flex items-center gap-2 mb-4">
              {improved
                ? <TrendingDown className="h-4 w-4 text-emerald-400" />
                : <TrendingUp className="h-4 w-4 text-indigo-400" />}
              <h3 className="text-sm font-semibold text-zinc-200">Deal Velocity Trends</h3>
              <span className="ml-auto text-xs text-zinc-500">avg days to close · last {velocityTrends.length} months</span>
              {delta !== null && (
                <span className={`text-xs font-mono font-bold ${improved ? "text-emerald-400" : "text-rose-400"}`}>
                  {improved ? "↓" : "↑"} {Math.abs(delta)}d MoM
                </span>
              )}
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={velocityTrends} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis
                  dataKey="month"
                  tick={{ fill: "#71717a", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: string) => v.slice(5)}
                />
                <YAxis
                  tick={{ fill: "#71717a", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => `${v}d`}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0];
                    const row = velocityTrends.find((r) => r.month === label);
                    return (
                      <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                        <p className="font-mono text-zinc-400 mb-1">{label}</p>
                        {p.value !== null
                          ? <p className="text-indigo-300 font-mono font-bold">{p.value}d avg cycle</p>
                          : <p className="text-zinc-600">No closed deals</p>}
                        {row && (
                          <>
                            <p className="text-emerald-400 mt-1">{row.closed_won} won</p>
                            <p className="text-rose-400">{row.closed_lost} lost</p>
                          </>
                        )}
                      </div>
                    );
                  }}
                />
                <ReferenceLine
                  y={velocityTrends.filter((r) => r.avg_cycle_days !== null).reduce((s, r) => s + (r.avg_cycle_days ?? 0), 0) / Math.max(1, velocityTrends.filter((r) => r.avg_cycle_days !== null).length)}
                  stroke="#52525b"
                  strokeDasharray="4 4"
                  label={{ value: "avg", position: "right", fill: "#52525b", fontSize: 9 }}
                />
                <Line
                  type="monotone"
                  dataKey="avg_cycle_days"
                  name="Avg cycle days"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={{ fill: "#6366f1", r: 3, strokeWidth: 0 }}
                  activeDot={{ r: 5, fill: "#818cf8" }}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
            <p className="mt-2 text-[10px] text-zinc-600 font-mono">Days from deal creation to closed_won / closed_lost, averaged per calendar month</p>
          </Card>
        );
      })()}

      {/* Message Volume by Source */}
      {messageVolume.length > 0 && (() => {
        const hasTeams = messageVolume.some((w) => w.teams > 0);
        const hasUnknown = messageVolume.some((w) => w.unknown > 0);
        const display = messageVolume.map((w) => ({
          ...w,
          label: w.week_start.slice(5), // MM-DD
        }));
        return (
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Message Volume by Source</p>
              <span className="ml-auto text-[10px] font-mono text-zinc-500">Last 12 weeks</span>
            </div>
            <div className="flex items-center gap-4 text-[10px]">
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-indigo-400" />Gmail</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-violet-400" />Slack</span>
              {hasTeams   && <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-sky-400"    />Teams</span>}
              {hasUnknown && <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-zinc-500"   />Other</span>}
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={display} margin={{ top: 4, right: 4, bottom: 0, left: -24 }} barSize={8} barGap={1}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: "#71717A", fontSize: 9 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: "#71717A", fontSize: 9 }} axisLine={false} tickLine={false} width={28} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }}
                    formatter={(v, name) => [v ?? 0, String(name).charAt(0).toUpperCase() + String(name).slice(1)]}
                  />
                  <Bar dataKey="gmail"   stackId="a" fill="#6366F1" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="slack"   stackId="a" fill="#8B5CF6" radius={[0, 0, 0, 0]} />
                  {hasTeams   && <Bar dataKey="teams"   stackId="a" fill="#38BDF8" radius={[0, 0, 0, 0]} />}
                  {hasUnknown && <Bar dataKey="unknown" stackId="a" fill="#52525B" radius={[2, 2, 0, 0]} />}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        );
      })()}

      {/* Contact Acquisition Funnel — Phase 16e */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-indigo-400" />
          <p className="text-sm font-semibold text-zinc-200">Contact Acquisition Funnel</p>
          <button
            onClick={() => setAcquisitionFunnelOpen((o) => !o)}
            className="ml-auto text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {acquisitionFunnelOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          <button
            onClick={() => {
              if (acquisitionFunnelLoading) return;
              setAcquisitionFunnelLoading(true);
              const load = (wsId: string, tok: string) =>
                apiClient.getContactAcquisitionFunnel(wsId, tok).then(setAcquisitionFunnel).catch(() => {}).finally(() => setAcquisitionFunnelLoading(false));
              if (DEMO_MODE) { load("demo-workspace-1", "demo-token"); return; }
              const supabase = createBrowserClient();
              supabase.auth.getSession().then(({ data: { session } }) => {
                if (!session) { setAcquisitionFunnelLoading(false); return; }
                const wsId = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
                if (wsId) load(wsId, session.access_token); else setAcquisitionFunnelLoading(false);
              });
            }}
            className="text-zinc-500 hover:text-zinc-300 transition-colors"
            title="Regenerate"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", acquisitionFunnelLoading && "animate-spin")} />
          </button>
        </div>
        {acquisitionFunnelOpen && (
          acquisitionFunnelLoading ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-5 w-full rounded bg-zinc-800" />
              <div className="h-5 w-4/5 rounded bg-zinc-800" />
              <div className="h-5 w-3/5 rounded bg-zinc-800" />
            </div>
          ) : acquisitionFunnel ? (
            <div className="space-y-4">
              {/* Funnel bars */}
              <div className="space-y-2">
                {acquisitionFunnel.funnel_stages.map((stage, idx) => {
                  const maxCount = Math.max(...acquisitionFunnel.funnel_stages.map((s) => s.count), 1);
                  const pct = Math.round((stage.count / maxCount) * 100);
                  const stageLabel = stage.stage.charAt(0).toUpperCase() + stage.stage.slice(1);
                  return (
                    <div key={stage.stage}>
                      {idx > 0 && stage.conversion_rate !== null && (
                        <div className="flex items-center gap-1 my-1 pl-2">
                          <div className="w-0.5 h-3 bg-zinc-700 mx-2" />
                          <span className="text-[10px] font-mono text-zinc-500">
                            {stage.conversion_rate}% conversion
                          </span>
                        </div>
                      )}
                      <div className="flex items-center gap-3">
                        <span className="w-20 text-xs text-zinc-400 shrink-0">{stageLabel}</span>
                        <div className="flex-1 bg-zinc-800 rounded-full h-5 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-indigo-500/70 flex items-center px-2 transition-all duration-500"
                            style={{ width: `${Math.max(pct, 4)}%` }}
                          >
                            <span className="text-[10px] font-mono text-white whitespace-nowrap">{stage.count}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* Top insight */}
              <p className="text-xs text-zinc-300 italic border-l-2 border-indigo-500 pl-3">
                {acquisitionFunnel.top_insight}
              </p>
              {/* Recommendations */}
              <ul className="space-y-1.5">
                {acquisitionFunnel.recommendations.map((r, i) => (
                  <li key={i} className="flex gap-2 text-xs text-zinc-400">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-zinc-600">
                Generated {new Date(acquisitionFunnel.generated_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500">No data available.</p>
          )
        )}
      </Card>

      {/* Contact Source Attribution — Phase 16f */}
      <Card>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-teal-400" />
            <p className="text-sm font-semibold text-zinc-200">Contact Source Attribution</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                const supabase = createBrowserClient();
                supabase.auth.getSession().then(({ data: { session } }) => {
                  const wsId = DEMO_MODE ? "demo-workspace-1" : (session?.user.app_metadata?.workspace_id ?? session?.user.user_metadata?.workspace_id);
                  const tok = DEMO_MODE ? "demo-token" : (session?.access_token ?? "");
                  if (!wsId || sourceAttributionLoading) return;
                  setSourceAttributionLoading(true);
                  apiClient.getContactSourceAttribution(wsId, tok).then(setSourceAttribution).catch(() => {}).finally(() => setSourceAttributionLoading(false));
                });
              }}
              className="rounded p-1 hover:bg-zinc-700 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", sourceAttributionLoading && "animate-spin")} />
            </button>
            <button onClick={() => setSourceAttributionOpen((o) => !o)} className="rounded p-1 hover:bg-zinc-700 text-zinc-500 hover:text-zinc-300 transition-colors">
              {sourceAttributionOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {sourceAttributionOpen && (
          sourceAttributionLoading ? (
            <div className="mt-4 space-y-2 animate-pulse">
              {[1,2,3].map((i) => <div key={i} className="h-6 rounded bg-zinc-800" />)}
            </div>
          ) : sourceAttribution ? (
            <div className="mt-4 space-y-4">
              {/* Per-source rows */}
              <div className="space-y-2">
                {sourceAttribution.sources.map((s) => {
                  const maxPipeline = Math.max(...sourceAttribution.sources.map((x) => x.pipeline_value), 1);
                  return (
                    <div key={s.source_label} className="space-y-0.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-zinc-200 font-medium">{s.source_label}</span>
                        <div className="flex items-center gap-3 text-zinc-400">
                          <span>{s.contact_count} contact{s.contact_count !== 1 ? "s" : ""}</span>
                          <span className="text-indigo-300 font-mono">{formatCurrency(s.pipeline_value)}</span>
                          <span className="text-emerald-400 font-mono">{formatCurrency(s.won_revenue)} won</span>
                          <span className="text-zinc-500">{s.win_rate}% WR</span>
                        </div>
                      </div>
                      <div className="relative h-1.5 rounded-full bg-zinc-800">
                        <div
                          className="absolute inset-y-0 left-0 rounded-full bg-teal-500"
                          style={{ width: `${Math.round((s.pipeline_value / maxPipeline) * 100)}%` }}
                        />
                        <div
                          className="absolute inset-y-0 left-0 rounded-full bg-emerald-500 opacity-70"
                          style={{ width: `${Math.round((s.won_revenue / maxPipeline) * 100)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* AI insight */}
              <p className="text-xs text-zinc-300 italic border-l-2 border-teal-500 pl-3">
                {sourceAttribution.insight}
              </p>
              {/* Recommendations */}
              <ul className="space-y-1.5">
                {sourceAttribution.recommendations.map((r, i) => (
                  <li key={i} className="flex gap-2 text-xs text-zinc-400">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-zinc-600">
                Generated {new Date(sourceAttribution.generated_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 mt-3">No data available.</p>
          )
        )}
      </Card>

      {/* Task Completion Trends — Phase 16g */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <CheckSquare className="h-4 w-4 text-emerald-400" />
          <p className="text-sm font-semibold text-zinc-200">Task Completion Trends</p>
          {taskCompletionTrends && (
            <span className={cn(
              "ml-1 rounded-full px-2 py-0.5 text-[10px] font-semibold",
              taskCompletionTrends.trend === "improving" ? "bg-emerald-500/20 text-emerald-300" :
              taskCompletionTrends.trend === "declining" ? "bg-rose-500/20 text-rose-300" :
              "bg-zinc-500/20 text-zinc-300"
            )}>
              {taskCompletionTrends.trend === "improving" ? "↑ Improving" :
               taskCompletionTrends.trend === "declining" ? "↓ Declining" : "→ Stable"}
            </span>
          )}
          <div className="flex-1" />
          <button
            onClick={() => {
              if (taskCompletionTrendsLoading) return;
              setTaskCompletionTrendsLoading(true);
              const load = (wsId: string, tok: string) =>
                apiClient.getTaskCompletionTrends(wsId, tok).then(setTaskCompletionTrends).catch(() => {}).finally(() => setTaskCompletionTrendsLoading(false));
              if (DEMO_MODE) { load("demo-workspace-1", "demo-token"); return; }
              const supabase = createBrowserClient();
              supabase.auth.getSession().then(({ data: { session } }) => {
                if (!session) { setTaskCompletionTrendsLoading(false); return; }
                const wsId = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
                if (wsId) load(wsId, session.access_token); else setTaskCompletionTrendsLoading(false);
              });
            }}
            className="text-zinc-500 hover:text-zinc-300 transition-colors"
            title="Regenerate"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", taskCompletionTrendsLoading && "animate-spin")} />
          </button>
          <button onClick={() => setTaskCompletionTrendsOpen((o) => !o)} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            {taskCompletionTrendsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>

        {taskCompletionTrendsOpen && (
          taskCompletionTrendsLoading ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-40 rounded-lg bg-zinc-800/60" />
              <div className="h-3 w-3/4 rounded bg-zinc-800/60" />
            </div>
          ) : taskCompletionTrends ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4 text-xs text-zinc-400">
                <span>Avg completion rate: <span className="font-semibold text-zinc-200">{taskCompletionTrends.avg_completion_rate}%</span></span>
              </div>
              <ResponsiveContainer width="100%" height={180}>
                <ComposedChart data={taskCompletionTrends.weeks} margin={{ top: 4, right: 40, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
                  <XAxis
                    dataKey="week_start"
                    tick={{ fontSize: 9, fill: "#71717a" }}
                    tickFormatter={(v: string) => {
                      const d = new Date(v);
                      return `${d.toLocaleString("default", { month: "short" })} ${d.getDate()}`;
                    }}
                    interval={2}
                  />
                  <YAxis yAxisId="left" tick={{ fontSize: 9, fill: "#71717a" }} width={28} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 9, fill: "#71717a" }} width={32} unit="%" />
                  <Tooltip
                    contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8, fontSize: 11 }}
                    formatter={(value: unknown, name: unknown) => {
                      if (name === "completion_rate") return [`${value}%`, "Completion Rate"];
                      const n = String(name);
                      return [value as number, n.charAt(0).toUpperCase() + n.slice(1)];
                    }}
                    labelFormatter={(label: unknown) => new Date(String(label)).toLocaleDateString()}
                  />
                  <Legend wrapperStyle={{ fontSize: 10, color: "#a1a1aa" }} />
                  <Bar yAxisId="left" dataKey="created" name="Created" fill="#52525b" radius={[2, 2, 0, 0]} />
                  <Bar yAxisId="left" dataKey="completed" name="Completed" fill="#10b981" radius={[2, 2, 0, 0]} />
                  <Bar yAxisId="left" dataKey="overdue" name="Overdue" fill="#f43f5e" radius={[2, 2, 0, 0]} />
                  <Line yAxisId="right" dataKey="completion_rate" name="completion_rate" stroke="#818cf8" strokeWidth={2} strokeDasharray="4 2" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
              <p className="text-xs text-zinc-300 italic border-l-2 border-emerald-500 pl-3">
                {taskCompletionTrends.insight}
              </p>
              <ul className="space-y-1.5">
                {taskCompletionTrends.recommendations.map((r, i) => (
                  <li key={i} className="flex gap-2 text-xs text-zinc-400">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-zinc-600">
                Generated {new Date(taskCompletionTrends.generated_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 mt-3">No task data available.</p>
          )
        )}
      </Card>

      {/* Response Time Benchmark */}
      <Card>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-sky-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Response Time Benchmark</h3>
            {msgBenchmark && (
              <span className={cn(
                "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                msgBenchmark.rating === "excellent" ? "bg-emerald-500/15 text-emerald-400" :
                msgBenchmark.rating === "good"      ? "bg-indigo-500/15 text-indigo-400" :
                msgBenchmark.rating === "fair"      ? "bg-amber-500/15 text-amber-400" :
                                                      "bg-rose-500/15 text-rose-400"
              )}>
                {msgBenchmark.rating}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (!msgBenchmarkLoading) {
                  setMsgBenchmarkLoading(true);
                  (DEMO_MODE
                    ? apiClient.getMessageResponseTimeBenchmark("demo-workspace-1", "demo-token")
                    : createBrowserClient().auth.getSession().then(({ data: { session } }) =>
                        session ? apiClient.getMessageResponseTimeBenchmark(
                          session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id,
                          session.access_token
                        ) : Promise.reject()
                      )
                  ).then(setMsgBenchmark).catch(() => {}).finally(() => setMsgBenchmarkLoading(false));
                }
              }}
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
              title="Regenerate"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", msgBenchmarkLoading && "animate-spin")} />
            </button>
            <button onClick={() => setMsgBenchmarkOpen((o) => !o)} className="text-zinc-500 hover:text-zinc-300">
              {msgBenchmarkOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {msgBenchmarkOpen && (
          msgBenchmarkLoading ? (
            <div className="mt-4 space-y-2">
              {[1, 2, 3].map((i) => <div key={i} className="h-6 bg-zinc-800 rounded animate-pulse" />)}
            </div>
          ) : msgBenchmark ? (
            <div className="mt-4 space-y-4">
              {/* Overall rating ring + per-service rows */}
              <div className="flex items-start gap-6">
                {/* SVG ring for overall avg */}
                {msgBenchmark.overall_avg_hours != null && (
                  <div className="flex flex-col items-center gap-1 flex-shrink-0">
                    <svg width="64" height="64" viewBox="0 0 64 64">
                      <circle cx="32" cy="32" r="26" fill="none" stroke="#27272A" strokeWidth="8" />
                      <circle
                        cx="32" cy="32" r="26" fill="none"
                        stroke={
                          msgBenchmark.rating === "excellent" ? "#10B981" :
                          msgBenchmark.rating === "good"      ? "#6366F1" :
                          msgBenchmark.rating === "fair"      ? "#F59E0B" : "#F43F5E"
                        }
                        strokeWidth="8"
                        strokeDasharray={`${Math.max(10, 163 - (msgBenchmark.overall_avg_hours / 48) * 163)} 163`}
                        strokeLinecap="round"
                        transform="rotate(-90 32 32)"
                      />
                    </svg>
                    <p className="text-[10px] text-zinc-400 font-mono">{msgBenchmark.overall_avg_hours}h avg</p>
                  </div>
                )}
                {/* Per-service rows */}
                <div className="flex-1 space-y-2">
                  {msgBenchmark.benchmark.map((b) => (
                    <div key={b.service} className="flex items-center gap-3 text-xs">
                      <span className="w-12 capitalize text-zinc-400 font-medium">{b.service}</span>
                      <span className={cn(
                        "font-mono",
                        b.avg_hours < 2 ? "text-emerald-400" :
                        b.avg_hours < 8 ? "text-indigo-400" :
                        b.avg_hours < 24 ? "text-amber-400" : "text-rose-400"
                      )}>avg {b.avg_hours}h</span>
                      <span className="text-zinc-500">p50 {b.p50_hours}h</span>
                      <span className="text-zinc-500">p90 {b.p90_hours}h</span>
                      <span className="ml-auto text-zinc-600">{b.message_count} pairs</span>
                    </div>
                  ))}
                  {msgBenchmark.benchmark.length === 0 && (
                    <p className="text-xs text-zinc-500">No reply pairs found. Connect a Gmail or Slack connector to track response times.</p>
                  )}
                </div>
              </div>
              {/* Insight */}
              <p className="text-xs text-zinc-400 italic border-l-2 border-sky-500/40 pl-3">{msgBenchmark.insight}</p>
              {/* Recommendations */}
              <ul className="space-y-1">
                {msgBenchmark.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-zinc-600">
                Generated {new Date(msgBenchmark.generated_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 mt-3">No message data available.</p>
          )
        )}
      </Card>

      {/* Contact Engagement Benchmark */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-violet-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Contact Engagement Benchmark</h3>
            {engagementBenchmark && (
              <span className="text-xs font-mono text-zinc-500">avg {engagementBenchmark.avg_score}/100</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setEngagementBenchmarkLoading(true);
                const load = DEMO_MODE
                  ? apiClient.getContactEngagementBenchmark("demo-workspace-1", "demo-token")
                  : createBrowserClient().auth.getSession().then(({ data: { session } }) =>
                      apiClient.getContactEngagementBenchmark(
                        session?.user.app_metadata?.workspace_id ?? session?.user.user_metadata?.workspace_id ?? "",
                        session?.access_token ?? ""
                      )
                    );
                load.then(setEngagementBenchmark).catch(() => {}).finally(() => setEngagementBenchmarkLoading(false));
              }}
              className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", engagementBenchmarkLoading && "animate-spin")} />
            </button>
            <button
              onClick={() => setEngagementBenchmarkOpen((o) => !o)}
              className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              {engagementBenchmarkOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
        {engagementBenchmarkOpen && (
          engagementBenchmarkLoading ? (
            <div className="space-y-2 mt-3">
              {[...Array(3)].map((_, i) => <div key={i} className="h-4 rounded bg-zinc-800 animate-pulse" />)}
            </div>
          ) : engagementBenchmark ? (
            <div className="space-y-4 mt-1">
              {/* Bucket bar chart */}
              <div className="space-y-2">
                {engagementBenchmark.buckets.map((b) => {
                  const total = engagementBenchmark.buckets.reduce((s, x) => s + x.count, 0) || 1;
                  const pct = Math.round((b.count / total) * 100);
                  const color = b.label.startsWith("High") ? "bg-violet-500" : b.label.startsWith("Medium") ? "bg-indigo-500" : "bg-zinc-600";
                  return (
                    <div key={b.label} className="space-y-0.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-zinc-400">{b.label}</span>
                        <span className="font-mono text-zinc-300">{b.count} contacts · avg {b.avg_score}</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-zinc-800">
                        <div className={cn("h-2 rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* Top / Bottom tables */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Top Engaged</p>
                  <div className="space-y-1.5">
                    {engagementBenchmark.top_contacts.map((c) => (
                      <div key={c.id} className="flex items-center gap-2">
                        <div className="h-1.5 rounded-full bg-violet-500" style={{ width: `${Math.round((c.score / 100) * 80)}px` }} />
                        <span className="text-xs text-zinc-300 truncate flex-1">{c.name ?? c.email}</span>
                        <span className="text-[11px] font-mono text-violet-400">{c.score}</span>
                      </div>
                    ))}
                    {engagementBenchmark.top_contacts.length === 0 && (
                      <p className="text-xs text-zinc-500">No contacts yet.</p>
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Least Engaged</p>
                  <div className="space-y-1.5">
                    {engagementBenchmark.bottom_contacts.map((c) => (
                      <div key={c.id} className="flex items-center gap-2">
                        <div className="h-1.5 rounded-full bg-zinc-600" style={{ width: `${Math.round((c.score / 100) * 80)}px` }} />
                        <span className="text-xs text-zinc-400 truncate flex-1">{c.name ?? c.email}</span>
                        <span className="text-[11px] font-mono text-zinc-500">{c.score}</span>
                      </div>
                    ))}
                    {engagementBenchmark.bottom_contacts.length === 0 && (
                      <p className="text-xs text-zinc-500">No contacts yet.</p>
                    )}
                  </div>
                </div>
              </div>
              {/* Insight */}
              <p className="text-xs text-zinc-400 italic border-l-2 border-violet-500/40 pl-3">{engagementBenchmark.insight}</p>
              {/* Recommendations */}
              <ul className="space-y-1">
                {engagementBenchmark.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-zinc-600">
                Generated {new Date(engagementBenchmark.generated_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 mt-3">No engagement data available.</p>
          )
        )}
      </Card>

      {/* Negotiation Readiness — Phase 16j */}
      <Card className="border-amber-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-amber-400" />
            <span className="text-sm font-semibold text-zinc-100">Negotiation Readiness</span>
            {negotiationReadiness && (
              <span className={cn(
                "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
                negotiationReadiness.not_ready_count === 0 && negotiationReadiness.total_deals > 0
                  ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                  : negotiationReadiness.not_ready_count > 0
                  ? "border-rose-500/20 bg-rose-500/10 text-rose-400"
                  : "border-amber-500/20 bg-amber-500/10 text-amber-400"
              )}>
                {negotiationReadiness.not_ready_count === 0 && negotiationReadiness.total_deals > 0
                  ? `${negotiationReadiness.ready_count} ready`
                  : negotiationReadiness.not_ready_count > 0
                  ? `${negotiationReadiness.not_ready_count} blocked`
                  : `${negotiationReadiness.total_deals} deals`}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateNegotiationReadiness}
              disabled={negotiationReadinessLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={cn("h-3 w-3", negotiationReadinessLoading && "animate-spin")} />
              {negotiationReadinessLoading ? "Generating…" : "Regenerate"}
            </button>
            <button
              onClick={() => setNegotiationReadinessOpen((o) => !o)}
              className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              {negotiationReadinessOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {negotiationReadinessOpen && (
          negotiationReadinessLoading && !negotiationReadiness ? (
            <div className="space-y-2 mt-3">
              {[...Array(3)].map((_, i) => <div key={i} className="h-10 rounded bg-zinc-800 animate-pulse" />)}
            </div>
          ) : negotiationReadiness ? (
            <div className={cn("space-y-3 mt-3", negotiationReadinessLoading && "opacity-40")}>
              <p className="text-xs text-zinc-400 italic">{negotiationReadiness.summary}</p>
              {negotiationReadiness.deals.length === 0 ? (
                <p className="text-xs text-zinc-500">No deals in proposal or negotiation stage.</p>
              ) : (
                <div className="space-y-2">
                  {negotiationReadiness.deals.map((d) => {
                    const readinessColor =
                      d.readiness === 'ready' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
                      : d.readiness === 'not_ready' ? 'text-rose-400 border-rose-500/30 bg-rose-500/10'
                      : 'text-amber-400 border-amber-500/30 bg-amber-500/10';
                    const readinessLabel =
                      d.readiness === 'ready' ? 'Ready' : d.readiness === 'not_ready' ? 'Blocked' : 'Needs Work';
                    const stageLabel = stageConfig[d.stage as keyof typeof stageConfig]?.label ?? d.stage;
                    return (
                      <div key={d.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <p className="text-xs font-medium text-zinc-200">{d.title}</p>
                            <p className="text-[11px] text-zinc-500">{d.company} · <span className="text-zinc-400">{stageLabel}</span></p>
                          </div>
                          <span className={cn("flex-shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium", readinessColor)}>
                            {readinessLabel}
                          </span>
                        </div>
                        {d.blockers.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {d.blockers.map((b, i) => (
                              <span key={i} className="rounded-full border border-rose-500/20 bg-rose-500/10 px-2 py-0.5 text-[10px] text-rose-300">{b}</span>
                            ))}
                          </div>
                        )}
                        {d.next_steps.length > 0 && (
                          <ul className="space-y-0.5">
                            {d.next_steps.map((s, i) => (
                              <li key={i} className="flex items-start gap-1.5 text-[11px] text-zinc-400">
                                <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                                {s}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="text-[10px] font-mono text-zinc-600">
                Generated {new Date(negotiationReadiness.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 mt-3">No negotiation data available.</p>
          )
        )}
      </Card>

      {/* Message Source Reliability */}
      <Card className="space-y-0 p-0 overflow-hidden">
        <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <CloudDownload className="h-4 w-4 text-sky-400" />
            <span className="text-sm font-semibold text-zinc-100">Message Source Reliability</span>
            {msgSourceReliability?.most_reliable_source && (
              <span className="inline-flex items-center rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-400">
                Most reliable: {msgSourceReliability.most_reliable_source}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateMsgSourceReliability}
              disabled={msgSourceReliabilityLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={cn("h-3 w-3", msgSourceReliabilityLoading && "animate-spin")} />
              {msgSourceReliabilityLoading ? "Generating…" : "Regenerate"}
            </button>
            <button
              onClick={() => setMsgSourceReliabilityOpen((o) => !o)}
              className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              {msgSourceReliabilityOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {msgSourceReliabilityOpen && (
          msgSourceReliabilityLoading && !msgSourceReliability ? (
            <div className="space-y-3 p-4">
              {[...Array(3)].map((_, i) => <div key={i} className="h-12 rounded bg-zinc-800 animate-pulse" />)}
            </div>
          ) : msgSourceReliability ? (
            <div className={cn("space-y-4 p-4", msgSourceReliabilityLoading && "opacity-40")}>
              {msgSourceReliability.sources.length === 0 ? (
                <p className="text-xs text-zinc-500">No messages ingested yet. Connect a Gmail or Slack account.</p>
              ) : (
                <div className="space-y-3">
                  {msgSourceReliability.sources.map((src) => {
                    const maxTrend = Math.max(...src.weekly_trend, 1);
                    const sparkPoints = src.weekly_trend.map((v, i) =>
                      `${(i / 11) * 100},${100 - (v / maxTrend) * 100}`
                    ).join(' ');
                    const serviceLabel = src.service.charAt(0).toUpperCase() + src.service.slice(1);
                    const rateColor = src.processed_rate >= 95
                      ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                      : src.processed_rate >= 80
                      ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                      : 'text-rose-400 bg-rose-500/10 border-rose-500/20';
                    const barColor = src.processed_rate >= 95 ? '#00C896' : src.processed_rate >= 80 ? '#FBBF24' : '#F43F5E';
                    return (
                      <div key={src.service} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-2">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-zinc-200">{serviceLabel}</span>
                            <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", rateColor)}>
                              {src.processed_rate}% processed
                            </span>
                          </div>
                          <span className="text-[11px] text-zinc-500 font-mono">{src.total_messages} msgs</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <div className="flex-1">
                            <div className="h-1.5 w-full rounded-full bg-zinc-800">
                              <div
                                className="h-1.5 rounded-full transition-all"
                                style={{ width: `${src.processed_rate}%`, backgroundColor: barColor }}
                              />
                            </div>
                          </div>
                          <svg
                            viewBox="0 0 100 100"
                            className="h-6 w-20 flex-shrink-0"
                            preserveAspectRatio="none"
                          >
                            <polyline
                              points={sparkPoints}
                              fill="none"
                              stroke="#38BDF8"
                              strokeWidth="3"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="text-xs text-zinc-400 italic">{msgSourceReliability.insight}</p>
              <ul className="space-y-1">
                {msgSourceReliability.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-zinc-600">
                Generated {new Date(msgSourceReliability.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No source reliability data available.</p>
          )
        )}
      </Card>

      {/* Stage Transition Analysis */}
      <Card className="border-zinc-700/50">
        <div className="flex items-center gap-2 p-4 border-b border-zinc-700/50">
          <ArrowRight className="h-4 w-4 text-violet-400" />
          <span className="text-sm font-semibold text-zinc-200">Stage Transition Analysis</span>
          {stageTransitionAnalysis?.bottleneck_stage && (
            <span className="ml-1 rounded-full bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-xs text-amber-400">
              Bottleneck: {stageTransitionAnalysis.bottleneck_stage}
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={regenerateStageTransitionAnalysis}
              disabled={stageTransitionLoading}
              className="flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", stageTransitionLoading && "animate-spin")} />
              {stageTransitionLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setStageTransitionOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {stageTransitionOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {stageTransitionOpen && (
          stageTransitionLoading && !stageTransitionAnalysis ? (
            <p className="p-4 text-xs text-zinc-500 animate-pulse">Analysing stage transitions…</p>
          ) : stageTransitionAnalysis ? (
            <div className={cn("space-y-4 p-4", stageTransitionLoading && "opacity-40")}>
              {stageTransitionAnalysis.transitions.length === 0 ? (
                <p className="text-xs text-zinc-500">No stage transitions recorded in the last 90 days.</p>
              ) : (
                <div className="space-y-2">
                  {stageTransitionAnalysis.transitions.map((t, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span className="w-28 truncate text-zinc-300 capitalize">{t.from_stage.replace(/_/g, ' ')}</span>
                      <ArrowRight className="h-3 w-3 flex-shrink-0 text-violet-400" />
                      <span className="w-28 truncate text-zinc-300 capitalize">{t.to_stage.replace(/_/g, ' ')}</span>
                      <span className="ml-auto text-zinc-400">{t.count}×</span>
                      <span className={cn(
                        "w-20 text-right font-mono",
                        t.avg_days > 14 ? "text-rose-400" : t.avg_days > 7 ? "text-amber-400" : "text-emerald-400"
                      )}>{t.avg_days}d avg</span>
                    </div>
                  ))}
                  {stageTransitionAnalysis.fastest_transition && (
                    <p className="text-xs text-zinc-500 pt-1">
                      Fastest: <span className="text-emerald-400">{stageTransitionAnalysis.fastest_transition}</span>
                    </p>
                  )}
                </div>
              )}
              <p className="text-xs text-zinc-400 italic">{stageTransitionAnalysis.insight}</p>
              <ul className="space-y-1">
                {stageTransitionAnalysis.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(stageTransitionAnalysis.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No stage transition data available.</p>
          )
        )}
      </Card>

      {/* Phase 16m: Revenue Trend Analysis */}
      <Card className="border-zinc-800 p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
          <TrendingUp className="h-4 w-4 text-emerald-400" />
          <span className="text-sm font-semibold text-zinc-200">Revenue Trend Analysis</span>
          {revenueTrend?.trend_direction && (() => {
            const cfg = TREND_DIR_CONFIG[revenueTrend.trend_direction];
            return (
              <span className={cn("ml-1 rounded-full border px-2 py-0.5 text-xs", cfg?.color, cfg?.bg)}>
                {cfg?.label ?? revenueTrend.trend_direction}
              </span>
            );
          })()}
          {revenueTrend?.growth_rate != null && (
            <span className={cn(
              "rounded-full border px-2 py-0.5 text-xs font-mono",
              revenueTrend.growth_rate >= 0 ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" : "text-rose-400 bg-rose-500/10 border-rose-500/20"
            )}>
              {revenueTrend.growth_rate >= 0 ? "+" : ""}{revenueTrend.growth_rate}% vs prior 6 mo
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={regenerateRevenueTrend}
              disabled={revenueTrendLoading}
              className="flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", revenueTrendLoading && "animate-spin")} />
              {revenueTrendLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setRevenueTrendOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {revenueTrendOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {revenueTrendOpen && (
          revenueTrendLoading && !revenueTrend ? (
            <p className="p-4 text-xs text-zinc-500 animate-pulse">Analysing revenue trends…</p>
          ) : revenueTrend ? (
            <div className={cn("space-y-4 p-4", revenueTrendLoading && "opacity-40")}>
              {revenueTrend.monthly_trend.some((r) => r.revenue > 0) ? (
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={revenueTrend.monthly_trend} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <defs>
                        <linearGradient id="revGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                      <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 10 }} tickLine={false} />
                      <YAxis tick={{ fill: "#71717A", fontSize: 10 }} tickLine={false} tickFormatter={(v: number) => `$${v >= 1000 ? `${Math.round(v / 1000)}k` : v}`} />
                      <Tooltip
                        content={({ active, payload, label }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload as RevenueTrendMonth;
                          return (
                            <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                              <p className="font-mono text-zinc-400 mb-1">{label}</p>
                              <p className="text-emerald-300">${d.revenue.toLocaleString()}</p>
                              <p className="text-zinc-500">{d.deal_count} deal{d.deal_count !== 1 ? "s" : ""} · avg ${d.avg_deal_size.toLocaleString()}</p>
                            </div>
                          );
                        }}
                      />
                      {revenueTrend.best_month && (
                        <ReferenceLine x={revenueTrend.best_month} stroke="#10B981" strokeDasharray="3 3" label={{ value: "Best", fill: "#10B981", fontSize: 9 }} />
                      )}
                      <Area type="monotone" dataKey="revenue" stroke="#10B981" strokeWidth={2} fill="url(#revGradient)" dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No closed-won revenue in the last 12 months.</p>
              )}
              <p className="text-xs text-zinc-400 italic">{revenueTrend.insight}</p>
              <ul className="space-y-1">
                {revenueTrend.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(revenueTrend.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No revenue trend data available.</p>
          )
        )}
      </Card>

      {/* Phase 16n: Contact Inactivity Risk */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <UserX className="h-4 w-4 text-rose-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Contact Inactivity Risk</h3>
            {inactivityRisk && (inactivityRisk.critical_count + inactivityRisk.high_risk_count + inactivityRisk.watch_count) > 0 && (
              <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-medium text-rose-400 border border-rose-500/20">
                {inactivityRisk.critical_count + inactivityRisk.high_risk_count + inactivityRisk.watch_count} at risk
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateInactivityRisk}
              disabled={inactivityRiskLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", inactivityRiskLoading && "animate-spin")} />
              {inactivityRiskLoading ? "Loading…" : "Regenerate"}
            </button>
            <button onClick={() => setInactivityRiskOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {inactivityRiskOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {inactivityRiskOpen && (
          inactivityRiskLoading && !inactivityRisk ? (
            <div className="h-24 animate-pulse rounded-b-xl bg-zinc-800/50" />
          ) : inactivityRisk ? (
            <div className={cn("space-y-4 p-4 pt-0", inactivityRiskLoading && "opacity-40")}>
              {/* Bucket summary row */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3 text-center">
                  <p className="text-xl font-bold text-rose-400">{inactivityRisk.critical_count}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">Critical</p>
                  <p className="text-xs text-zinc-600">&gt;60 days</p>
                </div>
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-center">
                  <p className="text-xl font-bold text-amber-400">{inactivityRisk.high_risk_count}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">High Risk</p>
                  <p className="text-xs text-zinc-600">30–60 days</p>
                </div>
                <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3 text-center">
                  <p className="text-xl font-bold text-yellow-400">{inactivityRisk.watch_count}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">Watch</p>
                  <p className="text-xs text-zinc-600">14–30 days</p>
                </div>
              </div>

              {/* Per-bucket expandable lists */}
              {inactivityRisk.contacts_by_bucket.map((bucketData) => {
                const isExpanded = inactivityExpandedBuckets.has(bucketData.bucket);
                const BUCKET_LABEL: Record<string, string> = { critical: "Critical (>60 days)", high_risk: "High Risk (30–60 days)", watch: "Watch (14–30 days)" };
                const BUCKET_COLOR: Record<string, string> = { critical: "text-rose-400", high_risk: "text-amber-400", watch: "text-yellow-400" };
                return (
                  <div key={bucketData.bucket}>
                    <button
                      onClick={() => setInactivityExpandedBuckets((prev) => {
                        const next = new Set(prev);
                        if (next.has(bucketData.bucket)) next.delete(bucketData.bucket); else next.add(bucketData.bucket);
                        return next;
                      })}
                      className="flex w-full items-center justify-between text-xs text-zinc-400 hover:text-zinc-200 py-1"
                    >
                      <span className={cn("font-medium", BUCKET_COLOR[bucketData.bucket])}>
                        {BUCKET_LABEL[bucketData.bucket]} ({bucketData.contacts.length})
                      </span>
                      {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    </button>
                    {isExpanded && (
                      <div className="mt-1 space-y-1 rounded-lg border border-zinc-800 bg-zinc-900/50 p-2">
                        {bucketData.contacts.map((c) => (
                          <div key={c.id} className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-zinc-800/50 transition-colors">
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-xs font-medium text-zinc-200">{c.name || c.email}</p>
                              <p className="truncate text-xs text-zinc-500">{c.company || c.email}</p>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              <span className="text-xs text-zinc-500">{c.days_since_touch > 900 ? "Never touched" : `${c.days_since_touch}d ago`}</span>
                              <Link href={`/contacts/${c.id}`} className="text-zinc-500 hover:text-indigo-400 transition-colors">
                                <ExternalLink className="h-3 w-3" />
                              </Link>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}

              {inactivityRisk.contacts_by_bucket.length === 0 && (
                <p className="text-xs text-emerald-400">All contacts have been recently engaged.</p>
              )}

              <p className="text-xs text-zinc-400 italic">{inactivityRisk.insight}</p>
              <ul className="space-y-1">
                {inactivityRisk.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(inactivityRisk.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No inactivity risk data available.</p>
          )
        )}
      </Card>

      {/* Phase 16o: Pipeline Momentum Snapshot */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-violet-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Pipeline Momentum</h3>
            {pipelineMomentum && (() => {
              const cfg = MOMENTUM_RATING_CONFIG[pipelineMomentum.momentum_rating];
              return (
                <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", cfg.bg, cfg.color)}>
                  {cfg.label}
                </span>
              );
            })()}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regeneratePipelineMomentum}
              disabled={pipelineMomentumLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", pipelineMomentumLoading && "animate-spin")} />
              {pipelineMomentumLoading ? "Loading…" : "Regenerate"}
            </button>
            <button onClick={() => setPipelineMomentumOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {pipelineMomentumOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {pipelineMomentumOpen && (
          pipelineMomentumLoading && !pipelineMomentum ? (
            <div className="h-24 animate-pulse rounded-b-xl bg-zinc-800/50" />
          ) : pipelineMomentum ? (
            <div className={cn("space-y-4 p-4 pt-0", pipelineMomentumLoading && "opacity-40")}>
              {/* Score + 3-metric row */}
              <div className="grid grid-cols-4 gap-3">
                <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3 text-center col-span-1">
                  <p className="text-2xl font-bold text-violet-400">{pipelineMomentum.momentum_score}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">Score</p>
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                  <p className="text-xl font-bold text-zinc-200">{pipelineMomentum.new_deals_14d}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">New Deals</p>
                  <p className="text-xs text-zinc-600">last 14d</p>
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                  <p className="text-xl font-bold text-zinc-200">{pipelineMomentum.stage_moves_14d}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">Stage Moves</p>
                  <p className="text-xs text-zinc-600">last 14d</p>
                </div>
                <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3 text-center">
                  <p className="text-xl font-bold text-rose-400">{pipelineMomentum.at_risk_count}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">At Risk</p>
                  <p className="text-xs text-zinc-600">health &lt;50</p>
                </div>
              </div>

              {/* Highlights */}
              {pipelineMomentum.highlights.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-zinc-400 mb-1">Highlights</p>
                  <ul className="space-y-1">
                    {pipelineMomentum.highlights.map((h, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                        <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400" />
                        {h}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Warnings */}
              {pipelineMomentum.warnings.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-zinc-400 mb-1">Watch</p>
                  <ul className="space-y-1">
                    {pipelineMomentum.warnings.map((w, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                        <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-rose-400" />
                        {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs text-zinc-600">
                Generated {new Date(pipelineMomentum.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No pipeline momentum data available.</p>
          )
        )}
      </Card>

      {/* Deal Age Risk */}
      <Card className="border-amber-500/15">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Deal Age Risk</h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateDealAgeRisk}
              disabled={dealAgeRiskLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", dealAgeRiskLoading && "animate-spin")} />
              {dealAgeRiskLoading ? "Loading…" : "Regenerate"}
            </button>
            <button onClick={() => setDealAgeRiskOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {dealAgeRiskOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {dealAgeRiskOpen && (
          dealAgeRiskLoading && !dealAgeRisk ? (
            <div className="h-24 animate-pulse rounded-b-xl bg-zinc-800/50" />
          ) : dealAgeRisk ? (
            <div className={cn("space-y-4 p-4 pt-0", dealAgeRiskLoading && "opacity-40")}>
              {/* 3-bucket count row */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3 text-center">
                  <p className="text-2xl font-bold text-rose-400">{dealAgeRisk.overdue_count}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">Overdue</p>
                </div>
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-center">
                  <p className="text-2xl font-bold text-amber-400">{dealAgeRisk.at_risk_count}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">At Risk</p>
                </div>
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-center">
                  <p className="text-2xl font-bold text-emerald-400">{dealAgeRisk.on_track_count}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">On Track</p>
                </div>
              </div>

              {/* Deal list */}
              {dealAgeRisk.deals.length > 0 && (
                <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
                  {dealAgeRisk.deals.map((deal) => {
                    const chipColor = deal.risk_level === 'overdue'
                      ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                      : deal.risk_level === 'at_risk'
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
                    return (
                      <div key={deal.id} className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-medium text-zinc-200">{deal.title ?? '(Untitled)'}</p>
                          <p className="text-xs text-zinc-500 capitalize">{deal.stage.replace(/_/g, ' ')}</p>
                        </div>
                        <span className={cn("ml-3 flex-shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium", chipColor)}>
                          {deal.days_open}d / {deal.expected_days}d
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Insight */}
              {dealAgeRisk.insight && (
                <p className="text-xs italic text-zinc-400">{dealAgeRisk.insight}</p>
              )}

              {/* Recommendations */}
              {dealAgeRisk.recommendations.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-zinc-400 mb-1">Recommendations</p>
                  <ul className="space-y-1">
                    {dealAgeRisk.recommendations.map((rec, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                        <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                        {rec}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs text-zinc-600">
                Generated {new Date(dealAgeRisk.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No deal age risk data available.</p>
          )
        )}
      </Card>

      {/* Phase 16q: Top Performer Deals */}
      <Card className="border-zinc-800 p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
          <Trophy className="h-4 w-4 text-emerald-400" />
          <span className="text-sm font-semibold text-zinc-200">Top Performer Deals</span>
          {topPerformers?.avg_win_rate != null && (
            <span className="rounded-full border px-2 py-0.5 text-xs text-emerald-400 bg-emerald-500/10 border-emerald-500/20">
              {topPerformers.avg_win_rate}% avg confidence
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={regenerateTopPerformers}
              disabled={topPerformersLoading}
              className="flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", topPerformersLoading && "animate-spin")} />
              {topPerformersLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setTopPerformersOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {topPerformersOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {topPerformersOpen && (
          topPerformersLoading && !topPerformers ? (
            <p className="p-4 text-xs text-zinc-500 animate-pulse">Ranking top performer deals…</p>
          ) : topPerformers ? (
            <div className={cn("space-y-4 p-4", topPerformersLoading && "opacity-40")}>
              {/* 3-tab switcher */}
              <div className="flex gap-1 rounded-lg bg-zinc-800/60 p-1">
                {(['value', 'speed', 'confidence'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setTopPerformersTab(tab)}
                    className={cn(
                      "flex-1 rounded-md px-2 py-1 text-xs capitalize transition-colors",
                      topPerformersTab === tab
                        ? "bg-zinc-700 text-zinc-100"
                        : "text-zinc-500 hover:text-zinc-300"
                    )}
                  >
                    {tab === 'value' ? 'By Value' : tab === 'speed' ? 'By Speed' : 'By Confidence'}
                  </button>
                ))}
              </div>
              {/* Deal list for active tab */}
              {(() => {
                const deals =
                  topPerformersTab === 'value' ? topPerformers.top_by_value
                  : topPerformersTab === 'speed' ? topPerformers.top_by_speed
                  : topPerformers.top_by_confidence;
                if (!deals.length) return <p className="text-xs text-zinc-500">No deals to show.</p>;
                return (
                  <div className="space-y-1.5">
                    {deals.map((deal, idx) => (
                      <div key={deal.id} className="flex items-center gap-2 rounded-md bg-zinc-800/50 px-2 py-1.5">
                        <span className="text-xs font-mono text-zinc-600 w-4">{idx + 1}</span>
                        <span className="text-xs text-zinc-300 flex-1 truncate">{deal.title ?? "Untitled"}</span>
                        <span className="text-xs text-zinc-500 truncate max-w-[80px]">{deal.company}</span>
                        <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-xs font-mono text-emerald-300">
                          ${deal.value >= 1000 ? `${Math.round(deal.value / 1000)}k` : deal.value}
                        </span>
                        {topPerformersTab === 'speed' && deal.cycle_days != null && (
                          <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-1.5 py-0.5 text-xs font-mono text-indigo-300">
                            {deal.cycle_days}d
                          </span>
                        )}
                        {topPerformersTab === 'confidence' && (
                          <span className="rounded-full border border-violet-500/20 bg-violet-500/10 px-1.5 py-0.5 text-xs font-mono text-violet-300">
                            {deal.win_probability}%
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })()}
              <p className="text-xs text-zinc-400 italic">{topPerformers.insight}</p>
              <ul className="space-y-1">
                {topPerformers.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(topPerformers.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No top performer data available.</p>
          )
        )}
      </Card>

      {/* Stage Concentration AI Card */}
      <Card className="border-violet-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-violet-400" />
            <span className="text-sm font-semibold text-zinc-100">Stage Concentration</span>
            {stageConcentration && (
              <span className="rounded-full border border-violet-500/20 bg-violet-500/10 px-2 py-0.5 text-xs font-mono text-violet-300">
                ${stageConcentration.total_pipeline_value >= 1000
                  ? `${(stageConcentration.total_pipeline_value / 1000).toFixed(0)}k`
                  : stageConcentration.total_pipeline_value}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateStageConcentration}
              disabled={stageConcentrationLoading}
              className="flex items-center gap-1 rounded-md bg-zinc-700/50 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              <RefreshCw className={`h-3 w-3 ${stageConcentrationLoading ? "animate-spin" : ""}`} />
              Regenerate
            </button>
            <button
              onClick={() => setStageConcentrationOpen(o => !o)}
              className="rounded-md p-1 text-zinc-400 hover:bg-zinc-700/50"
            >
              <ChevronDown className={`h-4 w-4 transition-transform ${stageConcentrationOpen ? "" : "-rotate-90"}`} />
            </button>
          </div>
        </div>
        {stageConcentrationOpen && (
          stageConcentrationLoading ? (
            <div className="mt-3 space-y-2">
              {[1, 2, 3].map(i => <div key={i} className="h-4 rounded bg-zinc-800/50 animate-pulse" />)}
            </div>
          ) : stageConcentration ? (
            <div className="mt-3 space-y-3">
              {/* Stacked bar */}
              <div className="flex h-5 w-full overflow-hidden rounded-full">
                {stageConcentration.stages.map((s, i) => {
                  const colors = ["bg-violet-500", "bg-indigo-500", "bg-sky-500", "bg-teal-500"];
                  return (
                    <div
                      key={s.stage}
                      className={`${colors[i % colors.length]} transition-all`}
                      style={{ width: `${s.pct_of_pipeline}%` }}
                      title={`${s.stage}: ${s.pct_of_pipeline.toFixed(1)}%`}
                    />
                  );
                })}
              </div>
              {/* Legend / per-stage rows */}
              <div className="space-y-1">
                {stageConcentration.stages.map((s, i) => {
                  const colors = ["text-violet-300 border-violet-500/20 bg-violet-500/10", "text-indigo-300 border-indigo-500/20 bg-indigo-500/10", "text-sky-300 border-sky-500/20 bg-sky-500/10", "text-teal-300 border-teal-500/20 bg-teal-500/10"];
                  const dotColors = ["bg-violet-400", "bg-indigo-400", "bg-sky-400", "bg-teal-400"];
                  const isHighValue = s.stage === stageConcentration.highest_value_stage;
                  const isStalled = s.stage === stageConcentration.most_stalled_stage;
                  return (
                    <div key={s.stage} className="flex items-center gap-2 rounded-md bg-zinc-800/40 px-2 py-1.5">
                      <span className={`h-2 w-2 flex-shrink-0 rounded-full ${dotColors[i % dotColors.length]}`} />
                      <span className="text-xs text-zinc-300 w-24 capitalize">{s.stage}</span>
                      <span className={`rounded-full border px-1.5 py-0.5 text-xs font-mono ${colors[i % colors.length]}`}>
                        {s.pct_of_pipeline.toFixed(1)}%
                      </span>
                      <span className="text-xs text-zinc-500 flex-1">{s.count} deal{s.count !== 1 ? "s" : ""}</span>
                      <span className="text-xs font-mono text-zinc-400">
                        ${s.total_value >= 1000 ? `${(s.total_value / 1000).toFixed(0)}k` : s.total_value}
                      </span>
                      {s.avg_health != null && (
                        <span className={`text-xs font-mono ${s.avg_health >= 70 ? "text-emerald-400" : s.avg_health >= 50 ? "text-amber-400" : "text-rose-400"}`}>
                          h{Math.round(s.avg_health)}
                        </span>
                      )}
                      {isHighValue && <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-1 py-0.5 text-xs text-emerald-400">top $</span>}
                      {isStalled && <span className="rounded-full border border-rose-500/20 bg-rose-500/10 px-1 py-0.5 text-xs text-rose-400">stalled</span>}
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-zinc-400 italic">{stageConcentration.insight}</p>
              <ul className="space-y-1">
                {stageConcentration.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(stageConcentration.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No stage concentration data available.</p>
          )
        )}
      </Card>

      {/* Close Rate by Stage */}
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 p-4 border-b border-zinc-800/60">
          <BarChart2 className="h-4 w-4 text-indigo-400 flex-shrink-0" />
          <h2 className="text-sm font-semibold text-zinc-200">Close Rate by Stage</h2>
          {closeRateByStage?.best_converting_stage && (
            <span className="rounded-full border px-2 py-0.5 text-xs text-emerald-400 bg-emerald-500/10 border-emerald-500/20">
              Best: {closeRateByStage.best_converting_stage}
            </span>
          )}
          {closeRateByStage?.worst_converting_stage && (
            <span className="rounded-full border px-2 py-0.5 text-xs text-rose-400 bg-rose-500/10 border-rose-500/20">
              Worst: {closeRateByStage.worst_converting_stage}
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={regenerateCloseRateByStage}
              disabled={closeRateByStageLoading}
              className="flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", closeRateByStageLoading && "animate-spin")} />
              {closeRateByStageLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setCloseRateByStageOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {closeRateByStageOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {closeRateByStageOpen && (
          closeRateByStageLoading && !closeRateByStage ? (
            <p className="p-4 text-xs text-zinc-500 animate-pulse">Analysing close rates by stage…</p>
          ) : closeRateByStage ? (
            <div className={cn("space-y-4 p-4", closeRateByStageLoading && "opacity-40")}>
              {closeRateByStage.stage_rates.length > 0 ? (
                <div className="space-y-2">
                  {closeRateByStage.stage_rates.map((s) => {
                    const isBest = s.stage === closeRateByStage.best_converting_stage;
                    const isWorst = s.stage === closeRateByStage.worst_converting_stage;
                    return (
                      <div key={s.stage} className="flex items-center gap-3">
                        <span className="w-24 flex-shrink-0 text-xs capitalize text-zinc-400">{s.stage}</span>
                        <div className="flex-1 h-4 rounded-full bg-zinc-800 overflow-hidden relative">
                          <div
                            className={cn("h-full rounded-full transition-all", isBest ? "bg-emerald-500" : isWorst ? "bg-rose-500" : "bg-indigo-500")}
                            style={{ width: `${s.win_rate}%` }}
                          />
                        </div>
                        <span className={cn("w-12 flex-shrink-0 text-right text-xs font-mono", isBest ? "text-emerald-400" : isWorst ? "text-rose-400" : "text-zinc-300")}>
                          {s.win_rate}%
                        </span>
                        <span className="text-xs text-zinc-500 flex-shrink-0">{s.win_count}W/{s.loss_count}L</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No closed deals to analyse yet.</p>
              )}
              <p className="text-xs text-zinc-400 italic">{closeRateByStage.insight}</p>
              <ul className="space-y-1">
                {closeRateByStage.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(closeRateByStage.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No close rate data available.</p>
          )
        )}
      </Card>

      {/* Pipeline Churn */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-rose-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Pipeline Churn</h3>
            {pipelineChurn?.highest_churn_stage && (
              <span className="text-xs px-2 py-0.5 rounded-full border bg-rose-500/10 border-rose-500/20 text-rose-400">
                Highest: {pipelineChurn.highest_churn_stage}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regeneratePipelineChurn}
              disabled={pipelineChurnLoading}
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", pipelineChurnLoading && "animate-spin")} />
              {pipelineChurnLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setPipelineChurnOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {pipelineChurnOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {pipelineChurnOpen && (
          pipelineChurnLoading && !pipelineChurn ? (
            <div className="p-4 space-y-2 animate-pulse">
              {[1,2,3,4].map((i) => <div key={i} className="h-8 rounded bg-zinc-800" />)}
            </div>
          ) : pipelineChurn ? (
            <div className={cn("space-y-4 p-4", pipelineChurnLoading && "opacity-40")}>
              {pipelineChurn.stage_churn.length > 0 ? (
                <div className="space-y-2">
                  {pipelineChurn.stage_churn.map((s) => {
                    const isHighest = s.stage === pipelineChurn.highest_churn_stage;
                    const barColor = s.churn_rate >= 40 ? "bg-rose-500" : s.churn_rate >= 20 ? "bg-amber-500" : "bg-zinc-600";
                    return (
                      <div key={s.stage} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-1.5">
                            <span className={cn("font-medium capitalize", isHighest ? "text-rose-400" : "text-zinc-300")}>
                              {s.stage}
                            </span>
                            {isHighest && (
                              <span className="text-[10px] px-1.5 py-px rounded border bg-rose-500/10 border-rose-500/20 text-rose-400">
                                Highest churn
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-zinc-400">
                            <span>{s.churned_count}/{s.total_entered} deals</span>
                            <span className={cn("font-semibold", s.churn_rate >= 40 ? "text-rose-400" : s.churn_rate >= 20 ? "text-amber-400" : "text-zinc-300")}>
                              {s.churn_rate}%
                            </span>
                          </div>
                        </div>
                        <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className={cn("h-full rounded-full transition-all", barColor)}
                            style={{ width: `${Math.min(s.churn_rate, 100)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No deal movement data available yet.</p>
              )}
              <p className="text-xs text-zinc-400 italic">{pipelineChurn.insight}</p>
              <ul className="space-y-1.5">
                {pipelineChurn.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(pipelineChurn.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No pipeline churn data available.</p>
          )
        )}
      </Card>

      {/* Conversion Quality */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-semibold text-zinc-200">Conversion Quality</span>
            {conversionQuality && (
              <span className="text-xs text-zinc-500">
                Avg score: <span className="text-emerald-400 font-semibold">{conversionQuality.avg_quality_score}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateConversionQuality}
              disabled={conversionQualityLoading}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <RefreshCw className={cn("h-3 w-3", conversionQualityLoading && "animate-spin")} />
              {conversionQualityLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setConversionQualityOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {conversionQualityOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {conversionQualityOpen && (
          conversionQualityLoading && !conversionQuality ? (
            <div className="h-24 animate-pulse bg-zinc-800/40 m-4 rounded" />
          ) : conversionQuality ? (
            <div className={cn("space-y-4 p-4", conversionQualityLoading && "opacity-40")}>
              {/* Tier bars */}
              <div className="space-y-2">
                {conversionQuality.quality_tiers.map((tier) => {
                  const total = conversionQuality.quality_tiers.reduce((s, t) => s + t.count, 0);
                  const pct = total > 0 ? Math.round((tier.count / total) * 100) : 0;
                  const tierConfig: Record<string, { label: string; color: string; bar: string }> = {
                    high:   { label: "High",   color: "text-emerald-400", bar: "bg-emerald-500" },
                    medium: { label: "Medium", color: "text-amber-400",   bar: "bg-amber-500"   },
                    low:    { label: "Low",    color: "text-rose-400",    bar: "bg-rose-500"    },
                  };
                  const cfg = tierConfig[tier.tier] ?? { label: tier.tier, color: "text-zinc-400", bar: "bg-zinc-500" };
                  return (
                    <div key={tier.tier}>
                      <div className="flex items-center justify-between mb-1">
                        <span className={cn("text-xs font-medium", cfg.color)}>{cfg.label}</span>
                        <span className="text-xs text-zinc-400">
                          {tier.count} deal{tier.count !== 1 ? "s" : ""} · avg ${tier.avg_value.toLocaleString()} · {tier.avg_cycle_days}d · health {tier.avg_health}
                        </span>
                      </div>
                      <div className="h-2 w-full rounded bg-zinc-800">
                        <div className={cn("h-2 rounded", cfg.bar)} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-zinc-400 italic">{conversionQuality.insight}</p>
              <ul className="space-y-1">
                {conversionQuality.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(conversionQuality.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No conversion quality data available.</p>
          )
        )}
      </Card>

      {/* Win/Loss Patterns */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-rose-400" />
            <span className="text-sm font-semibold text-zinc-200">Win/Loss Patterns</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateWinLossPatterns}
              disabled={winLossPatternsLoading}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <RefreshCw className={cn("h-3 w-3", winLossPatternsLoading && "animate-spin")} />
              {winLossPatternsLoading ? "Generating…" : "Regenerate"}
            </button>
            <button onClick={() => setWinLossPatternsOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {winLossPatternsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {winLossPatternsOpen && (
          winLossPatternsLoading && !winLossPatterns ? (
            <div className="h-24 animate-pulse bg-zinc-800/40 m-4 rounded" />
          ) : winLossPatterns ? (
            <div className={cn("space-y-4 p-4", winLossPatternsLoading && "opacity-40")}>
              {/* Per-stage bars */}
              <div className="space-y-2">
                {winLossPatterns.stage_patterns.map((p) => (
                  <div key={p.stage}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-zinc-300 capitalize">{p.stage.replace(/_/g, " ")}</span>
                      <span className="text-xs text-zinc-400">
                        {p.won}W / {p.lost}L · <span className={p.win_rate >= 60 ? "text-emerald-400" : p.win_rate >= 40 ? "text-amber-400" : "text-rose-400"}>{p.win_rate}%</span>
                      </span>
                    </div>
                    <div className="h-2 w-full rounded bg-zinc-800 flex overflow-hidden">
                      <div
                        className="h-2 bg-emerald-500"
                        style={{ width: `${(p.won / Math.max(p.won + p.lost, 1)) * 100}%` }}
                      />
                      <div
                        className="h-2 bg-rose-500"
                        style={{ width: `${(p.lost / Math.max(p.won + p.lost, 1)) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              {/* Competitor impact */}
              <div className="rounded-lg bg-zinc-800/50 border border-zinc-700/40 p-3 space-y-1">
                <p className="text-xs font-medium text-zinc-300">Competitor Impact</p>
                <div className="flex items-center justify-between text-xs text-zinc-400">
                  <span>With competitors</span>
                  <span className={winLossPatterns.competitor_impact.with_competitors_win_rate >= 50 ? "text-emerald-400" : "text-rose-400"}>
                    {winLossPatterns.competitor_impact.with_competitors_win_rate}% win rate
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-zinc-400">
                  <span>Without competitors</span>
                  <span className={winLossPatterns.competitor_impact.without_competitors_win_rate >= 50 ? "text-emerald-400" : "text-rose-400"}>
                    {winLossPatterns.competitor_impact.without_competitors_win_rate}% win rate
                  </span>
                </div>
              </div>
              <p className="text-xs text-zinc-400 italic">{winLossPatterns.insight}</p>
              <ul className="space-y-1">
                {winLossPatterns.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(winLossPatterns.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No win/loss pattern data available.</p>
          )
        )}
      </Card>

      {/* Avg Deal Size Trend */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-semibold text-zinc-200">Avg Deal Size Trend</span>
            {avgDealSizeTrend && (() => {
              const TREND_CFG: Record<string, { label: string; color: string }> = {
                accelerating: { label: "Accelerating", color: "text-emerald-400" },
                growing:      { label: "Growing",      color: "text-indigo-400"  },
                stable:       { label: "Stable",       color: "text-zinc-400"    },
                declining:    { label: "Declining",    color: "text-rose-400"    },
              };
              const cfg = TREND_CFG[avgDealSizeTrend.trend_direction] ?? { label: avgDealSizeTrend.trend_direction, color: "text-zinc-400" };
              return (
                <span className={cn("text-xs font-medium", cfg.color)}>
                  {cfg.label} ({avgDealSizeTrend.pct_change > 0 ? "+" : ""}{avgDealSizeTrend.pct_change}%)
                </span>
              );
            })()}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateAvgDealSizeTrend}
              disabled={avgDealSizeTrendLoading}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", avgDealSizeTrendLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setAvgDealSizeTrendOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {avgDealSizeTrendOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {avgDealSizeTrendOpen && (
          avgDealSizeTrendLoading && !avgDealSizeTrend ? (
            <div className="h-24 animate-pulse bg-zinc-800/40 m-4 rounded" />
          ) : avgDealSizeTrend && avgDealSizeTrend.months.length > 0 ? (
            <div className={cn("space-y-4 p-4", avgDealSizeTrendLoading && "opacity-40")}>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={avgDealSizeTrend.months} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
                  <XAxis dataKey="month" tick={{ fill: "#a1a1aa", fontSize: 10 }} />
                  <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fill: "#a1a1aa", fontSize: 10 }} width={44} />
                  <Tooltip
                    formatter={(v: unknown) => [`$${Number(v ?? 0).toLocaleString()}`, "Avg Deal Size"]}
                    contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8, fontSize: 11 }}
                    labelStyle={{ color: "#a1a1aa" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="avg_value"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={(props) => {
                      const { cx, cy, payload } = props as { cx: number; cy: number; payload: AvgDealSizeMonth };
                      const isBest = payload.month === avgDealSizeTrend.best_month;
                      return <circle key={payload.month} cx={cx} cy={cy} r={isBest ? 5 : 3} fill={isBest ? "#f59e0b" : "#10b981"} stroke="none" />;
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
              {avgDealSizeTrend.best_month && (
                <p className="text-xs text-amber-400">
                  Best month: <span className="font-semibold">{avgDealSizeTrend.best_month}</span> · ${avgDealSizeTrend.months.find((m) => m.month === avgDealSizeTrend.best_month)?.avg_value.toLocaleString()} avg
                </p>
              )}
              <p className="text-xs text-zinc-400 italic">{avgDealSizeTrend.insight}</p>
              <ul className="space-y-1">
                {avgDealSizeTrend.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(avgDealSizeTrend.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : avgDealSizeTrend && avgDealSizeTrend.months.length === 0 ? (
            <div className={cn("p-4 space-y-3", avgDealSizeTrendLoading && "opacity-40")}>
              <p className="text-xs text-zinc-400 italic">{avgDealSizeTrend.insight}</p>
              <ul className="space-y-1">
                {avgDealSizeTrend.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No avg deal size trend data available.</p>
          )
        )}
      </Card>

      {/* Follow-up Gap Analysis */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-amber-400" />
            <span className="text-sm font-semibold text-zinc-200">Follow-up Gap Analysis</span>
            {followupGaps && (
              <span className={cn("text-xs font-medium", followupGaps.overdue.length > 0 ? "text-rose-400" : "text-emerald-400")}>
                {followupGaps.overdue.length > 0
                  ? `${followupGaps.overdue.length} overdue`
                  : "All on track"}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateFollowupGaps}
              disabled={followupGapsLoading}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", followupGapsLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setFollowupGapsOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {followupGapsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {followupGapsOpen && (
          followupGapsLoading && !followupGaps ? (
            <div className="h-24 animate-pulse bg-zinc-800/40 m-4 rounded" />
          ) : followupGaps ? (
            <div className={cn("space-y-4 p-4", followupGapsLoading && "opacity-40")}>
              {/* 3-bucket summary row */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-3 text-center">
                  <p className="text-xl font-bold text-rose-400">{followupGaps.overdue.length}</p>
                  <p className="text-xs text-zinc-400 mt-0.5">Overdue &gt;14d</p>
                </div>
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-center">
                  <p className="text-xl font-bold text-amber-400">{followupGaps.due_soon.length}</p>
                  <p className="text-xs text-zinc-400 mt-0.5">Due soon 7–14d</p>
                </div>
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-center">
                  <p className="text-xl font-bold text-emerald-400">{followupGaps.on_track_count}</p>
                  <p className="text-xs text-zinc-400 mt-0.5">On track &lt;7d</p>
                </div>
              </div>
              <p className="text-xs text-zinc-500">Avg {followupGaps.avg_days_since_contact}d since last contact</p>
              {/* Overdue deals */}
              {followupGaps.overdue.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-rose-400 mb-1">Overdue</p>
                  <ul className="space-y-1">
                    {followupGaps.overdue.map((d) => (
                      <li key={d.deal_id} className="flex items-center justify-between rounded bg-zinc-800/50 px-3 py-1.5">
                        <div>
                          <span className="text-xs text-zinc-200 font-medium">{d.title}</span>
                          {d.company && <span className="text-xs text-zinc-500 ml-1">· {d.company}</span>}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-zinc-400 capitalize">{d.stage.replace("_", " ")}</span>
                          <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-xs font-mono text-rose-300">{d.days_since_contact}d</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {/* Due soon deals */}
              {followupGaps.due_soon.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-amber-400 mb-1">Due soon</p>
                  <ul className="space-y-1">
                    {followupGaps.due_soon.map((d) => (
                      <li key={d.deal_id} className="flex items-center justify-between rounded bg-zinc-800/50 px-3 py-1.5">
                        <div>
                          <span className="text-xs text-zinc-200 font-medium">{d.title}</span>
                          {d.company && <span className="text-xs text-zinc-500 ml-1">· {d.company}</span>}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-zinc-400 capitalize">{d.stage.replace("_", " ")}</span>
                          <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs font-mono text-amber-300">{d.days_since_contact}d</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-zinc-400 italic">{followupGaps.insight}</p>
              <ul className="space-y-1">
                {followupGaps.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(followupGaps.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No follow-up gap data available.</p>
          )
        )}
      </Card>

      {/* Value at Risk */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-rose-400" />
            <span className="text-sm font-semibold text-zinc-200">Value at Risk</span>
            {valueAtRisk && (
              <span className={cn("text-xs font-medium", valueAtRisk.at_risk_pct > 30 ? "text-rose-400" : valueAtRisk.at_risk_pct > 15 ? "text-amber-400" : "text-emerald-400")}>
                {valueAtRisk.at_risk_pct.toFixed(1)}% at risk
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateValueAtRisk}
              disabled={valueAtRiskLoading}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", valueAtRiskLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setValueAtRiskOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {valueAtRiskOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {valueAtRiskOpen && (
          valueAtRiskLoading && !valueAtRisk ? (
            <div className="h-24 animate-pulse bg-zinc-800/40 m-4 rounded" />
          ) : valueAtRisk ? (
            <div className={cn("space-y-4 p-4", valueAtRiskLoading && "opacity-40")}>
              {/* Pipeline summary row */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-3 text-center">
                  <p className="text-xl font-bold text-rose-400">{valueAtRisk.at_risk_pct.toFixed(1)}%</p>
                  <p className="text-xs text-zinc-400 mt-0.5">At Risk</p>
                </div>
                <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 text-center">
                  <p className="text-xl font-bold text-zinc-200">${(valueAtRisk.at_risk_value / 1000).toFixed(0)}K</p>
                  <p className="text-xs text-zinc-400 mt-0.5">At-Risk Value</p>
                </div>
                <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 text-center">
                  <p className="text-xl font-bold text-zinc-200">${(valueAtRisk.total_pipeline_value / 1000).toFixed(0)}K</p>
                  <p className="text-xs text-zinc-400 mt-0.5">Total Pipeline</p>
                </div>
              </div>
              {/* At-risk deal list */}
              {valueAtRisk.at_risk_deals.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-rose-400 mb-1">At-Risk Deals</p>
                  <ul className="space-y-1 max-h-48 overflow-y-auto">
                    {valueAtRisk.at_risk_deals.map((d) => (
                      <li key={d.deal_id} className="flex items-start justify-between rounded bg-zinc-800/50 px-3 py-2 gap-2">
                        <div className="min-w-0">
                          <span className="text-xs text-zinc-200 font-medium">{d.title}</span>
                          {d.company && <span className="text-xs text-zinc-500 ml-1">· {d.company}</span>}
                          <p className="text-xs text-zinc-500 mt-0.5 truncate">{d.risk_reason}</p>
                        </div>
                        <div className="flex flex-col items-end gap-1 flex-shrink-0">
                          <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-xs font-mono text-rose-300">${(d.value / 1000).toFixed(0)}K</span>
                          <span className={cn("rounded px-1.5 py-0.5 text-xs font-mono", d.health_score < 40 ? "bg-rose-500/20 text-rose-300" : "bg-amber-500/20 text-amber-300")}>
                            {d.health_score}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-zinc-400 italic">{valueAtRisk.insight}</p>
              <ul className="space-y-1">
                {valueAtRisk.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(valueAtRisk.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No value at risk data available.</p>
          )
        )}
      </Card>

      {/* Next Best Actions */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-indigo-400" />
            <span className="text-sm font-semibold text-zinc-200">Next Best Actions</span>
            {nextBestActions && (
              <span className="text-xs font-medium text-indigo-400">
                {nextBestActions.actions.filter((a) => a.priority === 'high').length} high priority
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateNextBestActions}
              disabled={nextBestActionsLoading}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", nextBestActionsLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setNextBestActionsOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {nextBestActionsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {nextBestActionsOpen && (
          nextBestActionsLoading && !nextBestActions ? (
            <div className="h-24 animate-pulse bg-zinc-800/40 m-4 rounded" />
          ) : nextBestActions && nextBestActions.actions.length > 0 ? (
            <div className={cn("space-y-4 p-4", nextBestActionsLoading && "opacity-40")}>
              <ul className="space-y-2">
                {nextBestActions.actions.map((a, i) => (
                  <li key={a.deal_id + i} className="flex items-start gap-3 rounded bg-zinc-800/50 px-3 py-2">
                    <span className={cn(
                      "mt-0.5 rounded px-1.5 py-0.5 text-xs font-semibold flex-shrink-0",
                      a.priority === 'high' ? "bg-rose-500/20 text-rose-300" :
                      a.priority === 'medium' ? "bg-amber-500/20 text-amber-300" :
                      "bg-emerald-500/20 text-emerald-300"
                    )}>
                      {a.priority}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs text-zinc-200 font-medium">{a.action}</p>
                      {a.rationale && <p className="text-xs text-zinc-500 mt-0.5">{a.rationale}</p>}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-400 italic">{nextBestActions.insight}</p>
              <ul className="space-y-1">
                {nextBestActions.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(nextBestActions.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : nextBestActions && nextBestActions.actions.length === 0 ? (
            <div className={cn("p-4 space-y-3", nextBestActionsLoading && "opacity-40")}>
              <p className="text-xs text-zinc-400 italic">{nextBestActions.insight}</p>
              <ul className="space-y-1">
                {nextBestActions.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No next best actions data available.</p>
          )
        )}
      </Card>

      {/* Weekly Coaching Digest */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-indigo-400" />
            <span className="text-sm font-semibold text-zinc-200">Weekly Coaching Digest</span>
            {coachingDigest && (
              <span className="text-xs font-medium text-indigo-400">
                {coachingDigest.coached_deals.length} deal{coachingDigest.coached_deals.length !== 1 ? "s" : ""} coached
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateCoachingDigest}
              disabled={coachingDigestLoading}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", coachingDigestLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setCoachingDigestOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {coachingDigestOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {coachingDigestOpen && (
          coachingDigestLoading && !coachingDigest ? (
            <div className="h-24 animate-pulse bg-zinc-800/40 m-4 rounded" />
          ) : coachingDigest && coachingDigest.coached_deals.length > 0 ? (
            <div className={cn("space-y-4 p-4", coachingDigestLoading && "opacity-40")}>
              {/* Weekly theme banner */}
              <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/10 px-3 py-2">
                <p className="text-xs text-indigo-300 font-medium">{coachingDigest.weekly_theme}</p>
              </div>
              {/* Coached deals */}
              <ul className="space-y-2">
                {coachingDigest.coached_deals.map((d) => (
                  <li key={d.deal_id} className="rounded border border-zinc-700/50 bg-zinc-800/30 overflow-hidden">
                    <button
                      onClick={() => setCoachingExpandedDeal((prev) => prev === d.deal_id ? null : d.deal_id)}
                      className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-zinc-800/60"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-zinc-200 font-medium">{d.title}</span>
                        <span className="text-xs text-zinc-500 capitalize">{d.stage.replace("_", " ")}</span>
                        <span className="rounded bg-zinc-700 px-1.5 py-0.5 text-xs font-mono text-zinc-300">${(d.value / 1000).toFixed(0)}K</span>
                      </div>
                      {coachingExpandedDeal === d.deal_id ? <ChevronUp className="h-3 w-3 text-zinc-400 flex-shrink-0" /> : <ChevronDown className="h-3 w-3 text-zinc-400 flex-shrink-0" />}
                    </button>
                    {coachingExpandedDeal === d.deal_id && (
                      <div className="px-3 pb-3 space-y-3 border-t border-zinc-700/50 pt-2">
                        <div>
                          <p className="text-xs font-semibold text-emerald-400 mb-1">What to do this week</p>
                          <p className="text-xs text-zinc-300">{d.what_to_do}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-rose-400 mb-1">What to avoid</p>
                          <p className="text-xs text-zinc-300">{d.what_to_avoid}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-amber-400 mb-1">Talking points</p>
                          <ul className="space-y-1">
                            {d.talking_points.map((tp, i) => (
                              <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                                <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                                {tp}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-400 italic">{coachingDigest.weekly_theme}</p>
              <ul className="space-y-1">
                {coachingDigest.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(coachingDigest.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : coachingDigest && coachingDigest.coached_deals.length === 0 ? (
            <div className={cn("p-4 space-y-3", coachingDigestLoading && "opacity-40")}>
              <p className="text-xs text-zinc-400 italic">{coachingDigest.weekly_theme}</p>
              <ul className="space-y-1">
                {coachingDigest.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No coaching digest data available.</p>
          )
        )}
      </Card>

      {/* Deal Momentum Tracker */}
      <Card className="border-blue-500/15">
        <div className="flex items-center justify-between p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-blue-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Deal Momentum</h3>
            {momentum && (
              <span className="text-xs bg-blue-900/40 text-blue-300 px-2 py-0.5 rounded-full border border-blue-700/30">
                Index: {momentum.momentum_index}/100
              </span>
            )}
            {momentum && (
              <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full border border-zinc-700">
                {momentum.accelerating.length}↑ {momentum.decelerating.length}↓ {momentum.stalled.length}⏸
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateMomentum}
              disabled={momentumLoading}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", momentumLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setMomentumOpen(!momentumOpen)}>
              {momentumOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {momentumOpen && (
          momentumLoading && !momentum ? (
            <div className="p-6 text-center text-xs text-zinc-500 animate-pulse">Analysing deal momentum…</div>
          ) : momentum ? (
            <div className={cn("p-4 space-y-4", momentumLoading && "opacity-40")}>
              {momentum.accelerating.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-emerald-400 mb-2">Accelerating ({momentum.accelerating.length})</p>
                  <div className="space-y-1">
                    {momentum.accelerating.map((d) => (
                      <div key={d.deal_id} className="flex items-start gap-3 rounded-md bg-emerald-950/20 border border-emerald-800/20 p-2">
                        <span className="mt-0.5 flex-shrink-0 text-xs font-bold text-emerald-400 w-6 text-center">{d.velocity_score}</span>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-zinc-100">{d.title}</p>
                          <p className="text-xs text-zinc-400">{d.trend_description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {momentum.decelerating.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-amber-400 mb-2">Decelerating ({momentum.decelerating.length})</p>
                  <div className="space-y-1">
                    {momentum.decelerating.map((d) => (
                      <div key={d.deal_id} className="flex items-start gap-3 rounded-md bg-amber-950/20 border border-amber-800/20 p-2">
                        <span className="mt-0.5 flex-shrink-0 text-xs font-bold text-amber-400 w-6 text-center">{d.velocity_score}</span>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-zinc-100">{d.title}</p>
                          <p className="text-xs text-zinc-400">{d.trend_description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {momentum.stalled.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-rose-400 mb-2">Stalled ({momentum.stalled.length})</p>
                  <div className="space-y-1">
                    {momentum.stalled.map((d) => (
                      <div key={d.deal_id} className="flex items-start gap-3 rounded-md bg-rose-950/20 border border-rose-800/20 p-2">
                        <span className="mt-0.5 flex-shrink-0 text-xs font-bold text-rose-400 w-6 text-center">{d.velocity_score}</span>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-zinc-100">{d.title}</p>
                          <p className="text-xs text-zinc-400">{d.trend_description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="rounded-md bg-zinc-800/50 border border-zinc-700/30 p-3">
                <p className="text-xs text-zinc-300 italic">{momentum.insight}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-zinc-400 mb-1">Recommendations</p>
                <ul className="space-y-1">
                  {momentum.recommendations.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                      <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-zinc-600">Generated {new Date(momentum.generated_at).toLocaleString()} · Claude Haiku</p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No momentum data available.</p>
          )
        )}
      </Card>

      {/* Risk Escalation Digest */}
      <Card className="border-rose-500/15">
        <div className="flex items-center justify-between p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-rose-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Risk Escalation Digest</h3>
            {riskEscalation && (
              <span className="text-xs bg-rose-900/40 text-rose-300 px-2 py-0.5 rounded-full border border-rose-700/30">
                {riskEscalation.escalations.length} at-risk deal{riskEscalation.escalations.length !== 1 ? "s" : ""}
              </span>
            )}
            {riskEscalation && (
              <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full border border-zinc-700">
                ${riskEscalation.total_at_risk_value.toLocaleString()} at risk
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateRiskEscalation}
              disabled={riskEscalationLoading}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", riskEscalationLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setRiskEscalationOpen(!riskEscalationOpen)}>
              {riskEscalationOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {riskEscalationOpen && (
          riskEscalationLoading && !riskEscalation ? (
            <div className="p-6 text-center text-xs text-zinc-500 animate-pulse">Generating risk escalation digest…</div>
          ) : riskEscalation && riskEscalation.escalations.length > 0 ? (
            <div className={cn("p-4 space-y-4", riskEscalationLoading && "opacity-40")}>
              <div className="space-y-2">
                {riskEscalation.escalations.map((deal) => (
                  <div key={deal.deal_id} className="rounded-lg border border-zinc-800 bg-zinc-900/50">
                    <button
                      className="w-full flex items-center justify-between p-3 text-left"
                      onClick={() => setRiskEscalationExpanded(riskEscalationExpanded === deal.deal_id ? null : deal.deal_id)}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className={cn("inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold flex-shrink-0",
                          deal.health_score < 40 ? "bg-rose-900/60 text-rose-300" : "bg-amber-900/60 text-amber-300"
                        )}>{deal.health_score}</span>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-zinc-100 truncate">{deal.title}</p>
                          <p className="text-xs text-zinc-500">{deal.company} · {deal.stage} · ${deal.value.toLocaleString()} · {deal.days_stale}d stale</p>
                        </div>
                      </div>
                      {riskEscalationExpanded === deal.deal_id ? <ChevronUp className="h-3 w-3 text-zinc-500" /> : <ChevronDown className="h-3 w-3 text-zinc-500" />}
                    </button>
                    {riskEscalationExpanded === deal.deal_id && (
                      <div className="px-3 pb-3 space-y-3 border-t border-zinc-800 pt-3">
                        <div>
                          <p className="text-xs font-medium text-zinc-400 mb-1">Risk Factors</p>
                          <ul className="space-y-1">
                            {deal.risk_factors.map((rf, i) => (
                              <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                                <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-rose-400 flex-shrink-0" />
                                {rf}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="rounded-md bg-zinc-800/60 p-2">
                          <p className="text-xs font-medium text-zinc-400 mb-1">Suggested Action</p>
                          <p className="text-xs text-zinc-200">{deal.suggested_action}</p>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="rounded-lg bg-rose-950/30 border border-rose-800/30 p-3">
                <p className="text-xs font-semibold text-rose-300 mb-2">Total Value at Risk: ${riskEscalation.total_at_risk_value.toLocaleString()}</p>
                <ul className="space-y-1">
                  {riskEscalation.recommendations.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                      <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-zinc-600">Generated {new Date(riskEscalation.generated_at).toLocaleString()} · Claude Haiku</p>
            </div>
          ) : riskEscalation && riskEscalation.escalations.length === 0 ? (
            <div className="p-4">
              <p className="text-xs text-zinc-400 italic">No at-risk deals found. Your pipeline looks healthy!</p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No risk escalation data available.</p>
          )
        )}
      </Card>

      {/* Competitor Battle Cards */}
      <Card className="border-orange-500/15">
        <div className="flex items-center justify-between p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-orange-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Competitor Battle Cards</h3>
            {battleCard && battleCard.top_competitor && (
              <span className="text-xs bg-orange-900/40 text-orange-300 px-2 py-0.5 rounded-full border border-orange-700/30">
                Top: {battleCard.top_competitor}
              </span>
            )}
            {battleCard && (
              <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full border border-zinc-700">
                {battleCard.battle_cards.length} competitor{battleCard.battle_cards.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateBattleCard}
              disabled={battleCardLoading}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", battleCardLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setBattleCardOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {battleCardOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {battleCardOpen && (
          battleCardLoading && !battleCard ? (
            <div className="p-4 space-y-2 animate-pulse">
              {[1, 2, 3].map((i) => <div key={i} className="h-12 bg-zinc-800 rounded" />)}
            </div>
          ) : battleCard && battleCard.battle_cards.length > 0 ? (
            <div className={cn("p-4 space-y-4", battleCardLoading && "opacity-40")}>
              <div className="space-y-1">
                {battleCard.battle_cards.map((card) => (
                  <div key={card.competitor} className="rounded-lg border border-zinc-800 overflow-hidden">
                    <button
                      onClick={() => setBattleCardExpanded(battleCardExpanded === card.competitor ? null : card.competitor)}
                      className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-zinc-800/50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-semibold text-zinc-200">{card.competitor}</span>
                        <span className="text-xs text-zinc-500">{card.encounter_count} encounter{card.encounter_count !== 1 ? "s" : ""}</span>
                        {card.win_rate !== null && (
                          <span className={cn(
                            "text-xs px-1.5 py-0.5 rounded font-mono",
                            card.win_rate >= 60 ? "bg-emerald-900/40 text-emerald-300 border border-emerald-700/30" :
                            card.win_rate >= 40 ? "bg-amber-900/40 text-amber-300 border border-amber-700/30" :
                            "bg-rose-900/40 text-rose-300 border border-rose-700/30"
                          )}>
                            {card.win_rate}% win rate
                          </span>
                        )}
                      </div>
                      {battleCardExpanded === card.competitor ? <ChevronUp className="h-3 w-3 text-zinc-500" /> : <ChevronDown className="h-3 w-3 text-zinc-500" />}
                    </button>
                    {battleCardExpanded === card.competitor && (
                      <div className="px-3 pb-3 space-y-3 border-t border-zinc-800">
                        {card.positioning && (
                          <div className="pt-2">
                            <p className="text-xs text-zinc-400 italic">{card.positioning}</p>
                          </div>
                        )}
                        <div>
                          <p className="text-xs font-semibold text-emerald-400 mb-1">Key Differentiators</p>
                          <ul className="space-y-0.5">
                            {card.key_differentiators.map((d, i) => (
                              <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                                <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400 flex-shrink-0" />{d}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-amber-400 mb-1">Objection Responses</p>
                          <ul className="space-y-0.5">
                            {card.objection_responses.map((r, i) => (
                              <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                                <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-amber-400 flex-shrink-0" />{r}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div>
                <p className="text-xs font-semibold text-zinc-400 mb-1.5">Strategic Recommendations</p>
                <ul className="space-y-1">
                  {battleCard.recommendations.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                      <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-zinc-600">Generated {new Date(battleCard.generated_at).toLocaleString()} · Claude Haiku</p>
            </div>
          ) : battleCard && battleCard.battle_cards.length === 0 ? (
            <div className="p-4 space-y-2">
              <p className="text-xs text-zinc-400 italic">No competitor data found in your deals. Start tracking competitors to enable battle-card generation.</p>
              <ul className="space-y-1">
                {battleCard.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No battle card data available. Click Regenerate to generate.</p>
          )
        )}
      </Card>

      {/* Deal Playbook */}
      <Card className="border-emerald-500/15">
        <div className="flex items-center justify-between p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Deal Playbook</h3>
            {playbook && (
              <span className="text-xs bg-emerald-900/40 text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-700/30 truncate max-w-[200px]">
                {playbook.playbook_title}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regeneratePlaybook}
              disabled={playbookLoading}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", playbookLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setPlaybookOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {playbookOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {playbookOpen && (
          playbookLoading && !playbook ? (
            <div className="p-4 space-y-2 animate-pulse">
              {[1, 2, 3].map((i) => <div key={i} className="h-8 bg-zinc-800 rounded" />)}
            </div>
          ) : playbook ? (
            <div className={cn("p-4 space-y-4", playbookLoading && "opacity-40")}>
              {/* Winning profile metrics */}
              <div className="grid grid-cols-5 gap-2">
                {[
                  { label: "Won", value: playbook.winning_profile.won_count, color: "text-emerald-400" },
                  { label: "Lost", value: playbook.winning_profile.lost_count, color: "text-rose-400" },
                  { label: "Win Rate", value: `${playbook.winning_profile.win_rate}%`, color: "text-indigo-400" },
                  { label: "Avg Health", value: playbook.winning_profile.avg_health, color: "text-amber-400" },
                  { label: "Cycle Days", value: `${playbook.winning_profile.avg_cycle_days}d`, color: "text-zinc-300" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="rounded-lg bg-zinc-800/60 p-2 text-center">
                    <p className={cn("text-sm font-bold font-mono", color)}>{value}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
                  </div>
                ))}
              </div>
              {/* Key behaviors */}
              <div>
                <p className="text-xs font-semibold text-emerald-400 mb-1.5">Key Winning Behaviors</p>
                <ul className="space-y-1">
                  {playbook.key_behaviors.map((b, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                      <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
                      {b}
                    </li>
                  ))}
                </ul>
              </div>
              {/* Stage playbook accordion */}
              {playbook.stage_playbook.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-zinc-400 mb-1.5">Stage-by-Stage Playbook</p>
                  <div className="space-y-1">
                    {playbook.stage_playbook.map((entry) => (
                      <div key={entry.stage} className="rounded-lg border border-zinc-800 overflow-hidden">
                        <button
                          onClick={() => setPlaybookExpandedStage(playbookExpandedStage === entry.stage ? null : entry.stage)}
                          className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800/50 transition-colors"
                        >
                          <span className="capitalize font-mono">{entry.stage}</span>
                          {playbookExpandedStage === entry.stage ? <ChevronUp className="h-3 w-3 text-zinc-500" /> : <ChevronDown className="h-3 w-3 text-zinc-500" />}
                        </button>
                        {playbookExpandedStage === entry.stage && (
                          <div className="px-3 pb-3 space-y-2 border-t border-zinc-800">
                            <div className="pt-2">
                              <p className="text-xs font-semibold text-emerald-400 mb-1">Key Actions</p>
                              <ul className="space-y-0.5">
                                {entry.key_actions.map((a, i) => (
                                  <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-emerald-500 flex-shrink-0" />{a}
                                  </li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="text-xs font-semibold text-sky-400 mb-1">Success Signals</p>
                              <ul className="space-y-0.5">
                                {entry.success_signals.map((s, i) => (
                                  <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-sky-400 flex-shrink-0" />{s}
                                  </li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="text-xs font-semibold text-rose-400 mb-1">Common Mistakes</p>
                              <ul className="space-y-0.5">
                                {entry.common_mistakes.map((m, i) => (
                                  <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-rose-400 flex-shrink-0" />{m}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* Recommendations */}
              <div>
                <p className="text-xs font-semibold text-zinc-400 mb-1.5">Recommendations</p>
                <ul className="space-y-1">
                  {playbook.recommendations.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                      <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-zinc-600">Generated {new Date(playbook.generated_at).toLocaleString()} · Claude Haiku</p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No playbook data available. Click Regenerate to generate.</p>
          )
        )}
      </Card>

      {/* Conversion Path Analysis */}
      <Card className="border-sky-500/15">
        <div className="flex items-center justify-between p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Route className="h-4 w-4 text-sky-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Conversion Path Analysis</h3>
            {conversionPaths && conversionPaths.paths.length > 0 && (
              <span className="text-xs bg-sky-900/40 text-sky-300 px-2 py-0.5 rounded-full border border-sky-700/30">
                {conversionPaths.paths.length} path{conversionPaths.paths.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={regenerateConversionPaths}
              disabled={conversionPathsLoading}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", conversionPathsLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setConversionPathsOpen((o) => !o)} className="text-zinc-400 hover:text-zinc-200">
              {conversionPathsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {conversionPathsOpen && (
          conversionPathsLoading && !conversionPaths ? (
            <div className="p-4 space-y-2 animate-pulse">
              {[1, 2, 3].map((i) => <div key={i} className="h-8 bg-zinc-800 rounded" />)}
            </div>
          ) : conversionPaths && conversionPaths.paths.length > 0 ? (
            <div className={cn("p-4 space-y-4", conversionPathsLoading && "opacity-40")}>
              <ul className="space-y-3">
                {conversionPaths.paths.map((p, i) => (
                  <li key={i} className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      {p.stages_sequence.map((s, si) => (
                        <span key={si} className="flex items-center gap-1">
                          <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300 font-mono">{s}</span>
                          {si < p.stages_sequence.length - 1 && <ArrowRight className="h-3 w-3 text-zinc-600 flex-shrink-0" />}
                        </span>
                      ))}
                      {conversionPaths.most_common_path && JSON.stringify(p.stages_sequence) === JSON.stringify(conversionPaths.most_common_path) && (
                        <span className="text-xs bg-sky-900/40 text-sky-300 px-1.5 py-0.5 rounded border border-sky-700/30">most common</span>
                      )}
                      {conversionPaths.fastest_path && JSON.stringify(p.stages_sequence) === JSON.stringify(conversionPaths.fastest_path) && (
                        <span className="text-xs bg-emerald-900/40 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-700/30">fastest</span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-xs text-zinc-500">
                      <span>{p.deal_count} deal{p.deal_count !== 1 ? "s" : ""}</span>
                      <span>{p.win_rate}% win rate</span>
                      {p.avg_days > 0 && <span>{p.avg_days}d avg</span>}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-400 italic">{conversionPaths.insight}</p>
              <ul className="space-y-1">
                {conversionPaths.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-zinc-600">
                Generated {new Date(conversionPaths.generated_at).toLocaleString()} · Claude Haiku
              </p>
            </div>
          ) : conversionPaths && conversionPaths.paths.length === 0 ? (
            <p className="text-xs text-zinc-500 p-4 italic">{conversionPaths.insight}</p>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No conversion path data available.</p>
          )
        )}
      </Card>

      {/* QBR Summary */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-indigo-400" />
            <span className="text-sm font-semibold text-zinc-200">QBR Summary</span>
            {qbrSummary && (
              <span className="rounded-full bg-indigo-500/15 border border-indigo-500/25 px-2 py-0.5 text-xs font-medium text-indigo-300">
                {qbrSummary.quarter}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={regenerateQbrSummary}
              disabled={qbrSummaryLoading}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors disabled:opacity-40"
            >
              <RefreshCw className={cn("h-3 w-3", qbrSummaryLoading && "animate-spin")} />
              Regenerate
            </button>
            <button onClick={() => setQbrSummaryOpen((p) => !p)} className="rounded p-1 hover:bg-zinc-700 transition-colors">
              {qbrSummaryOpen ? <ChevronUp className="h-3.5 w-3.5 text-zinc-400" /> : <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />}
            </button>
          </div>
        </div>
        {qbrSummaryOpen && (
          qbrSummaryLoading && !qbrSummary ? (
            <div className="p-4 space-y-2">
              {[1,2,3].map(i => <div key={i} className="h-3 rounded bg-zinc-700/50 animate-pulse" style={{width: `${70 + i * 8}%`}} />)}
            </div>
          ) : qbrSummary ? (
            <div className={cn("p-4 space-y-4", qbrSummaryLoading && "opacity-50")}>
              {/* Metrics row */}
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "Won", value: qbrSummary.metrics.closed_won_count, suffix: " deals", color: "text-emerald-400" },
                  { label: "Revenue", value: `$${(qbrSummary.metrics.closed_won_revenue / 1000).toFixed(0)}K`, color: "text-emerald-300" },
                  { label: "Win Rate", value: `${qbrSummary.metrics.win_rate}%`, color: "text-indigo-400" },
                  { label: "Pipeline", value: `$${(qbrSummary.metrics.total_pipeline_value / 1000).toFixed(0)}K`, color: "text-zinc-300" },
                ].map(({ label, value, suffix, color }) => (
                  <div key={label} className="rounded-lg bg-zinc-800/60 p-2 text-center">
                    <p className={cn("text-sm font-bold font-mono", color)}>{value}{suffix ?? ""}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
                  </div>
                ))}
              </div>
              {/* Wins & Pipeline narrative */}
              <div className="rounded-lg bg-emerald-500/8 border border-emerald-500/15 p-3">
                <p className="text-xs font-semibold text-emerald-400 mb-1">Wins This Quarter</p>
                <p className="text-xs text-zinc-300">{qbrSummary.wins_summary}</p>
              </div>
              <div className="rounded-lg bg-amber-500/8 border border-amber-500/15 p-3">
                <p className="text-xs font-semibold text-amber-400 mb-1">Pipeline Status</p>
                <p className="text-xs text-zinc-300">{qbrSummary.pipeline_status}</p>
              </div>
              {/* Top Wins / Top Risks two-column */}
              {(qbrSummary.top_wins.length > 0 || qbrSummary.top_risks.length > 0) && (
                <div className="grid grid-cols-2 gap-3">
                  {qbrSummary.top_wins.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-emerald-400 mb-1.5">Top Wins</p>
                      <ul className="space-y-1.5">
                        {qbrSummary.top_wins.map((w) => (
                          <li key={w.id} className="flex items-center gap-2 text-xs">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
                            <span className="text-zinc-200 truncate">{w.title}</span>
                            <span className="ml-auto font-mono text-emerald-300 flex-shrink-0">${(w.value / 1000).toFixed(0)}K</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {qbrSummary.top_risks.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-rose-400 mb-1.5">Top Risks</p>
                      <ul className="space-y-1.5">
                        {qbrSummary.top_risks.map((r) => (
                          <li key={r.id} className="flex items-center gap-2 text-xs">
                            <span className="h-1.5 w-1.5 rounded-full bg-rose-400 flex-shrink-0" />
                            <span className="text-zinc-200 truncate">{r.title}</span>
                            <span className={cn("ml-auto font-mono flex-shrink-0", r.health_score < 40 ? "text-rose-400" : "text-amber-400")}>h:{r.health_score}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
              {/* Strategic recommendations */}
              <div>
                <p className="text-xs font-semibold text-zinc-400 mb-1.5">Strategic Recommendations</p>
                <ul className="space-y-1">
                  {qbrSummary.strategic_recommendations.map((rec, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                      <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-zinc-600">Generated {new Date(qbrSummary.generated_at).toLocaleString()} · Claude Haiku</p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500 p-4">No QBR data available. Click Regenerate to generate.</p>
          )
        )}
      </Card>

      {/* Stale alert */}
      {stats.stale > 0 && (
        <Card className="border-rose-500/15 flex items-center gap-3">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-zinc-300">
            <span className="font-semibold text-rose-400">{stats.stale} deal{stats.stale !== 1 ? "s" : ""}</span> with health score below 40 — check Deal Health Alerts on the Dashboard or review each deal in the Pipeline.
          </p>
        </Card>
      )}
    </div>
  );
}
