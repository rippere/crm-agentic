import type {
  Contact,
  Deal,
  Agent,
  ActivityEvent,
  KPI,
  Workspace,
} from './types'

// ─── Workspace ────────────────────────────────────────────────────────────────
export const demoWorkspace: Workspace = {
  id: 'demo-workspace-1',
  name: 'Acme Corp',
  slug: 'acme-corp',
  mode: 'both' as const,
  created_at: new Date().toISOString(),
}

// ─── Contacts ─────────────────────────────────────────────────────────────────
export const demoContacts: Contact[] = [
  {
    id: 'c-001',
    name: 'Sarah Chen',
    email: 'sarah.chen@techcorp.com',
    company: 'TechCorp Solutions',
    role: 'VP of Engineering',
    avatar: 'SC',
    status: 'customer',
    mlScore: {
      value: 91,
      label: 'hot',
      trend: 'up',
      signals: ['3 meetings in 30 days', 'Opened 8/10 emails', 'Champion identified'],
    },
    semanticTags: [
      { label: 'enterprise', confidence: 0.94, color: 'indigo' },
      { label: 'high-value', confidence: 0.88, color: 'emerald' },
      { label: 'technical-buyer', confidence: 0.82, color: 'amber' },
    ],
    lastActivity: '2h ago',
    deals: 3,
    revenue: 145000,
    createdAt: '2024-01-15T09:00:00Z',
  },
  {
    id: 'c-002',
    name: 'Marcus Rivera',
    email: 'mrivera@globalfinance.io',
    company: 'Global Finance Inc.',
    role: 'Chief Revenue Officer',
    avatar: 'MR',
    status: 'prospect',
    mlScore: {
      value: 78,
      label: 'hot',
      trend: 'up',
      signals: ['Demo scheduled', 'Requested pricing', 'Decision maker'],
    },
    semanticTags: [
      { label: 'enterprise', confidence: 0.91, color: 'indigo' },
      { label: 'decision-maker', confidence: 0.85, color: 'emerald' },
    ],
    lastActivity: '5h ago',
    deals: 1,
    revenue: 0,
    createdAt: '2024-02-03T11:00:00Z',
  },
  {
    id: 'c-003',
    name: 'Priya Nair',
    email: 'priya@startupbase.co',
    company: 'StartupBase',
    role: 'CEO & Co-Founder',
    avatar: 'PN',
    status: 'lead',
    mlScore: {
      value: 62,
      label: 'warm',
      trend: 'up',
      signals: ['Attended webinar', 'Downloaded whitepaper', 'Visited pricing page 4x'],
    },
    semanticTags: [
      { label: 'startup', confidence: 0.97, color: 'amber' },
      { label: 'growth-stage', confidence: 0.73, color: 'indigo' },
    ],
    lastActivity: '1d ago',
    deals: 0,
    revenue: 0,
    createdAt: '2024-02-18T14:30:00Z',
  },
  {
    id: 'c-004',
    name: 'James Whitfield',
    email: 'j.whitfield@accelarate.com',
    company: 'Accelarate Partners',
    role: 'Managing Director',
    avatar: 'JW',
    status: 'customer',
    mlScore: {
      value: 84,
      label: 'hot',
      trend: 'stable',
      signals: ['Renewed contract', 'Expanded seats by 40%', 'Referred 2 prospects'],
    },
    semanticTags: [
      { label: 'high-value', confidence: 0.96, color: 'emerald' },
      { label: 'advocate', confidence: 0.79, color: 'emerald' },
      { label: 'enterprise', confidence: 0.88, color: 'indigo' },
    ],
    lastActivity: '3h ago',
    deals: 2,
    revenue: 220000,
    createdAt: '2023-11-10T08:00:00Z',
  },
  {
    id: 'c-005',
    name: 'Amara Osei',
    email: 'amara.osei@buildright.ng',
    company: 'BuildRight Ltd',
    role: 'Head of Operations',
    avatar: 'AO',
    status: 'prospect',
    mlScore: {
      value: 55,
      label: 'warm',
      trend: 'down',
      signals: ['No reply in 14 days', 'Low email engagement', 'Budget approval pending'],
    },
    semanticTags: [
      { label: 'mid-market', confidence: 0.81, color: 'amber' },
      { label: 'ops-buyer', confidence: 0.68, color: 'indigo' },
    ],
    lastActivity: '2d ago',
    deals: 1,
    revenue: 0,
    createdAt: '2024-03-01T10:00:00Z',
  },
  {
    id: 'c-006',
    name: 'Lena Kowalski',
    email: 'lena.k@mediahub.eu',
    company: 'MediaHub Europe',
    role: 'Director of Marketing',
    avatar: 'LK',
    status: 'customer',
    mlScore: {
      value: 71,
      label: 'warm',
      trend: 'stable',
      signals: ['Active platform user', 'Monthly check-ins', 'NPS score 9'],
    },
    semanticTags: [
      { label: 'marketing-buyer', confidence: 0.9, color: 'rose' },
      { label: 'mid-market', confidence: 0.76, color: 'amber' },
    ],
    lastActivity: '6h ago',
    deals: 1,
    revenue: 48000,
    createdAt: '2024-01-22T09:00:00Z',
  },
  {
    id: 'c-007',
    name: 'Devon Park',
    email: 'devon@nexusai.dev',
    company: 'Nexus AI',
    role: 'CTO',
    avatar: 'DP',
    status: 'lead',
    mlScore: {
      value: 38,
      label: 'cold',
      trend: 'down',
      signals: ['Last visit 30 days ago', 'Unsubscribed from newsletter', 'No response to follow-ups'],
    },
    semanticTags: [
      { label: 'technical-buyer', confidence: 0.87, color: 'amber' },
      { label: 'startup', confidence: 0.72, color: 'amber' },
    ],
    lastActivity: '5d ago',
    deals: 0,
    revenue: 0,
    createdAt: '2024-03-14T15:00:00Z',
  },
  {
    id: 'c-008',
    name: 'Fatima Al-Rashid',
    email: 'fatima@oilgasdyn.com',
    company: 'OilGas Dynamics',
    role: 'IT Procurement Lead',
    avatar: 'FA',
    status: 'churned',
    mlScore: {
      value: 22,
      label: 'cold',
      trend: 'down',
      signals: ['Cancelled subscription', 'Support tickets unresolved', 'Competitor switch detected'],
    },
    semanticTags: [
      { label: 'at-risk', confidence: 0.99, color: 'rose' },
      { label: 'enterprise', confidence: 0.84, color: 'indigo' },
    ],
    lastActivity: '12d ago',
    deals: 0,
    revenue: 72000,
    createdAt: '2023-08-05T10:00:00Z',
  },
  {
    id: 'c-009',
    name: 'Tom Nakashima',
    email: 'tnakashima@scalepath.jp',
    company: 'ScalePath Japan',
    role: 'Business Development Manager',
    avatar: 'TN',
    status: 'prospect',
    mlScore: {
      value: 66,
      label: 'warm',
      trend: 'up',
      signals: ['Trial account active', 'Invited 3 colleagues', 'Requested enterprise pricing'],
    },
    semanticTags: [
      { label: 'apac-region', confidence: 0.95, color: 'indigo' },
      { label: 'high-potential', confidence: 0.71, color: 'emerald' },
    ],
    lastActivity: '1d ago',
    deals: 0,
    revenue: 0,
    createdAt: '2024-03-28T08:00:00Z',
  },
  {
    id: 'c-010',
    name: 'Claire Dupont',
    email: 'claire.dupont@clairefield.fr',
    company: 'Clairefield Conseil',
    role: 'Partner',
    avatar: 'CD',
    status: 'customer',
    mlScore: {
      value: 88,
      label: 'hot',
      trend: 'up',
      signals: ['Upsell conversation active', 'Sponsor of internal rollout', 'Bought 5 seats → 18 seats'],
    },
    semanticTags: [
      { label: 'high-value', confidence: 0.93, color: 'emerald' },
      { label: 'enterprise', confidence: 0.87, color: 'indigo' },
      { label: 'champion', confidence: 0.81, color: 'emerald' },
    ],
    lastActivity: '30m ago',
    deals: 2,
    revenue: 0,
    createdAt: '2023-12-01T09:00:00Z',
  },
]

