
import React from 'react';
import { WorkflowStatus, Template, WorkflowRun, Artifact } from './types';

export const NAV_ITEMS = [
  { label: 'Dashboard', icon: <i className="fas fa-home"></i>, path: '/' },
  { label: 'Templates Library', icon: <i className="fas fa-book"></i>, path: '/templates' },
  { label: 'Workflow Builder', icon: <i className="fas fa-project-diagram"></i>, path: '/builder' },
  { label: 'Translation', icon: <i className="fas fa-language"></i>, path: '/translation' },
  { label: 'Orchestration', icon: <i className="fas fa-microchip"></i>, path: '/monitor' },
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


