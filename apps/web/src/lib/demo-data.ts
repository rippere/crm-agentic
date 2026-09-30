import type {
  Contact,
  Deal,
  Agent,
  ActivityEvent,
  KPI,
  Workspace,
  Lead,
  LeadStage,
  LeadSource,
  LeadFunnelStage,
  EngagementLabel,
  Segment,
  Campaign,
  Sequence,
  SequenceStep,
  Enrollment,
  EngagementEvent,
  PendingOutreach,
} from './types'

// ─── Workspace ────────────────────────────────────────────────────────────────
export const demoWorkspace: Workspace = {
  id: 'demo-workspace-1',
  name: "Zach's Photo Booth Co.",
  slug: 'photobooth-co',
  mode: 'both' as const,
  created_at: new Date().toISOString(),
}

// ─── Contacts ─────────────────────────────────────────────────────────────────
export const demoContacts: Contact[] = [
  {
    id: 'c-001',
    name: 'Rico Alvarez',
    email: 'rico@rowdysteer.com',
    company: 'The Rowdy Steer Saloon',
    role: 'Owner',
    avatar: 'RA',
    status: 'customer',
    mlScore: {
      value: 91,
      label: 'hot',
      trend: 'up',
      signals: ['3 booth swaps in 30 days', 'Revenue-share up 22% month-over-month', 'Flagship nightlife location'],
    },
    semanticTags: [
      { label: 'Tier A', confidence: 1, color: 'indigo' },
      { label: 'high-traffic', confidence: 0.88, color: 'emerald' },
      { label: 'nightlife', confidence: 0.82, color: 'amber' },
    ],
    lastActivity: '2h ago',
    deals: 3,
    revenue: 145000,
    createdAt: '2024-01-15T09:00:00Z',
  },
  {
    id: 'c-002',
    name: 'Denise Fontaine',
    email: 'denise@route9plaza.com',
    company: 'Route 9 Travel Plaza',
    role: 'Operations Owner',
    avatar: 'DF',
    status: 'prospect',
    mlScore: {
      value: 78,
      label: 'hot',
      trend: 'up',
      signals: ['Requested revenue-share terms', 'Toured a live booth at a peer plaza', 'Signs for all 4 sites'],
    },
    semanticTags: [
      { label: 'Tier B', confidence: 1, color: 'amber' },
      { label: 'truck-stop', confidence: 0.85, color: 'indigo' },
      { label: 'high-foot-traffic', confidence: 0.8, color: 'emerald' },
    ],
    lastActivity: '5h ago',
    deals: 1,
    revenue: 0,
    createdAt: '2024-02-03T11:00:00Z',
  },
  {
    id: 'c-003',
    name: 'Naomi Blackwell',
    email: 'naomi@neonalley.co',
    company: 'Neon Alley Arcade Bar',
    role: 'Co-Owner',
    avatar: 'NB',
    status: 'lead',
    mlScore: {
      value: 62,
      label: 'warm',
      trend: 'up',
      signals: ['Visited the partner page 4x', 'Downloaded the revenue-share one-pager', 'Came to a booth demo night'],
    },
    semanticTags: [
      { label: 'Tier C', confidence: 1, color: 'rose' },
      { label: 'arcade-bar', confidence: 0.9, color: 'amber' },
      { label: 'growth-venue', confidence: 0.73, color: 'indigo' },
    ],
    lastActivity: '1d ago',
    deals: 0,
    revenue: 0,
    createdAt: '2024-02-18T14:30:00Z',
  },
  {
    id: 'c-004',
    name: 'Grant Whitaker',
    email: 'grant@whitakerbowl.com',
    company: "Whitaker's Bowl & Brew",
    role: 'Managing Partner',
    avatar: 'GW',
    status: 'customer',
    mlScore: {
      value: 84,
      label: 'hot',
      trend: 'stable',
      signals: ['Renewed revenue-share contract', 'Added a 2nd booth (+40% prints)', 'Referred 2 venues'],
    },
    semanticTags: [
      { label: 'Tier A', confidence: 1, color: 'indigo' },
      { label: 'multi-booth', confidence: 0.96, color: 'emerald' },
      { label: 'anchor-partner', confidence: 0.79, color: 'emerald' },
    ],
    lastActivity: '3h ago',
    deals: 2,
    revenue: 220000,
    createdAt: '2023-11-10T08:00:00Z',
  },
  {
    id: 'c-005',
    name: 'Terrell Hughes',
    email: 'terrell@southsidesports.com',
    company: 'Southside Sports Bar',
    role: 'General Manager',
    avatar: 'TH',
    status: 'prospect',
    mlScore: {
      value: 55,
      label: 'warm',
      trend: 'down',
      signals: ['No reply in 14 days', 'Low booth usage during trial', 'Owner sign-off pending'],
    },
    semanticTags: [
      { label: 'Tier B', confidence: 1, color: 'amber' },
      { label: 'sports-bar', confidence: 0.81, color: 'indigo' },
      { label: 'trial-stalled', confidence: 0.68, color: 'rose' },
    ],
    lastActivity: '2d ago',
    deals: 1,
    revenue: 0,
    createdAt: '2024-03-01T10:00:00Z',
  },
  {
    id: 'c-006',
    name: 'Bianca Moreau',
    email: 'bianca@galleriapopups.com',
    company: 'Galleria Mall Pop-Up Marketing',
    role: 'Marketing Director',
    avatar: 'BM',
    status: 'customer',
    mlScore: {
      value: 71,
      label: 'warm',
      trend: 'stable',
      signals: ['Active branded-booth campaign', 'Monthly check-ins', 'Partner NPS 9'],
    },
    semanticTags: [
      { label: 'Tier B', confidence: 1, color: 'amber' },
      { label: 'retail-activation', confidence: 0.9, color: 'indigo' },
      { label: 'brand-campaign', confidence: 0.76, color: 'emerald' },
    ],
    lastActivity: '6h ago',
    deals: 1,
    revenue: 48000,
    createdAt: '2024-01-22T09:00:00Z',
  },
  {
    id: 'c-007',
    name: 'Colton Reed',
    email: 'colton@basementcomedy.com',
    company: 'The Basement Comedy Club',
    role: 'Owner',
    avatar: 'CR',
    status: 'lead',
    mlScore: {
      value: 38,
      label: 'cold',
      trend: 'down',
      signals: ['Last visit 30 days ago', 'Unsubscribed from partner newsletter', 'No response to follow-ups'],
    },
    semanticTags: [
      { label: 'Tier C', confidence: 1, color: 'rose' },
      { label: 'comedy-club', confidence: 0.87, color: 'amber' },
      { label: 'low-traffic', confidence: 0.72, color: 'rose' },
    ],
    lastActivity: '5d ago',
    deals: 0,
    revenue: 0,
    createdAt: '2024-03-14T15:00:00Z',
  },
  {
    id: 'c-008',
    name: 'Warren Kessler',
    email: 'warren@kesslersroadhouse.com',
    company: "Kessler's Roadhouse",
    role: 'Owner',
    avatar: 'WK',
    status: 'churned',
    mlScore: {
      value: 22,
      label: 'cold',
      trend: 'down',
      signals: ['Ended revenue-share partnership', 'Booth removed after a payout dispute', 'Switched to a competitor booth vendor'],
    },
    semanticTags: [
      { label: 'at-risk', confidence: 0.99, color: 'rose' },
      { label: 'Tier C', confidence: 1, color: 'rose' },
      { label: 'former-partner', confidence: 0.84, color: 'indigo' },
    ],
    lastActivity: '12d ago',
    deals: 0,
    revenue: 72000,
    createdAt: '2023-08-05T10:00:00Z',
  },
  {
    id: 'c-009',
    name: 'Hana Sato',
    email: 'hana@karaokedistrict.com',
    company: 'Karaoke District Lounge',
    role: 'Booking Manager',
    avatar: 'HS',
    status: 'prospect',
    mlScore: {
      value: 66,
      label: 'warm',
      trend: 'up',
      signals: ['Trial booth live for 2 weekends', 'Invited 3 sister locations', 'Requested a multi-venue rate'],
    },
    semanticTags: [
      { label: 'Tier B', confidence: 1, color: 'amber' },
      { label: 'karaoke-lounge', confidence: 0.95, color: 'indigo' },
      { label: 'multi-venue-potential', confidence: 0.71, color: 'emerald' },
    ],
    lastActivity: '1d ago',
    deals: 0,
    revenue: 0,
    createdAt: '2024-03-28T08:00:00Z',
  },
  {
    id: 'c-010',
    name: 'Dominique Laurent',
    email: 'dominique@velvetroomclub.com',
    company: 'Velvet Room Nightclub',
    role: 'Owner',
    avatar: 'DL',
    status: 'customer',
    mlScore: {
      value: 88,
      label: 'hot',
      trend: 'up',
      signals: ['Expanding from 1 → 3 club locations', 'Champion for the booth program', 'Premium mirror-booth upsell active'],
    },
    semanticTags: [
      { label: 'Tier A', confidence: 1, color: 'indigo' },
      { label: 'nightclub', confidence: 0.93, color: 'amber' },
      { label: 'expansion-partner', confidence: 0.81, color: 'emerald' },
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
    title: 'Rowdy Steer — Flagship Booth Revenue-Share',
    company: 'The Rowdy Steer Saloon',
    contactName: 'Rico Alvarez',
    value: 145000,
    stage: 'negotiation',
    mlWinProbability: 82,
    healthScore: 78,
    expectedClose: 'May 15, 2024',
    assignedAgent: 'Pipeline Optimizer',
    notes: 'Split terms agreed at 70/30. Finalising the second bar-top booth placement.',
    createdAt: '2024-01-20T10:00:00Z',
  },
  {
    id: 'd-002',
    title: 'Route 9 Travel Plaza — Multi-Site Booth Rollout',
    company: 'Route 9 Travel Plaza',
    contactName: 'Denise Fontaine',
    value: 250000,
    stage: 'proposal',
    mlWinProbability: 64,
    healthScore: 35,
    expectedClose: 'Jun 30, 2024',
    assignedAgent: 'Lead Scorer',
    notes: 'Proposal sent for a 4-site rollout. Awaiting owner-group sign-off.',
    createdAt: '2024-02-10T09:00:00Z',
  },
  {
    id: 'd-003',
    title: "Whitaker's Bowl & Brew — Renewal + 2nd Booth",
    company: "Whitaker's Bowl & Brew",
    contactName: 'Grant Whitaker',
    value: 88000,
    stage: 'closed_won',
    mlWinProbability: 100,
    healthScore: 100,
    expectedClose: 'Apr 01, 2024',
    assignedAgent: 'Pipeline Optimizer',
    notes: 'Renewed the 2-year revenue-share. Added a second booth by the lanes.',
    createdAt: '2023-12-05T11:00:00Z',
  },
  {
    id: 'd-004',
    title: 'Southside Sports Bar — Booth Pilot',
    company: 'Southside Sports Bar',
    contactName: 'Terrell Hughes',
    value: 32000,
    stage: 'qualified',
    mlWinProbability: 47,
    healthScore: 62,
    expectedClose: 'Jul 31, 2024',
    assignedAgent: 'Lead Scorer',
    notes: 'Pilot placement agreed. Owner sign-off in progress.',
    createdAt: '2024-03-05T14:00:00Z',
  },
  {
    id: 'd-005',
    title: 'Galleria Mall — Branded Booth Activation',
    company: 'Galleria Mall Pop-Up Marketing',
    contactName: 'Bianca Moreau',
    value: 48000,
    stage: 'closed_won',
    mlWinProbability: 100,
    healthScore: 100,
    expectedClose: 'Mar 15, 2024',
    assignedAgent: 'Email Composer',
    notes: 'Branded holiday activation live. Booth wrapped in campaign artwork.',
    createdAt: '2024-01-25T10:00:00Z',
  },
  {
    id: 'd-006',
    title: 'Karaoke District — Weekend Booth Trial',
    company: 'Karaoke District Lounge',
    contactName: 'Hana Sato',
    value: 18000,
    stage: 'discovery',
    mlWinProbability: 31,
    healthScore: 22,
    expectedClose: 'Aug 31, 2024',
    assignedAgent: 'Semantic Sorter',
    notes: 'Discovery call done. Weekend trial placement scoped.',
    createdAt: '2024-04-01T08:00:00Z',
  },
  {
    id: 'd-007',
    title: 'Velvet Room — Premium Mirror Booth Upsell',
    company: 'Velvet Room Nightclub',
    contactName: 'Dominique Laurent',
    value: 72000,
    stage: 'proposal',
    mlWinProbability: 73,
    healthScore: 71,
    expectedClose: 'May 31, 2024',
    assignedAgent: 'Pipeline Optimizer',
    notes: 'Upsell to the premium mirror booth prepared. Champion aligned on the 3-club expansion.',
    createdAt: '2024-03-20T09:00:00Z',
  },
  {
    id: 'd-008',
    title: 'Basement Comedy Club — Starter Booth',
    company: 'The Basement Comedy Club',
    contactName: 'Colton Reed',
    value: 5000,
    stage: 'closed_lost',
    mlWinProbability: 0,
    healthScore: 0,
    expectedClose: 'Apr 10, 2024',
    assignedAgent: 'Lead Scorer',
    notes: 'Chose a competitor booth vendor. Cited the revenue-share split.',
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
      'Scores contacts 0–100 from engagement signals, firmographic data, and deal history. Updates scores on new activity.',
    model: 'heuristic + signals',
    accuracy: 91,
    tasksToday: 178,
    lastRun: '5 min ago',
    metrics: [
      { label: 'Scores Updated', value: '178', delta: '+12%' },
      { label: 'Hot Leads', value: '23' },
      { label: 'Avg Score', value: '64' },
    ],
    workflow: [
      { id: 'w1', label: 'Activity Signal', type: 'trigger', position: { x: 0, y: 0 } },
      { id: 'w2', label: 'Feature Extract', type: 'action', position: { x: 1, y: 0 } },
      { id: 'w3', label: 'Score Signals', type: 'action', position: { x: 2, y: 0 } },
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
    model: 'whisper-base + claude-haiku',
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
    model: 'heuristic',
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
    model: 'claude-haiku-4-5',
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
      { id: 'w2', label: 'Claude Sentiment', type: 'action', position: { x: 1, y: 0 } },
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
    description: 'updated 3 partners — Rico Alvarez moved to Hot (91)',
    meta: 'workspace: photobooth-co',
    timestamp: '2 min ago',
    severity: 'success',
  },
  {
    id: 'ev-002',
    type: 'tag_applied',
    agentName: 'Semantic Sorter',
    description: 'applied 7 tags to 5 partners from today\'s sync',
    meta: 'Tier A ×3, nightlife ×2, high-traffic ×2',
    timestamp: '8 min ago',
    severity: 'info',
  },
  {
    id: 'ev-003',
    type: 'email_sent',
    agentName: 'Email Composer',
    description: 'generated draft for Denise Fontaine — Re: Revenue-Share Terms',
    meta: 'open_rate_est: 72%',
    timestamp: '22 min ago',
    severity: 'success',
  },
  {
    id: 'ev-004',
    type: 'deal_moved',
    agentName: 'Pipeline Optimizer',
    description: 'flagged the Rowdy Steer deal as stalled — 18 days in Negotiation',
    meta: 'recommended: schedule follow-up call',
    timestamp: '35 min ago',
    severity: 'warning',
  },
  {
    id: 'ev-005',
    type: 'call_summarized',
    agentName: 'Call Summarizer',
    description: 'summarised 28-min call with Grant Whitaker — 3 action items extracted',
    meta: 'sentiment: positive',
    timestamp: '1 hour ago',
    severity: 'success',
  },
  {
    id: 'ev-006',
    type: 'agent_run',
    agentName: 'Sentiment Analyzer',
    description: 'scanned 14 inbound emails — 1 at-risk signal detected (Warren Kessler)',
    meta: 'severity: negative',
    timestamp: '1 hour ago',
    severity: 'warning',
  },
  {
    id: 'ev-007',
    type: 'contact_scored',
    agentName: 'Lead Scorer',
    description: 'scored 12 new leads from this week\'s venue list',
    meta: 'hot: 2, warm: 6, cold: 4',
    timestamp: '2 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-008',
    type: 'tag_applied',
    agentName: 'Semantic Sorter',
    description: 'classified Hana Sato as multi-venue-potential, karaoke-lounge',
    timestamp: '3 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-009',
    type: 'deal_moved',
    agentName: 'Pipeline Optimizer',
    description: 'moved the Velvet Room upsell from Qualified → Proposal based on champion signal',
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
    description: 'found 2 tasks in email from rico@rowdysteer.com',
    meta: 'tasks: "Send revenue-share addendum", "Schedule booth swap"',
    timestamp: '6 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-012',
    type: 'contact_scored',
    agentName: 'Lead Scorer',
    description: 'Terrell Hughes score dropped from 68 → 55 (no reply 14 days)',
    timestamp: '8 hours ago',
    severity: 'warning',
  },
  {
    id: 'ev-013',
    type: 'email_sent',
    agentName: 'Email Composer',
    description: 'drafted re-engagement email for Colton Reed — cold outreach sequence step 3',
    timestamp: '9 hours ago',
    severity: 'info',
  },
  {
    id: 'ev-014',
    type: 'call_summarized',
    agentName: 'Call Summarizer',
    description: 'processed call with Naomi Blackwell — booth demo follow-up notes created',
    meta: '18 min call, sentiment: neutral',
    timestamp: '1 day ago',
    severity: 'info',
  },
  {
    id: 'ev-015',
    type: 'deal_moved',
    agentName: 'Pipeline Optimizer',
    description: 'Southside Sports Bar pilot moved Discovery → Qualified after champion confirmed',
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
    subject: 'Re: Flagship Booth — Revenue-Share Terms',
    sender_email: 'rico@rowdysteer.com',
    received_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    body_plain:
      'Hi,\n\nThanks for sending over the updated revenue-share agreement. I went through it with my business partner and we have a few asks:\n\n1. Can we move the split from 65/35 to 70/30 in our favor given our weekend crowds?\n2. On peak country nights we\'d want a booth attendant guaranteed on-site.\n3. Print restock — can we get cartridges swapped faster so we never run dry mid-night?\n\nSend a revised version by Friday and we can lock the second booth before the fall.\n\nBest,\nRico',
    processed: true,
    contact_id: 'c-001',
    clarity_score: { score: 92, rationale: 'Clear action items with specific deadlines. Three distinct asks with context.' },
    tasks: [
      { id: 't-m001-1', title: 'Revise agreement — negotiate 70/30 revenue split', status: 'open' },
      { id: 't-m001-2', title: 'Add peak-night attendant guarantee to agreement', status: 'in_progress' },
      { id: 't-m001-3', title: 'Confirm print-restock SLA with ops team', status: 'open' },
    ],
  },
  {
    id: 'm-002',
    subject: 'Photo booths for our travel plazas?',
    sender_email: 'denise@route9plaza.com',
    received_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    body_plain:
      'Hello,\n\nI heard about your booths from Grant over at Whitaker\'s Bowl & Brew. We run four travel plazas along the interstate and get heavy foot traffic overnight.\n\nCould we schedule a 30-minute intro call? I\'m particularly interested in:\n— How the revenue-share model works\n— Whether the booth runs unattended\n— The instant print + digital gallery\n\nI have availability Thursday 2–5pm EST or Friday morning.\n\nRegards,\nDenise Fontaine\nOperations Owner, Route 9 Travel Plaza',
    processed: true,
    contact_id: 'c-002',
    clarity_score: { score: 78, rationale: 'Clear intent to book a call. Specific interests listed. Availability provided.' },
    tasks: [
      { id: 't-m002-1', title: 'Schedule intro call with Denise Fontaine — Thu/Fri EST', status: 'open' },
    ],
  },
  {
    id: 'm-003',
    subject: 'Booth for our big game nights?',
    sender_email: 'terrell@southsidesports.com',
    received_at: new Date(Date.now() - 26 * 3600000).toISOString(),
    body_plain:
      'Hi team,\n\nWe pack in around 3,000 patrons across a big game weekend and I think a booth would crush it. Can it run unattended through a rush like that?\n\nAlso, what does the revenue split look like for a room our size? The owner won\'t sign off until I can put numbers in front of him.\n\nThanks,\nTerrell',
    processed: false,
    contact_id: 'c-005',
    clarity_score: { score: 61, rationale: 'Fit question with urgency signal. Blocking owner sign-off — high priority.' },
    tasks: [
      { id: 't-m003-1', title: 'Confirm unattended-booth fit for Southside game nights', status: 'open' },
    ],
  },
  {
    id: 'm-004',
    subject: 'Quick check-in',
    sender_email: 'bianca@galleriapopups.com',
    received_at: new Date(Date.now() - 6 * 3600000).toISOString(),
    body_plain:
      'Hey,\n\nJust wanted to check in on the branded activation. The booth is a hit and shoppers love the wrapped design!\n\nOne small thing — the digital gallery upload seems to lag 2–3 seconds vs the instant delivery we expected. Worth a look?\n\nOtherwise very happy with the rollout.\n\nB',
    processed: true,
    contact_id: 'c-006',
    clarity_score: { score: 55, rationale: 'Positive overall but contains a delivery-latency report that needs investigation.' },
    tasks: [
      { id: 't-m004-1', title: 'Investigate gallery-upload delay for Galleria booth — target instant', status: 'in_progress' },
    ],
  },
  {
    id: 'm-005',
    subject: 'Renewal discussion — next steps',
    sender_email: 'grant@whitakerbowl.com',
    received_at: new Date(Date.now() - 3 * 3600000).toISOString(),
    body_plain:
      'Hi,\n\nGreat call earlier. As discussed, I\'d like to move on:\n\n1. Adding a second booth by the lanes ($18K/yr projected)\n2. Extending to a 2-year revenue-share\n3. Upgrading to the premium mirror booth\n\nCan you send a revised quote for these three options? Our owner-group meets May 10th so we\'d need it signed by May 8th.\n\nLooking forward to continuing the partnership.\n\nGrant',
    processed: true,
    contact_id: 'c-004',
    clarity_score: { score: 88, rationale: 'Highly actionable. Three specific upsell items with a hard deadline. Decision-maker engaged.' },
    tasks: [
      { id: 't-m005-1', title: 'Send revised quote — 2nd booth + 2-year renewal + mirror upgrade', status: 'open' },
      { id: 't-m005-2', title: 'Get renewal signed before May 8th', status: 'open' },
    ],
  },
  {
    id: 'm-006',
    subject: 'Update on the weekend booth trial',
    sender_email: 'hana@karaokedistrict.com',
    received_at: new Date(Date.now() - 48 * 3600000).toISOString(),
    body_plain:
      'Hello,\n\nThe weekend trial has been going great. I\'ve looped in two of our sister lounges who want in.\n\nA few questions:\n- Is there a multi-venue revenue-share rate?\n- Can the booth run late-night unattended?\n- Can we get a call with your field team about installs?\n\nThank you,\nHana',
    processed: false,
    contact_id: 'c-009',
    clarity_score: { score: 45, rationale: 'Good engagement signals but questions are exploratory. No clear deadline.' },
    tasks: [
      { id: 't-m006-1', title: 'Connect Hana Sato with the field-ops team', status: 'open' },
      { id: 't-m006-2', title: 'Answer multi-venue rate + late-night operation for Karaoke District', status: 'open' },
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
    title: 'Revise agreement — negotiate 70/30 revenue split',
    description: 'Update the revenue-share split in the Rowdy Steer agreement. Rico asked for 70/30 given weekend crowds.',
    status: 'in_progress',
    due_date: new Date(Date.now() + 2 * 86400000).toISOString(),
    contact_id: 'c-001',
    contact_name: 'Rico Alvarez',
    clarity_score: { score: 92, rationale: 'Clear commercial ask with a specific split.' },
    message_snippet: 'Can we move the split from 65/35 to 70/30 in our favor given our weekend crowds?',
  },
  {
    id: 't-002',
    title: 'Add peak-night attendant guarantee to booth agreement',
    description: 'Guarantee an on-site booth attendant on peak country nights for The Rowdy Steer Saloon.',
    status: 'open',
    due_date: new Date(Date.now() + 2 * 86400000).toISOString(),
    contact_id: 'c-001',
    contact_name: 'Rico Alvarez',
    clarity_score: { score: 85, rationale: 'Service-level requirement. High urgency.' },
    message_snippet: 'On peak country nights we\'d want a booth attendant guaranteed on-site.',
  },
  {
    id: 't-003',
    title: 'Schedule intro call with Denise Fontaine',
    description: 'Book 30-minute intro call. Availability: Thursday 2–5pm EST or Friday morning.',
    status: 'open',
    due_date: new Date(Date.now() + 1 * 86400000).toISOString(),
    contact_id: 'c-002',
    contact_name: 'Denise Fontaine',
    clarity_score: { score: 78, rationale: 'Availability clearly provided. High-value prospect.' },
    message_snippet: 'I have availability Thursday 2–5pm EST or Friday morning.',
  },
  {
    id: 't-004',
    title: "Send revised quote for Whitaker's 2nd booth",
    description: 'Include a 2nd booth by the lanes ($18K/yr), a 2-year revenue-share renewal, and the premium mirror-booth upgrade.',
    status: 'open',
    due_date: new Date(Date.now() + 5 * 86400000).toISOString(),
    contact_id: 'c-004',
    contact_name: 'Grant Whitaker',
    clarity_score: { score: 88, rationale: 'Three specific line items. Hard deadline May 8th.' },
    message_snippet: 'Can you send a revised quote for these three options? Our owner-group meets May 10th.',
  },
  {
    id: 't-005',
    title: 'Investigate gallery-upload delay for Galleria booth',
    description: 'Galleria reporting a 2–3s gallery-upload delay vs instant. Check the upload queue and processing pipeline.',
    status: 'in_progress',
    due_date: null,
    contact_id: 'c-006',
    contact_name: 'Bianca Moreau',
    clarity_score: { score: 55, rationale: 'Delivery-latency report. Vague on reproduction steps.' },
    message_snippet: 'The digital gallery upload seems to lag 2–3 seconds vs the instant delivery we expected.',
  },
  {
    id: 't-006',
    title: 'Confirm unattended-booth fit for Southside game nights',
    description: 'Southside packs ~3,000 patrons on a big game weekend. Confirm the booth runs unattended through the rush and share split numbers.',
    status: 'open',
    due_date: new Date(Date.now() + 3 * 86400000).toISOString(),
    contact_id: 'c-005',
    contact_name: 'Terrell Hughes',
    clarity_score: { score: 61, rationale: 'Blocking owner sign-off — high urgency.' },
    message_snippet: 'We pack in around 3,000 patrons across a big game weekend. Can it run unattended?',
  },
  {
    id: 't-007',
    title: 'Connect Karaoke District with the field-ops team',
    description: 'Hana Sato requested a call with the field team re: multi-venue installs and late-night operation.',
    status: 'open',
    due_date: new Date(Date.now() + 4 * 86400000).toISOString(),
    contact_id: 'c-009',
    contact_name: 'Hana Sato',
    clarity_score: { score: 45, rationale: 'Exploratory request. No hard deadline given.' },
    message_snippet: 'Can we get a call with your field team about installs?',
  },
  {
    id: 't-008',
    title: 'Follow up: Whitaker renewal signed before May 8th',
    description: 'Ensure the revised revenue-share renewal is countersigned ahead of the owner-group meeting on May 10th.',
    status: 'done',
    due_date: new Date(Date.now() - 1 * 86400000).toISOString(),
    contact_id: 'c-004',
    contact_name: 'Grant Whitaker',
    clarity_score: { score: 88, rationale: 'Deadline-critical. Champion confirmed.' },
    message_snippet: 'Our owner-group meets May 10th so we\'d need it signed by May 8th.',
  },
  {
    id: 't-009',
    title: 'Install mirror booth at Velvet Room Nightclub',
    description: 'Field op: on-site install of the premium mirror booth ahead of Saturday\'s grand-reopening. Confirm the power drop and floor space with Dominique.',
    status: 'open',
    due_date: new Date(Date.now() + 3 * 86400000).toISOString(),
    contact_id: 'c-010',
    contact_name: 'Dominique Laurent',
    clarity_score: null,
    message_snippet: null,
  },
  {
    id: 't-010',
    title: 'Swap booth + restock prints at The Rowdy Steer Saloon',
    description: 'Field op: rotate the bar-top booth for the open-air unit and restock 4 print cartridges before the weekend country-night crowd.',
    status: 'in_progress',
    due_date: new Date(Date.now() + 1 * 86400000).toISOString(),
    contact_id: 'c-001',
    contact_name: 'Rico Alvarez',
    clarity_score: null,
    message_snippet: null,
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

// ─── Lead-Gen / Outbound Engagement demo fixtures ────────────────────────────
// September demo of Zach's photo-booth division: "10,000 leads → a database →
// a funnel of engagement." Leads are event-industry prospects (wedding venues,
// event planners, corporate coordinators, party-rental shops). ~40 rows span all
// six funnel stages with varied engagement scores.

const LEADGEN_WS = 'demo-workspace-1'

function _engagementLabel(score: number): EngagementLabel {
  if (score >= 70) return 'hot'
  if (score >= 40) return 'warm'
  return 'cold'
}

function _signalsFor(stage: LeadStage, score: number): string[] {
  const base: Record<LeadStage, string[]> = {
    new: ['Imported from event-expo list', 'No outreach sent yet'],
    contacted: ['First email delivered', 'Awaiting reply'],
    engaged: ['Opened 3 of 4 emails', 'Clicked pricing link'],
    qualified: ['Replied requesting a quote', 'Confirmed event date'],
    converted: ['Signed booking contract', 'Deposit received'],
    lost: ['Went with a competitor', 'No response after 5 touches'],
  }
  return base[stage].concat(score >= 70 ? ['High engagement velocity'] : [])
}

// [name, company, title, stage, source, score]
const _LEAD_SEED: Array<[string, string, string, LeadStage, LeadSource, number]> = [
  // ── new (10) ──
  ['Hannah Brooks', 'Willowmere Barn Weddings', 'Venue Coordinator', 'new', 'import', 8],
  ['Diego Marín', 'Fiesta Party Rentals', 'Owner', 'new', 'import', 0],
  ['Priyanka Rao', 'Lotus Event Planning', 'Lead Planner', 'new', 'web', 14],
  ['Cody Franklin', 'Riverside Country Club', 'Events Manager', 'new', 'import', 5],
  ['Meredith Vaughn', 'The Gilded Hall', 'Sales Director', 'new', 'event', 18],
  ['Samuel Okafor', 'Summit Corporate Events', 'Program Manager', 'new', 'import', 3],
  ['Bethany Cole', 'Sweetgrass Farm Venue', 'Owner', 'new', 'referral', 12],
  ['Trevor Lang', 'Downtown Convention Center', 'Booking Lead', 'new', 'import', 0],
  ['Isabella Ferro', 'Bella Vista Vineyards', 'Hospitality Manager', 'new', 'web', 16],
  ['Marcus Webb', 'Northside High School', 'Prom Committee Chair', 'new', 'import', 6],
  // ── contacted (8) ──
  ['Angela Sørensen', 'Harbor Lights Ballroom', 'Events Director', 'contacted', 'import', 24],
  ['Ryan Coats', 'Peak Adventure Weddings', 'Coordinator', 'contacted', 'web', 33],
  ['Latoya Simmons', 'Grand Magnolia Estate', 'Venue Manager', 'contacted', 'referral', 28],
  ['Henrik Bauer', 'Bauer Brewing Co.', 'Taproom Events Lead', 'contacted', 'event', 21],
  ['Chloe Nakamura', 'Cherry Blossom Gardens', 'Owner', 'contacted', 'import', 37],
  ['Vincent Alfaro', 'Alfaro Catering & Events', 'General Manager', 'contacted', 'manual', 30],
  ['Grace Odenkirk', 'Lakeshore Resort', 'Group Sales', 'contacted', 'import', 26],
  ['Devin Pryce', 'Pryce Entertainment Group', 'Booking Agent', 'contacted', 'referral', 39],
  // ── engaged (7) ──
  ['Sofia Marchetti', 'Marchetti Manor', 'Events Director', 'engaged', 'web', 52],
  ['Omar Haddad', 'Skyline Rooftop Venue', 'Venue Owner', 'engaged', 'referral', 61],
  ['Kaitlyn Reyes', 'Evergreen Event Co.', 'Senior Planner', 'engaged', 'event', 47],
  ['Jerome Baptiste', 'Crescent Ballroom', 'Sales Manager', 'engaged', 'import', 58],
  ['Nadia Volkov', 'Aurora Gala Productions', 'Producer', 'engaged', 'web', 64],
  ['Tyler Mccabe', 'Mccabe Country Weddings', 'Owner', 'engaged', 'referral', 44],
  ['Ingrid Halvorsen', 'Fjord & Fern Events', 'Creative Director', 'engaged', 'manual', 55],
  // ── qualified (6) ──
  ['Rebecca Ortiz', 'The Ivory Rose Venue', 'Owner', 'qualified', 'referral', 72],
  ['Malik Johnson', 'Grandstand Corporate Retreats', 'Events Lead', 'qualified', 'web', 68],
  ['Yuki Tanaka', 'Zen Garden Weddings', 'Coordinator', 'qualified', 'event', 76],
  ['Fiona Callahan', 'Callahan Estate & Gardens', 'Sales Director', 'qualified', 'referral', 79],
  ['Andre Dupont', 'Chateau Belmont', 'Hospitality Lead', 'qualified', 'manual', 65],
  ['Simone Leclerc', 'Leclerc Luxury Events', 'Principal Planner', 'qualified', 'web', 74],
  // ── converted (5) ──
  ['Whitney Adair', 'Adair Grand Ballroom', 'Owner', 'converted', 'referral', 88],
  ['Rajiv Kapoor', 'Celebration Station Rentals', 'CEO', 'converted', 'web', 91],
  ['Elena Petrova', 'Petrova Wedding Collective', 'Founder', 'converted', 'event', 84],
  ['Brandon Stiles', 'Stiles Corporate Functions', 'Director', 'converted', 'referral', 82],
  ['Carmen Solis', 'Sol y Mar Beach Weddings', 'Venue Manager', 'converted', 'manual', 95],
  // ── lost (4) ──
  ['Gregory Voss', 'Voss Event Hall', 'Owner', 'lost', 'import', 22],
  ['Tabitha Nguyen', 'Golden Hour Photography Studio', 'Studio Lead', 'lost', 'web', 14],
  ['Dominic Reyes', 'Reyes Reunions & Galas', 'Organizer', 'lost', 'referral', 27],
  ['Paula Winters', 'Winterhaven Lodge', 'Events Coordinator', 'lost', 'import', 9],
]

// A couple of converted venues already have a booth installed and earning in the
// field — carried as booth metadata on the lead's schema-free customFields (no new type).
const _BOOTH_IN_FIELD: Record<string, { booth_model: string; install_date: string; venue: string }> = {
  'l-032': { booth_model: 'Open-Air Pro', install_date: '2026-08-12', venue: 'Adair Grand Ballroom' },
  'l-033': { booth_model: 'Mirror Booth X', install_date: '2026-08-19', venue: 'Celebration Station Rentals' },
}

export const demoLeads: Lead[] = _LEAD_SEED.map(([name, company, title, stage, source, score], i) => {
  const idNum = String(i + 1).padStart(3, '0')
  const daysAgo = 2 + i
  const email = name.toLowerCase().replace(/[^a-z]+/g, '.').replace(/^\.|\.$/g, '') +
    '@' + company.toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 16) + '.com'
  const engaged = stage !== 'new'
  return {
    id: `l-${idNum}`,
    workspaceId: LEADGEN_WS,
    contactId: stage === 'converted' ? `c-conv-${idNum}` : null,
    name,
    email,
    phone: `+1 (555) ${String(200 + i).padStart(3, '0')}-${String(1000 + i * 7).slice(-4)}`,
    company,
    title,
    source,
    stage,
    score,
    scoreDetail: {
      value: score,
      label: _engagementLabel(score),
      signals: _signalsFor(stage, score),
    },
    ownerId: null,
    customFields: { event_type: stage === 'lost' ? 'unknown' : 'wedding/corporate', guest_estimate: 80 + (i % 6) * 40, ...(_BOOTH_IN_FIELD[`l-${idNum}`] ?? {}) },
    externalId: `expo-2026-${idNum}`,
    lastEngagedAt: engaged ? new Date(Date.now() - daysAgo * 86400000).toISOString() : null,
    createdAt: new Date(Date.now() - (60 - i) * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - daysAgo * 86400000).toISOString(),
  }
})

// Funnel rollup derived from demoLeads (count + summed score per stage).
export function demoLeadFunnel(): LeadFunnelStage[] {
  const order: LeadStage[] = ['new', 'contacted', 'engaged', 'qualified', 'converted', 'lost']
  return order.map((stage) => {
    const rows = demoLeads.filter((l) => l.stage === stage)
    return { stage, count: rows.length, value: rows.reduce((a, l) => a + l.score, 0) }
  })
}

// ─── Segments ────────────────────────────────────────────────────────────────
export const demoSegments: Segment[] = [
  {
    id: 'seg-001',
    workspaceId: LEADGEN_WS,
    name: 'Wedding Venues — Fall 2026',
    description: 'Barns, estates, and vineyards booking fall wedding season.',
    kind: 'static',
    filter: {},
    memberCount: 14,
    createdAt: new Date(Date.now() - 30 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 4 * 86400000).toISOString(),
  },
  {
    id: 'seg-002',
    workspaceId: LEADGEN_WS,
    name: 'Hot Leads (score ≥ 70)',
    description: 'Dynamic: any lead scoring 70 or above right now.',
    kind: 'dynamic',
    filter: { minScore: 70 },
    memberCount: demoLeads.filter((l) => l.score >= 70).length,
    createdAt: new Date(Date.now() - 22 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 1 * 86400000).toISOString(),
  },
  {
    id: 'seg-003',
    workspaceId: LEADGEN_WS,
    name: 'Corporate Event Coordinators',
    description: 'Company holiday parties, retreats, and conferences.',
    kind: 'dynamic',
    filter: { tags: ['corporate'] },
    memberCount: 6,
    createdAt: new Date(Date.now() - 18 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 6 * 86400000).toISOString(),
  },
  {
    id: 'seg-004',
    workspaceId: LEADGEN_WS,
    name: 'Cold — Never Contacted',
    description: 'Dynamic: freshly imported leads still in the New stage.',
    kind: 'dynamic',
    filter: { stage: 'new' },
    memberCount: demoLeads.filter((l) => l.stage === 'new').length,
    createdAt: new Date(Date.now() - 12 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 2 * 86400000).toISOString(),
  },
]

// ─── Sequences (+ ordered steps) ─────────────────────────────────────────────
export const demoSequences: Sequence[] = [
  {
    id: 'sq-001',
    workspaceId: LEADGEN_WS,
    name: 'Wedding Venue Warm-Up (3-step)',
    description: 'Intro → gallery → limited-date offer for wedding venues.',
    channel: 'email',
    status: 'active',
    stepCount: 3,
    settings: { stop_on_reply: true, quiet_hours: [21, 8] },
    createdAt: new Date(Date.now() - 28 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 5 * 86400000).toISOString(),
    steps: [
      {
        id: 'ss-001-0', workspaceId: LEADGEN_WS, sequenceId: 'sq-001', stepOrder: 0,
        channel: 'email', delayHours: 0,
        subject: 'Photo booth magic for {{company}} events?',
        bodyTemplate: 'Hi {{name}},\n\nI run the photo-booth division here and {{company}} looks like a perfect fit for our open-air booths. Couples love the instant prints and the digital gallery.\n\nWould it be worth a quick chat about your fall dates?\n\nBest,\nZach',
        requiresApproval: true, aiGenerate: false,
        createdAt: new Date(Date.now() - 28 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 28 * 86400000).toISOString(),
      },
      {
        id: 'ss-001-1', workspaceId: LEADGEN_WS, sequenceId: 'sq-001', stepOrder: 1,
        channel: 'email', delayHours: 72,
        subject: 'A few booths in action at venues like yours',
        bodyTemplate: 'Hi {{name}},\n\nSharing a short gallery of setups from venues similar to {{company}}. The mirror booth has been a huge hit at estate weddings this year.\n\nHappy to hold a date if you have an event coming up.\n\nZach',
        requiresApproval: true, aiGenerate: true,
        createdAt: new Date(Date.now() - 28 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 28 * 86400000).toISOString(),
      },
      {
        id: 'ss-001-2', workspaceId: LEADGEN_WS, sequenceId: 'sq-001', stepOrder: 2,
        channel: 'email', delayHours: 120,
        subject: 'Holding fall dates for {{company}}',
        bodyTemplate: 'Hi {{name}},\n\nFall books up fast — I can pencil {{company}} in for a preferred-partner rate if we lock something this month. Want me to send a simple quote?\n\nZach',
        requiresApproval: true, aiGenerate: false,
        createdAt: new Date(Date.now() - 28 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 28 * 86400000).toISOString(),
      },
    ],
  },
  {
    id: 'sq-002',
    workspaceId: LEADGEN_WS,
    name: 'Corporate Holiday Party Outreach',
    description: 'Two-touch email + SMS for corporate event coordinators.',
    channel: 'mixed',
    status: 'draft',
    stepCount: 2,
    settings: { stop_on_reply: true },
    createdAt: new Date(Date.now() - 15 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 3 * 86400000).toISOString(),
    steps: [
      {
        id: 'ss-002-0', workspaceId: LEADGEN_WS, sequenceId: 'sq-002', stepOrder: 0,
        channel: 'email', delayHours: 0,
        subject: 'Holiday party photo booths — {{company}}',
        bodyTemplate: 'Hi {{name}},\n\nHoliday party season is around the corner. Our booths keep {{company}} employees laughing and hand them a printed keepsake on the way out. Want the corporate package?\n\nZach',
        requiresApproval: true, aiGenerate: false,
        createdAt: new Date(Date.now() - 15 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 15 * 86400000).toISOString(),
      },
      {
        id: 'ss-002-1', workspaceId: LEADGEN_WS, sequenceId: 'sq-002', stepOrder: 1,
        channel: 'sms', delayHours: 96,
        subject: null,
        bodyTemplate: 'Hi {{name}}, Zach here — following up on photo booths for the {{company}} holiday party. Happy to text over a quick quote!',
        requiresApproval: true, aiGenerate: false,
        createdAt: new Date(Date.now() - 15 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 15 * 86400000).toISOString(),
      },
    ],
  },
  {
    id: 'sq-003',
    workspaceId: LEADGEN_WS,
    name: 'Partner Onboarding & Education (3-step)',
    description: 'Welcome → drive-usage best practices → first revenue-share report for newly signed venue partners.',
    channel: 'email',
    status: 'active',
    stepCount: 3,
    settings: { stop_on_reply: false, quiet_hours: [21, 8] },
    createdAt: new Date(Date.now() - 20 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 2 * 86400000).toISOString(),
    steps: [
      {
        id: 'ss-003-0', workspaceId: LEADGEN_WS, sequenceId: 'sq-003', stepOrder: 0,
        channel: 'email', delayHours: 0,
        subject: 'Welcome aboard, {{company}} — your booth is live',
        bodyTemplate: 'Hi {{name}},\n\nWelcome to the partner program! Your booth is installed and earning. Here\'s how the revenue-share works: patrons pay per session, prints are unlimited, and your split is deposited monthly. Your field contact is on call for swaps and restocks.\n\nExpect your first payout summary in ~30 days.\n\nZach',
        requiresApproval: false, aiGenerate: false,
        createdAt: new Date(Date.now() - 20 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 20 * 86400000).toISOString(),
      },
      {
        id: 'ss-003-1', workspaceId: LEADGEN_WS, sequenceId: 'sq-003', stepOrder: 1,
        channel: 'email', delayHours: 72,
        subject: 'Getting the most from your booth at {{company}}',
        bodyTemplate: 'Hi {{name}},\n\nA few things partners do to boost booth revenue: put the tabletop sign at the bar, have staff point guests to it on busy nights, and run a "share to unlock a free print" prompt. Weekends and events are where the numbers jump.\n\nWant a peak-night attendant added? Just reply.\n\nZach',
        requiresApproval: false, aiGenerate: true,
        createdAt: new Date(Date.now() - 20 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 20 * 86400000).toISOString(),
      },
      {
        id: 'ss-003-2', workspaceId: LEADGEN_WS, sequenceId: 'sq-003', stepOrder: 2,
        channel: 'email', delayHours: 168,
        subject: 'Your first revenue-share report is ready',
        bodyTemplate: 'Hi {{name}},\n\nYour first monthly report for {{company}} is ready: total sessions, prints, digital gallery scans, and your revenue-share deposit. If the numbers look strong, a second booth usually pays for itself fast — happy to scope one.\n\nZach',
        requiresApproval: false, aiGenerate: false,
        createdAt: new Date(Date.now() - 20 * 86400000).toISOString(),
        updatedAt: new Date(Date.now() - 20 * 86400000).toISOString(),
      },
    ],
  },
]

// ─── Campaigns ───────────────────────────────────────────────────────────────
export const demoCampaigns: Campaign[] = [
  {
    id: 'cmp-001',
    workspaceId: LEADGEN_WS,
    segmentId: 'seg-001',
    sequenceId: 'sq-001',
    name: 'Fall Wedding Season Blast',
    status: 'active',
    channel: 'email',
    scheduledAt: new Date(Date.now() - 8 * 86400000).toISOString(),
    startedAt: new Date(Date.now() - 8 * 86400000).toISOString(),
    completedAt: null,
    stats: { enrolled: 14, sent: 31, opened: 19, clicked: 7, replied: 4, converted: 2 },
    settings: { daily_cap: 50, sender_identity: 'zach@photoboothco.com' },
    createdAt: new Date(Date.now() - 10 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 1 * 86400000).toISOString(),
  },
  {
    id: 'cmp-002',
    workspaceId: LEADGEN_WS,
    segmentId: 'seg-003',
    sequenceId: 'sq-002',
    name: 'Corporate Holiday Parties',
    status: 'scheduled',
    channel: 'mixed',
    scheduledAt: new Date(Date.now() + 6 * 86400000).toISOString(),
    startedAt: null,
    completedAt: null,
    stats: { enrolled: 0, sent: 0, opened: 0, clicked: 0, replied: 0, converted: 0 },
    settings: { daily_cap: 30 },
    createdAt: new Date(Date.now() - 4 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 2 * 86400000).toISOString(),
  },
  {
    id: 'cmp-003',
    workspaceId: LEADGEN_WS,
    segmentId: 'seg-004',
    sequenceId: null,
    name: 'Cold Lead Reactivation',
    status: 'draft',
    channel: 'email',
    scheduledAt: null,
    startedAt: null,
    completedAt: null,
    stats: {},
    settings: {},
    createdAt: new Date(Date.now() - 3 * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 3 * 86400000).toISOString(),
  },
]

// ─── Enrollments (live positions in the Fall Wedding campaign) ───────────────
export const demoEnrollments: Enrollment[] = [
  { id: 'en-001', workspaceId: LEADGEN_WS, campaignId: 'cmp-001', sequenceId: 'sq-001', leadId: 'l-019', currentStep: 1, status: 'waiting', nextRunAt: new Date(Date.now() + 6 * 3600000).toISOString(), lastSentAt: new Date(Date.now() - 2 * 86400000).toISOString(), createdAt: new Date(Date.now() - 8 * 86400000).toISOString(), updatedAt: new Date(Date.now() - 2 * 86400000).toISOString() },
  { id: 'en-002', workspaceId: LEADGEN_WS, campaignId: 'cmp-001', sequenceId: 'sq-001', leadId: 'l-020', currentStep: 2, status: 'active', nextRunAt: new Date(Date.now() + 1 * 86400000).toISOString(), lastSentAt: new Date(Date.now() - 1 * 86400000).toISOString(), createdAt: new Date(Date.now() - 8 * 86400000).toISOString(), updatedAt: new Date(Date.now() - 1 * 86400000).toISOString() },
  { id: 'en-003', workspaceId: LEADGEN_WS, campaignId: 'cmp-001', sequenceId: 'sq-001', leadId: 'l-025', currentStep: 0, status: 'waiting', nextRunAt: new Date(Date.now() - 1 * 3600000).toISOString(), lastSentAt: null, createdAt: new Date(Date.now() - 3 * 86400000).toISOString(), updatedAt: new Date(Date.now() - 3 * 86400000).toISOString() },
  { id: 'en-004', workspaceId: LEADGEN_WS, campaignId: 'cmp-001', sequenceId: 'sq-001', leadId: 'l-031', currentStep: 3, status: 'completed', nextRunAt: null, lastSentAt: new Date(Date.now() - 5 * 86400000).toISOString(), createdAt: new Date(Date.now() - 8 * 86400000).toISOString(), updatedAt: new Date(Date.now() - 5 * 86400000).toISOString() },
  { id: 'en-005', workspaceId: LEADGEN_WS, campaignId: 'cmp-001', sequenceId: 'sq-001', leadId: 'l-021', currentStep: 1, status: 'stopped', nextRunAt: null, lastSentAt: new Date(Date.now() - 4 * 86400000).toISOString(), createdAt: new Date(Date.now() - 8 * 86400000).toISOString(), updatedAt: new Date(Date.now() - 4 * 86400000).toISOString() },
  { id: 'en-006', workspaceId: LEADGEN_WS, campaignId: 'cmp-001', sequenceId: 'sq-001', leadId: 'l-024', currentStep: 0, status: 'waiting', nextRunAt: new Date(Date.now() - 30 * 60000).toISOString(), lastSentAt: null, createdAt: new Date(Date.now() - 2 * 86400000).toISOString(), updatedAt: new Date(Date.now() - 2 * 86400000).toISOString() },
]

// ─── Pending outreach (bot → human approval queue) ───────────────────────────
function _leadLabel(leadId: string): { name: string | null; company: string | null } {
  const l = demoLeads.find((x) => x.id === leadId)
  return { name: l?.name ?? null, company: l?.company ?? null }
}

export const demoPendingOutreach: PendingOutreach[] = [
  {
    enrollmentId: 'en-003', leadId: 'l-025', campaignId: 'cmp-001', sequenceId: 'sq-001',
    currentStep: 0, status: 'waiting',
    subject: 'Photo booth magic for The Ivory Rose Venue events?',
    body: 'Hi Rebecca,\n\nI run the photo-booth division here and The Ivory Rose Venue looks like a perfect fit for our open-air booths. Couples love the instant prints and the digital gallery.\n\nWould it be worth a quick chat about your fall dates?\n\nBest,\nZach',
    leadName: _leadLabel('l-025').name, leadCompany: _leadLabel('l-025').company, aiGenerated: false,
  },
  {
    enrollmentId: 'en-006', leadId: 'l-024', campaignId: 'cmp-001', sequenceId: 'sq-001',
    currentStep: 0, status: 'waiting',
    subject: 'Photo booth magic for Tyler Mccabe Country Weddings events?',
    body: 'Hi Tyler,\n\nI run the photo-booth division here and Mccabe Country Weddings looks like a perfect fit for our open-air booths. Couples love the instant prints and the digital gallery.\n\nWould it be worth a quick chat about your fall dates?\n\nBest,\nZach',
    leadName: _leadLabel('l-024').name, leadCompany: _leadLabel('l-024').company, aiGenerated: false,
  },
  {
    enrollmentId: 'en-001', leadId: 'l-019', campaignId: 'cmp-001', sequenceId: 'sq-001',
    currentStep: 1, status: 'waiting',
    subject: 'A few booths in action at venues like yours',
    body: 'Hi Sofia,\n\nSharing a short gallery of setups from venues similar to Marchetti Manor. The mirror booth has been a huge hit at estate weddings this year.\n\nHappy to hold a date if you have an event coming up.\n\nZach',
    leadName: _leadLabel('l-019').name, leadCompany: _leadLabel('l-019').company, aiGenerated: true,
  },
  {
    enrollmentId: 'en-002', leadId: 'l-020', campaignId: 'cmp-001', sequenceId: 'sq-001',
    currentStep: 2, status: 'waiting',
    subject: 'Holding fall dates for Skyline Rooftop Venue',
    body: 'Hi Omar,\n\nFall books up fast — I can pencil Skyline Rooftop Venue in for a preferred-partner rate if we lock something this month. Want me to send a simple quote?\n\nZach',
    leadName: _leadLabel('l-020').name, leadCompany: _leadLabel('l-020').company, aiGenerated: false,
  },
]

// ─── Engagement events (timeline for a couple of active leads) ───────────────
export const demoEngagementEvents: EngagementEvent[] = [
  { id: 'ee-001', workspaceId: LEADGEN_WS, leadId: 'l-020', campaignId: 'cmp-001', enrollmentId: 'en-002', stepId: 'ss-001-0', type: 'sent', channel: 'email', weight: 0, metadata: { subject: 'Photo booth magic for Skyline Rooftop Venue events?' }, occurredAt: new Date(Date.now() - 7 * 86400000).toISOString(), createdAt: new Date(Date.now() - 7 * 86400000).toISOString() },
  { id: 'ee-002', workspaceId: LEADGEN_WS, leadId: 'l-020', campaignId: 'cmp-001', enrollmentId: 'en-002', stepId: 'ss-001-0', type: 'opened', channel: 'email', weight: 5, metadata: {}, occurredAt: new Date(Date.now() - 6.8 * 86400000).toISOString(), createdAt: new Date(Date.now() - 6.8 * 86400000).toISOString() },
  { id: 'ee-003', workspaceId: LEADGEN_WS, leadId: 'l-020', campaignId: 'cmp-001', enrollmentId: 'en-002', stepId: 'ss-001-0', type: 'clicked', channel: 'email', weight: 15, metadata: { url: 'https://photoboothco.com/gallery' }, occurredAt: new Date(Date.now() - 6.7 * 86400000).toISOString(), createdAt: new Date(Date.now() - 6.7 * 86400000).toISOString() },
  { id: 'ee-004', workspaceId: LEADGEN_WS, leadId: 'l-020', campaignId: 'cmp-001', enrollmentId: 'en-002', stepId: 'ss-001-1', type: 'sent', channel: 'email', weight: 0, metadata: {}, occurredAt: new Date(Date.now() - 4 * 86400000).toISOString(), createdAt: new Date(Date.now() - 4 * 86400000).toISOString() },
  { id: 'ee-005', workspaceId: LEADGEN_WS, leadId: 'l-020', campaignId: 'cmp-001', enrollmentId: 'en-002', stepId: 'ss-001-1', type: 'opened', channel: 'email', weight: 5, metadata: {}, occurredAt: new Date(Date.now() - 3.9 * 86400000).toISOString(), createdAt: new Date(Date.now() - 3.9 * 86400000).toISOString() },
  { id: 'ee-006', workspaceId: LEADGEN_WS, leadId: 'l-020', campaignId: 'cmp-001', enrollmentId: 'en-002', stepId: 'ss-001-1', type: 'replied', channel: 'email', weight: 30, metadata: { snippet: 'What are your fall rates?' }, occurredAt: new Date(Date.now() - 3.5 * 86400000).toISOString(), createdAt: new Date(Date.now() - 3.5 * 86400000).toISOString() },
  { id: 'ee-007', workspaceId: LEADGEN_WS, leadId: 'l-031', campaignId: 'cmp-001', enrollmentId: 'en-004', stepId: 'ss-001-2', type: 'converted', channel: 'email', weight: 40, metadata: { deal: 'Fall wedding booking' }, occurredAt: new Date(Date.now() - 5 * 86400000).toISOString(), createdAt: new Date(Date.now() - 5 * 86400000).toISOString() },
  { id: 'ee-008', workspaceId: LEADGEN_WS, leadId: 'l-021', campaignId: 'cmp-001', enrollmentId: 'en-005', stepId: 'ss-001-0', type: 'bounced', channel: 'email', weight: -20, metadata: { reason: 'mailbox full' }, occurredAt: new Date(Date.now() - 6 * 86400000).toISOString(), createdAt: new Date(Date.now() - 6 * 86400000).toISOString() },
  { id: 'ee-009', workspaceId: LEADGEN_WS, leadId: 'l-025', campaignId: 'cmp-001', enrollmentId: 'en-003', stepId: 'ss-001-0', type: 'queued', channel: 'email', weight: 0, metadata: {}, occurredAt: new Date(Date.now() - 1 * 3600000).toISOString(), createdAt: new Date(Date.now() - 1 * 3600000).toISOString() },
  { id: 'ee-010', workspaceId: LEADGEN_WS, leadId: 'l-019', campaignId: 'cmp-001', enrollmentId: 'en-001', stepId: 'ss-001-0', type: 'opened', channel: 'email', weight: 5, metadata: {}, occurredAt: new Date(Date.now() - 3 * 86400000).toISOString(), createdAt: new Date(Date.now() - 3 * 86400000).toISOString() },
]

// Per-lead engagement-event lookup for the lead detail timeline.
export function demoLeadEvents(leadId: string): EngagementEvent[] {
  return demoEngagementEvents
    .filter((e) => e.leadId === leadId)
    .sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime())
}