// ─── Deals ────────────────────────────────────────────────────────────────────
export const demoDeals: Deal[] = [
  {
    id: 'd-001',
    title: 'TechCorp Platform Expansion',
    company: 'TechCorp Solutions',
    contactName: 'Sarah Chen',
    value: 145000,
    stage: 'negotiation',
    mlWinProbability: 82,
    healthScore: 78,
    expectedClose: 'May 15, 2024',
    assignedAgent: 'Pipeline Optimizer',
    notes: 'Legal review complete. Finalising SLA terms.',
    createdAt: '2024-01-20T10:00:00Z',
  },
  {
    id: 'd-002',
    title: 'Global Finance Enterprise Suite',
    company: 'Global Finance Inc.',
    contactName: 'Marcus Rivera',
    value: 250000,
    stage: 'proposal',
    mlWinProbability: 64,
    healthScore: 35,
    expectedClose: 'Jun 30, 2024',
    assignedAgent: 'Lead Scorer',
    notes: 'Custom proposal sent. Awaiting board sign-off.',
    createdAt: '2024-02-10T09:00:00Z',
  },
  {
    id: 'd-003',
    title: 'Accelarate Renewal + Upsell',
    company: 'Accelarate Partners',
    contactName: 'James Whitfield',
    value: 88000,
    stage: 'closed_won',
    mlWinProbability: 100,
    healthScore: 100,
    expectedClose: 'Apr 01, 2024',
    assignedAgent: 'Pipeline Optimizer',
    notes: 'Renewed 2-year contract. Added analytics module.',
    createdAt: '2023-12-05T11:00:00Z',
  },
  {
    id: 'd-004',
    title: 'BuildRight Ops Platform Pilot',
    company: 'BuildRight Ltd',
    contactName: 'Amara Osei',
    value: 32000,
    stage: 'qualified',
    mlWinProbability: 47,
    healthScore: 62,
    expectedClose: 'Jul 31, 2024',
    assignedAgent: 'Lead Scorer',
    notes: 'Pilot scope agreed. Budget approval in progress.',
    createdAt: '2024-03-05T14:00:00Z',
  },
  {
    id: 'd-005',
    title: 'MediaHub CRM Integration',
    company: 'MediaHub Europe',
    contactName: 'Lena Kowalski',
    value: 48000,
    stage: 'closed_won',
    mlWinProbability: 100,
    healthScore: 100,
    expectedClose: 'Mar 15, 2024',
    assignedAgent: 'Email Composer',
    notes: 'Integration complete. Customer live on v2.',
    createdAt: '2024-01-25T10:00:00Z',
  },
  {
    id: 'd-006',
    title: 'ScalePath Japan Starter',
    company: 'ScalePath Japan',
    contactName: 'Tom Nakashima',
    value: 18000,
    stage: 'discovery',
    mlWinProbability: 31,
    healthScore: 22,
    expectedClose: 'Aug 31, 2024',
    assignedAgent: 'Semantic Sorter',
    notes: 'Initial discovery call done. Feature checklist shared.',
    createdAt: '2024-04-01T08:00:00Z',
  },
  {
    id: 'd-007',
    title: 'Clairefield Enterprise Upsell',
    company: 'Clairefield Conseil',
    contactName: 'Claire Dupont',
    value: 72000,
    stage: 'proposal',
    mlWinProbability: 73,
    healthScore: 71,
    expectedClose: 'May 31, 2024',
    assignedAgent: 'Pipeline Optimizer',
    notes: 'Upsell proposal prepared. Champion aligned.',
    createdAt: '2024-03-20T09:00:00Z',
  },
  {
    id: 'd-008',
    title: 'Nexus AI Starter Package',
    company: 'Nexus AI',
    contactName: 'Devon Park',
    value: 5000,
    stage: 'closed_lost',
    mlWinProbability: 0,
    healthScore: 0,
    expectedClose: 'Apr 10, 2024',
    assignedAgent: 'Lead Scorer',
    notes: 'Chose competitor. Price sensitivity cited.',
    createdAt: '2024-02-28T10:00:00Z',
  },
]

