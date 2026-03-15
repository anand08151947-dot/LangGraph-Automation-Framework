
import React from 'react';
import { WorkflowStatus, Template, WorkflowRun, Artifact } from './types';

export const NAV_ITEMS = [
  { label: 'Dashboard', icon: <i className="fas fa-home"></i>, path: '/' },
  { label: 'Templates Library', icon: <i className="fas fa-book"></i>, path: '/templates' },
  { label: 'Workflow Builder', icon: <i className="fas fa-project-diagram"></i>, path: '/builder' },
  { label: 'Translation', icon: <i className="fas fa-language"></i>, path: '/translation' },
  { label: 'Orchestration', icon: <i className="fas fa-microchip"></i>, path: '/monitor' },
  { label: 'Tool Registry', icon: <i className="fas fa-plug"></i>, path: '/tools' },
  { label: 'Audit Log', icon: <i className="fas fa-clipboard-list"></i>, path: '/audit' },
  { label: 'Artifact Export', icon: <i className="fas fa-download"></i>, path: '/export' },
  { label: 'Settings', icon: <i className="fas fa-cog"></i>, path: '/settings' },
  { label: 'Help & Docs', icon: <i className="fas fa-question-circle"></i>, path: '/docs' },
];

export const MOCK_TEMPLATES: Template[] = [
  {
    id: '1',
    name: 'Customer Support Bot',
    description: 'A multi-agent system for handling customer inquiries and ticket routing.',
    domain: 'Customer Service',
    configJson: '{\n  "agents": ["Triage", "Resolver"],\n  "tools": ["Zendesk", "Slack"]\n}'
  },
  {
    id: '2',
    name: 'Research Assistant',
    description: 'Aggregates data from multiple sources and generates reports.',
    domain: 'Education',
    configJson: '{\n  "agents": ["Researcher", "Writer"],\n  "tools": ["GoogleSearch", "Wikipedia"]\n}'
  },
  {
    id: '3',
    name: 'Code Reviewer',
    description: 'Automated agent to scan pull requests for bugs and style issues.',
    domain: 'Software Dev',
    configJson: '{\n  "agents": ["Linter", "Architect"],\n  "tools": ["Git", "SonarCloud"]\n}'
  }
];

export const MOCK_RUNS: WorkflowRun[] = [
  { id: 'run-1', name: 'Research Task', status: WorkflowStatus.COMPLETED, startTime: '2026-03-12 17:30', logs: [] },
  { id: 'run-2', name: 'Customer Onboarding', status: WorkflowStatus.RUNNING, startTime: '2026-03-12 17:50', logs: [] },
  { id: 'run-3', name: 'Data Pipeline Test', status: WorkflowStatus.FAILED, startTime: '2026-03-12 16:45', logs: [] },
  { id: 'run-4', name: 'Code Review Bot', status: WorkflowStatus.PENDING, startTime: '2026-03-12 18:00', logs: [] },
];


