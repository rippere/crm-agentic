/**
 * mock-data.ts — thin re-export layer used by pages directly.
 * All data lives in demo-data.ts; this file just aliases to the names
 * the pages expect.
 */
export {
  demoContacts as mockContacts,
  demoDeals as mockDeals,
  demoAgents as mockAgents,
  demoActivity as mockActivity,
  demoKPIs as mockKPIs,
  demoRevenueChartData as revenueChartData,
  demoAgentAccuracyData as agentAccuracyData,
} from './demo-data'