// ─── Agents ───────────────────────────────────────────────────────────────────
export const demoAgents: Agent[] = [
  {
    id: 'a-001',
    name: 'Semantic Sorter',
    type: 'semantic_sorter',
    status: 'active',
    description:
      'Classifies incoming contacts and messages using sentence-transformer embeddings. Assigns semantic tags like enterprise, startup, technical-buyer with confidence scores.',
    model: 'sentence-transformers/all-MiniLM-L6-v2',
    accuracy: 94,
    tasksToday: 312,
    lastRun: '2 min ago',
    metrics: [
      { label: 'Tags Applied', value: '1,204', delta: '+8%' },
      { label: 'Avg Confidence', value: '87%' },
      { label: 'Throughput', value: '420/hr' },
    ],
    workflow: [
      { id: 'w1', label: 'New Contact / Message', type: 'trigger', position: { x: 0, y: 0 } },
      { id: 'w2', label: 'Embed Text', type: 'action', position: { x: 1, y: 0 } },
      { id: 'w3', label: 'Cosine Similarity', type: 'condition', position: { x: 2, y: 0 } },
      { id: 'w4', label: 'Assign Tags', type: 'output', position: { x: 3, y: 0 } },
    ],
  },
  {
    id: 'a-002',
    name: 'Lead Scorer',
    type: 'lead_scorer',
    status: 'active',
    description:
      'Scores contacts 0–100 using a gradient-boosted model trained on historical conversion data. Updates scores on new activity signals.',
    model: 'xgboost-v2.1-crm',
    accuracy: 91,
    tasksToday: 178,
    lastRun: '5 min ago',
    metrics: [
      { label: 'Scores Updated', value: '178', delta: '+12%' },
      { label: 'Hot Leads', value: '23' },
      { label: 'F1 Score', value: '0.91' },
    ],
    workflow: [
      { id: 'w1', label: 'Activity Signal', type: 'trigger', position: { x: 0, y: 0 } },
      { id: 'w2', label: 'Feature Extract', type: 'action', position: { x: 1, y: 0 } },
      { id: 'w3', label: 'XGBoost Predict', type: 'action', position: { x: 2, y: 0 } },
      { id: 'w4', label: 'Update Score', type: 'output', position: { x: 3, y: 0 } },
    ],
  },
  {
    id: 'a-003',
    name: 'Email Composer',
    type: 'email_composer',
    status: 'idle',
    description:
      'Generates personalised outreach emails using Claude claude-sonnet-4-6. Context-aware — pulls in contact history, deal stage, and semantic tags.',
    model: 'claude-sonnet-4-6',
    accuracy: 88,
    tasksToday: 41,
    lastRun: '1h ago',
    metrics: [
      { label: 'Drafts Created', value: '41' },
      { label: 'Open Rate', value: '34%', delta: '+5%' },
      { label: 'Reply Rate', value: '18%' },
    ],
    workflow: [
      { id: 'w1', label: 'Compose Request', type: 'trigger', position: { x: 0, y: 0 } },
      { id: 'w2', label: 'Fetch Context', type: 'action', position: { x: 1, y: 0 } },
      { id: 'w3', label: 'Claude Generate', type: 'action', position: { x: 2, y: 0 } },
      { id: 'w4', label: 'Return Draft', type: 'output', position: { x: 3, y: 0 } },
    ],
  },
  {
    id: 'a-004',
    name: 'Call Summarizer',
    type: 'call_summarizer',
    status: 'processing',
    description:
      'Transcribes and summarises sales calls. Extracts action items, objections, and next steps. Pushes summaries to contact timeline.',
    model: 'whisper-large-v3 + claude-haiku',
    accuracy: 89,
    tasksToday: 14,
    lastRun: 'Just now',
    metrics: [
      { label: 'Calls Processed', value: '14' },
      { label: 'Avg Duration', value: '28 min' },
      { label: 'Action Items', value: '47' },
    ],
    workflow: [
      { id: 'w1', label: 'Call Recording', type: 'trigger', position: { x: 0, y: 0 } },
      { id: 'w2', label: 'Whisper Transcribe', type: 'action', position: { x: 1, y: 0 } },
      { id: 'w3', label: 'Claude Summarize', type: 'action', position: { x: 2, y: 0 } },
      { id: 'w4', label: 'Push to Timeline', type: 'output', position: { x: 3, y: 0 } },
    ],
  },
  {
    id: 'a-005',
    name: 'Pipeline Optimizer',
    type: 'pipeline_optimizer',
    status: 'active',
    description:
      'Analyses deal velocity and stage durations. Flags stalled deals and recommends next-best actions to unblock pipeline.',
    model: 'heuristic-v3 + gpt-4o-mini',
    accuracy: 86,
    tasksToday: 29,
    lastRun: '15 min ago',
    metrics: [
      { label: 'Deals Analysed', value: '29', delta: '+3' },
      { label: 'Stalled Flagged', value: '4' },
      { label: 'Actions Sent', value: '11' },
    ],
    workflow: [
      { id: 'w1', label: 'Nightly Schedule', type: 'trigger', position: { x: 0, y: 0 } },
      { id: 'w2', label: 'Velocity Calc', type: 'action', position: { x: 1, y: 0 } },
      { id: 'w3', label: 'Risk Score', type: 'condition', position: { x: 2, y: 0 } },
      { id: 'w4', label: 'Flag + Notify', type: 'output', position: { x: 3, y: 0 } },
    ],
  },
  {
    id: 'a-006',
    name: 'Sentiment Analyzer',
    type: 'sentiment_analyzer',
    status: 'idle',
    description:
      'Runs sentiment analysis on inbound emails and call transcripts. Detects churn risk signals and flags at-risk accounts.',
    model: 'cardiffnlp/twitter-roberta-base-sentiment',
    accuracy: 83,
    tasksToday: 96,
    lastRun: '45 min ago',
    metrics: [
      { label: 'Messages Scanned', value: '96' },
      { label: 'At-Risk Flagged', value: '3' },
      { label: 'Positive Rate', value: '71%' },
    ],
    workflow: [
      { id: 'w1', label: 'New Message', type: 'trigger', position: { x: 0, y: 0 } },
      { id: 'w2', label: 'RoBERTa Classify', type: 'action', position: { x: 1, y: 0 } },
      { id: 'w3', label: 'Threshold Check', type: 'condition', position: { x: 2, y: 0 } },
      { id: 'w4', label: 'Update Risk Flag', type: 'output', position: { x: 3, y: 0 } },
    ],
  },
]

