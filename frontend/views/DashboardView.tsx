
import React, { useEffect, useState } from 'react';
import { Card, Button, Badge } from '../components/Shared';
import { WorkflowRun, WorkflowStatus } from '../types';
import { getWorkflowRuns } from '../services/api.runs';
import branding from '../branding';

const DashboardView: React.FC<{ onNavigate: (path: string) => void }> = ({ onNavigate }) => {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);

  useEffect(() => {
    getWorkflowRuns().then(setRuns).catch(() => setRuns([]));
  }, []);

  const totalRuns = runs.length;
  const completed = runs.filter(r => r.status === WorkflowStatus.COMPLETED).length;
  const running = runs.filter(r => r.status === WorkflowStatus.RUNNING).length;
  const failed = runs.filter(r => r.status === WorkflowStatus.FAILED).length;
  const successRate = totalRuns > 0 ? ((completed / totalRuns) * 100).toFixed(1) : '0';

  const stats = [
    { label: 'Total Runs', value: String(totalRuns), icon: 'fa-project-diagram', color: 'text-indigo-600' },
    { label: 'Active Runs', value: String(running), icon: 'fa-clock', color: 'text-emerald-600' },
    { label: 'Success Rate', value: `${successRate}%`, icon: 'fa-check-circle', color: 'text-blue-600' },
    { label: 'Failed Runs', value: String(failed), icon: 'fa-exclamation-circle', color: 'text-amber-600' },
  ];

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Welcome Hero */}
      <div
        className="rounded-2xl p-8 text-white flex flex-col md:flex-row items-center justify-between gap-6 shadow-xl"
        style={{ background: `linear-gradient(135deg, ${branding.colors.accent}, ${branding.colors.accentDark})` }}
      >
        <div className="space-y-2">
          <h1 className="text-3xl font-bold">{branding.heroWelcome(branding.user.name)}</h1>
          <p className="max-w-md" style={{ color: branding.colors.heroText }}>{branding.heroSubtitle}</p>
          <div className="pt-4">
            <Button variant="secondary" onClick={() => onNavigate('/builder')} className="!border-none font-semibold" style={{ color: branding.colors.accentDark } as any}>
              <i className="fas fa-plus mr-2"></i> Create New Workflow
            </Button>
          </div>
        </div>
        <div className="hidden md:block">
          <div className="w-48 h-48 bg-white/10 rounded-full flex items-center justify-center backdrop-blur-sm border border-white/20">
            <i className="fas fa-robot text-6xl text-white/50"></i>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, i) => (
          <Card key={i} className="hover:border-indigo-200 transition-colors cursor-default">
            <div className="flex items-center gap-4">
              <div className={`w-12 h-12 rounded-xl bg-slate-50 flex items-center justify-center text-xl ${stat.color}`}>
                <i className={`fas ${stat.icon}`}></i>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">{stat.label}</p>
                <p className="text-2xl font-bold text-slate-800">{stat.value}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Main Dashboard Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Recent Workflows */}
        <Card title="Recent Orchestrations" className="lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-xs uppercase text-slate-400 font-bold border-b border-slate-100">
                  <th className="pb-4 font-bold">Workflow Name</th>
                  <th className="pb-4 font-bold">Started At</th>
                  <th className="pb-4 font-bold text-center">Status</th>
                  <th className="pb-4 font-bold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((run) => (
                  <tr key={run.id} className="group hover:bg-slate-50 transition-colors">
                    <td className="py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600">
                          <i className="fas fa-brain text-xs"></i>
                        </div>
                        <span className="font-medium text-slate-700">{run.name}</span>
                      </div>
                    </td>
                    <td className="py-4 text-sm text-slate-500">{run.startTime}</td>
                    <td className="py-4 text-center">
                      <Badge type={run.status} label={run.status} />
                    </td>
                    <td className="py-4 text-right">
                      <button className="text-slate-400 hover:text-indigo-600 transition-colors" title="View details">
                        <i className="fas fa-external-link-alt"></i>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-6">
            <Button variant="ghost" onClick={() => onNavigate('/monitor')} className="w-full">
              View All Runs
            </Button>
          </div>
        </Card>

        {/* Quick Help / Activity */}
        <div className="space-y-6">
          <Card title="Activity Feed">
            <div className="space-y-6">
              {[
                { time: '10m ago', text: 'Workflow "Research Task" completed successfully.' },
                { time: '2h ago', text: 'New template "Customer Support" added to library.' },
                { time: '5h ago', text: 'Updated API key for OpenAI module.' },
              ].map((item, i) => (
                <div key={i} className="flex gap-4">
                  <div className="mt-1 w-2 h-2 rounded-full bg-indigo-500 ring-4 ring-indigo-50"></div>
                  <div>
                    <p className="text-sm text-slate-700">{item.text}</p>
                    <p className="text-xs text-slate-400 font-medium">{item.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-indigo-500 to-purple-600 !text-white border-none">
            <h3 className="font-bold mb-2">Need a custom agent?</h3>
            <p className="text-sm text-white/80 mb-4">Chat with our AI translator to convert complex business logic into JSON workflows in seconds.</p>
            <Button variant="secondary" className="w-full !text-indigo-600 !border-none" onClick={() => onNavigate('/translation')}>
              Open Translator
            </Button>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default DashboardView;