// ─── Activity Events ──────────────────────────────────────────────────────────
export const demoActivity: ActivityEvent[] = [
  {
    id: 'ev-001',
    type: 'contact_scored',
    agentName: 'Lead Scorer',
    description: 'updated 3 contacts — Sarah Chen moved to Hot (91)',
    meta: 'workspace: acme-corp',
    timestamp: '2 min ago',
    severity: 'success',
  },
  {
    id: 'ev-002',
    type: 'tag_applied',
    agentName: 'Semantic Sorter',
    description: 'applied 7 tags to 5 contacts from today\'s sync',
    meta: 'enterprise ×3, startup ×2, high-value ×2',
    timestamp: '8 min ago',
    severity: 'info',
  },
  {
    id: 'ev-003',
    type: 'email_sent',
    agentName: 'Email Composer',
    description: 'generated draft for Marcus Rivera — Re: Enterprise Proposal',
    meta: 'open_rate_est: 72%',
    timestamp: '22 min ago',
    severity: 'success',
  },
  {
    id: 'ev-004',
    type: 'deal_moved',
    agentName: 'Pipeline Optimizer',
    description: 'flagged TechCorp deal as stalled — 18 days in Negotiation',
    meta: 'recommended: schedule follow-up call',
    timestamp: '35 min ago',
    severity: 'warning',
  },
  {
    id: 'ev-005',
    type: 'call_summarized',
    agentName: 'Call Summarizer',
    description: 'summarised 28-min call with James Whitfield — 3 action items extracted',
    meta: 'sentiment: positive',
    timestamp: '1 hour ago',
    severity: 'success',
  },
  {
    id: 'ev-006',
    type: 'agent_run',
    agentName: 'Sentiment Analyzer',
    description: 'scanned 14 inbound emails — 1 at-risk signal detected (Fatima Al-Rashid)',
    meta: 'severity: negative',
    timestamp: '1 hour ago',
    severity: 'warning',
  },
  {
    id: 'ev-007',
    type: 'contact_scored',
    agentName: 'Lead Scorer',
    description: 'scored 12 new leads from this week\'s signups',
    meta: 'hot: 2, warm: 6, cold: 4',
    timestamp: '2 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-008',
    type: 'tag_applied',
    agentName: 'Semantic Sorter',
    description: 'classified Tom Nakashima as high-potential, apac-region',
    timestamp: '3 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-009',
    type: 'deal_moved',
    agentName: 'Pipeline Optimizer',
    description: 'moved Clairefield Upsell from Qualified → Proposal based on champion signal',
    timestamp: '4 hours ago',
    severity: 'success',
  },
  {
    id: 'ev-010',
    type: 'model_updated',
    agentName: 'Lead Scorer',
    description: 'retrained on last 90 days of closed deals — accuracy improved to 91%',
    meta: 'prev: 88%, Δ+3%',
    timestamp: '5 hours ago',
    severity: 'success',
  },
  {
    id: 'ev-011',
    type: 'agent_run',
    agentName: 'Task Extractor',
    description: 'found 2 tasks in email from sarah@techcorp.com',
    meta: 'tasks: "Send SLA draft", "Schedule legal review"',
    timestamp: '6 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-012',
    type: 'contact_scored',
    agentName: 'Lead Scorer',
    description: 'Amara Osei score dropped from 68 → 55 (no reply 14 days)',
    timestamp: '8 hours ago',
    severity: 'warning',
  },
  {
    id: 'ev-013',
    type: 'email_sent',
    agentName: 'Email Composer',
    description: 'drafted re-engagement email for Devon Park — cold outreach sequence step 3',
    timestamp: '9 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-014',
    type: 'call_summarized',
    agentName: 'Call Summarizer',
    description: 'processed call with Priya Nair — product demo follow-up notes created',
    meta: '18 min call, sentiment: neutral',
    timestamp: '1 day ago',
    severity: 'info',
  },
  {
    id: 'ev-015',
    type: 'deal_moved',
    agentName: 'Pipeline Optimizer',
    description: 'BuildRight Pilot moved Discovery → Qualified after champion confirmed',
    timestamp: '1 day ago',
    severity: 'success',
  },
]

// ─── Messages (for Inbox page) ────────────────────────────────────────────────
export interface DemoMessage {
  id: string
  subject: string | null
  sender_email: string | null
  received_at: string | null
  body_plain: string | null
  processed: boolean
  contact_id: string | null
  clarity_score?: { score: number; rationale: string } | null
  tasks?: Array<{ id: string; title: string; status: string }>
}

export const demoMessages: DemoMessage[] = [
  {
    id: 'm-001',
    subject: 'Re: Enterprise Platform — SLA Review',
    sender_email: 'sarah.chen@techcorp.com',
    received_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    body_plain:
      'Hi,\n\nThank you for sending over the updated SLA draft. I\'ve reviewed it with our legal team and we have a few questions:\n\n1. Section 4.2 — can we negotiate the uptime SLA to 99.95% instead of 99.9%?\n2. Data residency clause — we need explicit EU storage guarantee.\n3. Support response time — can we get P1 response down to 30 minutes?\n\nPlease send a revised version by Friday. We\'re hoping to sign before end of Q2.\n\nBest,\nSarah',
    processed: true,
    contact_id: 'c-001',
    clarity_score: { score: 92, rationale: 'Clear action items with specific deadlines. Three distinct asks with context.' },
    tasks: [
      { id: 't-m001-1', title: 'Revise SLA — negotiate 99.95% uptime', status: 'open' },
      { id: 't-m001-2', title: 'Add EU data residency clause to SLA', status: 'in_progress' },
      { id: 't-m001-3', title: 'Confirm P1 support SLA timing with team', status: 'open' },
    ],
  },
  {
    id: 'm-002',
    subject: 'Partnership opportunity — AI workflow automation',
    sender_email: 'mrivera@globalfinance.io',
    received_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    body_plain:
      'Hello,\n\nI came across your platform through a colleague at Accelarate. We\'re a 400-person finance firm looking to automate our sales ops.\n\nCould we schedule a 30-minute intro call? I\'m particularly interested in:\n— AI-powered lead scoring\n— Gmail integration\n— Pipeline analytics\n\nI have availability Thursday 2–5pm EST or Friday morning.\n\nRegards,\nMarcus Rivera\nCRO, Global Finance Inc.',
    processed: true,
    contact_id: 'c-002',
    clarity_score: { score: 78, rationale: 'Clear intent to book a call. Specific feature interests listed. Availability provided.' },
    tasks: [
      { id: 't-m002-1', title: 'Schedule intro call with Marcus Rivera — Thu/Fri EST', status: 'open' },
    ],
  },
  {
    id: 'm-003',
    subject: 'Feature request — bulk CSV import',
    sender_email: 'amara.osei@buildright.ng',
    received_at: new Date(Date.now() - 26 * 3600000).toISOString(),
    body_plain:
      'Hi team,\n\nWe have about 3,000 legacy contacts in a spreadsheet we need to import before go-live. Is bulk CSV import supported?\n\nIf not, can this be prioritised for Q3? It\'s blocking our procurement sign-off.\n\nThanks,\nAmara',
    processed: false,
    contact_id: 'c-005',
    clarity_score: { score: 61, rationale: 'Feature request with urgency signal. Blocking procurement — high priority.' },
    tasks: [
      { id: 't-m003-1', title: 'Check CSV import capability for BuildRight', status: 'open' },
    ],
  },
  {
    id: 'm-004',
    subject: 'Quick check-in',
    sender_email: 'lena.k@mediahub.eu',
    received_at: new Date(Date.now() - 6 * 3600000).toISOString(),
    body_plain:
      'Hey,\n\nJust wanted to check in on the v2 integration. Everything seems to be running smoothly on our end!\n\nOne small thing — the webhook seems to have a 2–3 second delay vs the 200ms we expected. Worth investigating?\n\nOtherwise very happy with the rollout.\n\nL',
    processed: true,
    contact_id: 'c-006',
    clarity_score: { score: 55, rationale: 'Positive overall but contains latency report that needs investigation.' },
    tasks: [
      { id: 't-m004-1', title: 'Investigate webhook delay for MediaHub — target 200ms', status: 'in_progress' },
    ],
  },
  {
    id: 'm-005',
    subject: 'Renewal discussion — next steps',
    sender_email: 'james.whitfield@accelarate.com',
    received_at: new Date(Date.now() - 3 * 3600000).toISOString(),
    body_plain:
      'Hi,\n\nGreat call earlier. As discussed, I\'d like to explore:\n\n1. Adding the analytics module ($18K/yr)\n2. Expanding from 12 to 20 seats\n3. Premier support tier\n\nCan you send a revised quote for these three options? Our board meeting is May 10th so we\'d need the contract signed by May 8th.\n\nLooking forward to continuing the partnership.\n\nJames',
    processed: true,
    contact_id: 'c-004',
    clarity_score: { score: 88, rationale: 'Highly actionable. Three specific upsell items with hard deadline. Decision-maker engaged.' },
    tasks: [
      { id: 't-m005-1', title: 'Send revised quote — analytics + seats + premier support', status: 'open' },
      { id: 't-m005-2', title: 'Get contract signed before May 8th', status: 'open' },
    ],
  },
  {
    id: 'm-006',
    subject: 'Update on Japan trial',
    sender_email: 'tnakashima@scalepath.jp',
    received_at: new Date(Date.now() - 48 * 3600000).toISOString(),
    body_plain:
      'Hello,\n\nOur trial has been going well. I\'ve invited two colleagues — our Head of Sales and a BizDev analyst — to join the trial workspace.\n\nA few questions:\n- Is there a Japanese language UI option planned?\n- How does data sovereignty work for Japanese entities?\n- Can we get a call with your APAC team?\n\nThank you,\nTom',
    processed: false,
    contact_id: 'c-009',
    clarity_score: { score: 45, rationale: 'Good engagement signals but questions are exploratory. No clear deadline.' },
    tasks: [
      { id: 't-m006-1', title: 'Connect Tom Nakashima with APAC team', status: 'open' },
      { id: 't-m006-2', title: 'Answer i18n and data sovereignty questions for ScalePath', status: 'open' },
    ],
  },
]

// ─── Tasks (for Tasks page) ────────────────────────────────────────────────────
export interface DemoTask {
  id: string
  title: string
  description: string | null
  status: 'open' | 'in_progress' | 'done'
  due_date: string | null
  contact_id: string | null
  contact_name?: string
  clarity_score?: { score: number; rationale?: string } | null
  message_snippet?: string | null
}

export const demoTasks: DemoTask[] = [
  {
    id: 't-001',
    title: 'Revise SLA — negotiate 99.95% uptime with legal',
    description: 'Update Section 4.2 of the enterprise SLA. Legal team requested 99.95% uptime guarantee.',
    status: 'in_progress',
    due_date: new Date(Date.now() + 2 * 86400000).toISOString(),
    contact_id: 'c-001',
    contact_name: 'Sarah Chen',
    clarity_score: { score: 92, rationale: 'Clear legal requirement with specific clause reference.' },
    message_snippet: 'Section 4.2 — can we negotiate the uptime SLA to 99.95% instead of 99.9%?',
  },
  {
    id: 't-002',
    title: 'Add EU data residency clause to SLA',
    description: 'Explicit guarantee for EU data storage required by TechCorp legal team.',
    status: 'open',
    due_date: new Date(Date.now() + 2 * 86400000).toISOString(),
    contact_id: 'c-001',
    contact_name: 'Sarah Chen',
    clarity_score: { score: 85, rationale: 'Compliance requirement. High urgency.' },
    message_snippet: 'Data residency clause — we need explicit EU storage guarantee.',
  },
  {
    id: 't-003',
    title: 'Schedule intro call with Marcus Rivera',
    description: 'Book 30-minute intro call. Availability: Thursday 2–5pm EST or Friday morning.',
    status: 'open',
    due_date: new Date(Date.now() + 1 * 86400000).toISOString(),
    contact_id: 'c-002',
    contact_name: 'Marcus Rivera',
    clarity_score: { score: 78, rationale: 'Availability clearly provided. High-value prospect.' },
    message_snippet: 'I have availability Thursday 2–5pm EST or Friday morning.',
  },
  {
    id: 't-004',
    title: 'Send revised quote for Accelarate upsell',
    description: 'Include analytics module ($18K/yr), expanded seats (12→20), and Premier support tier.',
    status: 'open',
    due_date: new Date(Date.now() + 5 * 86400000).toISOString(),
    contact_id: 'c-004',
    contact_name: 'James Whitfield',
    clarity_score: { score: 88, rationale: 'Three specific line items. Hard deadline May 8th.' },
    message_snippet: 'Can you send a revised quote for these three options? Our board meeting is May 10th.',
  },
  {
    id: 't-005',
    title: 'Investigate webhook latency for MediaHub',
    description: 'MediaHub reporting 2–3s delay vs expected 200ms. Check queue and event processing pipeline.',
    status: 'in_progress',
    due_date: null,
    contact_id: 'c-006',
    contact_name: 'Lena Kowalski',
    clarity_score: { score: 55, rationale: 'Technical bug report. Vague on reproduction steps.' },
    message_snippet: 'The webhook seems to have a 2–3 second delay vs the 200ms we expected.',
  },
  {
    id: 't-006',
    title: 'Check CSV import support for BuildRight',
    description: '3,000 legacy contacts need importing. Feature may not exist — check roadmap.',
    status: 'open',
    due_date: new Date(Date.now() + 3 * 86400000).toISOString(),
    contact_id: 'c-005',
    contact_name: 'Amara Osei',
    clarity_score: { score: 61, rationale: 'Blocking procurement — high urgency. Feature unclear.' },
    message_snippet: 'We have about 3,000 legacy contacts in a spreadsheet we need to import before go-live.',
  },
  {
    id: 't-007',
    title: 'Connect ScalePath with APAC team',
    description: 'Tom Nakashima requested a call with the APAC team re: localisation and sovereignty.',
    status: 'open',
    due_date: new Date(Date.now() + 4 * 86400000).toISOString(),
    contact_id: 'c-009',
    contact_name: 'Tom Nakashima',
    clarity_score: { score: 45, rationale: 'Exploratory request. No hard deadline given.' },
    message_snippet: 'Can we get a call with your APAC team?',
  },
  {
    id: 't-008',
    title: 'Follow up: Accelarate contract signed before May 8th',
    description: 'Ensure revised contract is countersigned ahead of board meeting on May 10th.',
    status: 'done',
    due_date: new Date(Date.now() - 1 * 86400000).toISOString(),
    contact_id: 'c-004',
    contact_name: 'James Whitfield',
    clarity_score: { score: 88, rationale: 'Deadline-critical. Champion confirmed.' },
    message_snippet: 'Our board meeting is May 10th so we\'d need the contract signed by May 8th.',
  },
]

// ─── Connectors ───────────────────────────────────────────────────────────────
export interface DemoConnector {
  id: string
  service: string
  status: string
  last_sync: string | null
  message_count: number
}

export const demoConnectors: DemoConnector[] = [
  {
    id: 'conn-001',
    service: 'gmail',
    status: 'connected',
    last_sync: new Date(Date.now() - 2 * 3600000).toISOString(),
    message_count: 142,
  },
  {
    id: 'conn-002',
    service: 'slack',
    status: 'disconnected',
    last_sync: null,
    message_count: 0,
  },
]

// ─── Dashboard aggregates ─────────────────────────────────────────────────────
export const demoDashboard = {
  totalContacts: 10,
  totalRevenue: 485000,
  activeDeals: 6,
  avgDealValue: 67500,
  tasksExtractedToday: 7,
  avgClarityScore: 71,
  openTasks: 5,
  messagesIngested: 142,
  revenueGrowth: 12,
  dealGrowth: 8,
}

// ─── KPIs (formatted for dashboard) ──────────────────────────────────────────
export const demoKPIs: KPI[] = [
  {
    id: 'k1',
    label: 'Total Revenue',
    value: '$485,000',
    delta: '+12% vs last month',
    deltaType: 'positive',
    icon: 'dollar',
    sparkData: [280, 310, 295, 340, 380, 420, 485],
  },
  {
    id: 'k2',
    label: 'Active Deals',
    value: '6',
    delta: '8 total',
    deltaType: 'neutral',
    icon: 'briefcase',
    sparkData: [5, 6, 7, 5, 6, 7, 6],
  },
  {
    id: 'k3',
    label: 'ML Lead Accuracy',
    value: '91%',
    delta: '+3% since retrain',
    deltaType: 'positive',
    icon: 'brain',
    sparkData: [84, 85, 87, 88, 88, 89, 91],
  },
  {
    id: 'k4',
    label: 'Agents Running',
    value: '3 / 6',
    delta: '3 idle',
    deltaType: 'neutral',
    icon: 'bot',
    sparkData: [2, 3, 4, 3, 3, 4, 3],
  },
]

// ─── Chart data (for dashboard) ───────────────────────────────────────────────
export const demoRevenueChartData = [
  { month: 'Nov', revenue: 210000 },
  { month: 'Dec', revenue: 195000 },
  { month: 'Jan', revenue: 280000 },
  { month: 'Feb', revenue: 320000 },
  { month: 'Mar', revenue: 415000 },
  { month: 'Apr', revenue: 485000 },
]

export const demoAgentAccuracyData = [
  { day: 'Mon', semantic: 93, leadScore: 89, sentiment: 81 },
  { day: 'Tue', semantic: 94, leadScore: 90, sentiment: 82 },
  { day: 'Wed', semantic: 94, leadScore: 89, sentiment: 83 },
  { day: 'Thu', semantic: 95, leadScore: 91, sentiment: 82 },
  { day: 'Fri', semantic: 94, leadScore: 91, sentiment: 84 },
  { day: 'Sat', semantic: 93, leadScore: 90, sentiment: 83 },
  { day: 'Sun', semantic: 94, leadScore: 91, sentiment: 83 },
]
