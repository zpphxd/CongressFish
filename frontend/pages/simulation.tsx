import React, { useState } from 'react';
import { Loader, AlertCircle, CheckCircle } from 'lucide-react';

interface SimulationState {
  simulationId?: string;
  status: 'idle' | 'uploading' | 'running' | 'complete' | 'error';
  progress: number;
  progressStage?: string;
  bill?: {
    title: string;
    description: string;
  };
  results?: any;
  error?: string;
}

interface SelectedMember {
  bioguide_id: string;
  full_name: string;
  position: any;
}

export default function SimulationPage() {
  const [state, setState] = useState<SimulationState>({ status: 'idle', progress: 0, progressStage: '' });
  const [billQuery, setBillQuery] = useState('');
  const [billFile, setBillFile] = useState<File | null>(null);
  const [selectedMember, setSelectedMember] = useState<SelectedMember | null>(null);
  const [selectedBranches, setSelectedBranches] = useState<Set<string>>(
    new Set(['house', 'senate'])
  );

  const branches = [
    { id: 'house', label: '🏛️ House of Representatives', color: 'blue' },
    { id: 'senate', label: '⚖️ Senate', color: 'indigo' },
    { id: 'executive', label: '✋ Executive Branch', color: 'red' },
    { id: 'judicial', label: '⚔️ Judicial Branch', color: 'purple' },
  ];

  const toggleBranch = (branchId: string) => {
    const newBranches = new Set(selectedBranches);
    if (newBranches.has(branchId)) {
      newBranches.delete(branchId);
    } else {
      newBranches.add(branchId);
    }
    setSelectedBranches(newBranches);
  };

  const selectAllBranches = () => {
    setSelectedBranches(new Set(branches.map(b => b.id)));
  };

  const handleStartSimulation = async () => {
    if (!billQuery.trim()) {
      setState(prev => ({
        ...prev,
        status: 'error',
        error: 'Please describe a bill or policy'
      }));
      return;
    }

    setState({ status: 'running', progress: 0, bill: { title: billQuery, description: billQuery } });

    try {
      const scope = selectedBranches.size === 4 ? 'all' : Array.from(selectedBranches).join(',');

      const response = await fetch('/api/simulation/congressfish/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: billQuery,
          scope,
        }),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || data.detail || 'Failed to start simulation');
      }

      const simulationId = data.data.simulation_id;
      setState(prev => ({ ...prev, simulationId, progress: 5 }));

      // Poll for completion
      pollSimulation(simulationId);
    } catch (error) {
      setState(prev => ({
        ...prev,
        status: 'error',
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  };

  const pollSimulation = async (simulationId: string) => {
    const maxAttempts = 600; // 10 minutes with 1 second polling
    let attempts = 0;

    const poll = async () => {
      try {
        const statusResponse = await fetch(`/api/simulation/congressfish/${simulationId}/status`);
        const statusData = await statusResponse.json();

        if (!statusResponse.ok || !statusData.success) {
          throw new Error(statusData.error || 'Status check failed');
        }

        const status = statusData.data;

        const progressStages = [
          { threshold: 10, label: 'Loading members from personas...' },
          { threshold: 40, label: 'Building debate context...' },
          { threshold: 70, label: 'Running OASIS debate rounds...' },
          { threshold: 90, label: 'Tallying votes...' },
          { threshold: 100, label: 'Simulation complete!' }
        ];

        const currentStage = progressStages.find(s => status.progress <= s.threshold)?.label || 'Processing...';

        setState(prev => ({ ...prev, progress: Math.min(status.progress || 50, 99), progressStage: currentStage }));

        if (status.status === 'complete') {
          // Fetch results
          const resultsResponse = await fetch(`/api/simulation/congressfish/${simulationId}/results`);
          const resultsData = await resultsResponse.json();

          if (!resultsResponse.ok || !resultsData.success) {
            throw new Error(resultsData.error || 'Failed to fetch results');
          }

          setState(prev => ({
            ...prev,
            status: 'complete',
            progress: 100,
            results: resultsData.data,
          }));
        } else if (status.status === 'error') {
          setState(prev => ({
            ...prev,
            status: 'error',
            error: status.error || 'Simulation failed',
          }));
        } else if (attempts < maxAttempts) {
          attempts++;
          setTimeout(poll, 1000);
        } else {
          setState(prev => ({
            ...prev,
            status: 'error',
            error: 'Simulation timeout',
          }));
        }
      } catch (error) {
        setState(prev => ({
          ...prev,
          status: 'error',
          error: error instanceof Error ? error.message : 'Poll error',
        }));
      }
    };

    poll();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="border-b border-slate-700 bg-slate-800/50 backdrop-blur">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex items-center gap-4 mb-2">
            <h1 className="text-4xl font-bold text-white">🏛️ CongressFish</h1>
            <span className="px-3 py-1 bg-blue-500/20 text-blue-300 rounded-full text-sm">
              Bill Simulation Engine
            </span>
          </div>
          <p className="text-slate-400">
            Propose bills, watch Congress debate them, see how members vote based on their
            ideology, committees, and interests
          </p>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Input Panel */}
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-white mb-4">Propose a Bill</h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Bill Document (Optional)
                  </label>
                  <div className="border-2 border-dashed border-slate-600 rounded px-3 py-4 text-center bg-slate-700/50 hover:bg-slate-700 transition cursor-pointer">
                    <input
                      type="file"
                      accept=".pdf,.txt,.md"
                      onChange={e => setBillFile(e.target.files?.[0] || null)}
                      disabled={state.status === 'running'}
                      className="hidden"
                      id="bill-upload"
                    />
                    <label htmlFor="bill-upload" className="cursor-pointer block">
                      <div className="text-2xl mb-2">📄</div>
                      <p className="text-sm text-slate-300">
                        {billFile ? billFile.name : 'Click to upload or drag PDF/TXT'}
                      </p>
                    </label>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Bill Description
                  </label>
                  <textarea
                    value={billQuery}
                    onChange={e => setBillQuery(e.target.value)}
                    placeholder="E.g., 'Comprehensive climate action bill with carbon pricing, renewable energy investments, and grid modernization...'"
                    className="w-full h-24 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={state.status === 'running'}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-3">
                    Which branches participate?
                  </label>

                  <div className="space-y-2 mb-4">
                    {branches.map(branch => (
                      <label key={branch.id} className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedBranches.has(branch.id)}
                          onChange={() => toggleBranch(branch.id)}
                          disabled={state.status === 'running'}
                          className="w-4 h-4 rounded border-slate-500"
                        />
                        <span className="text-slate-300">{branch.label}</span>
                      </label>
                    ))}
                  </div>

                  <button
                    onClick={selectAllBranches}
                    disabled={state.status === 'running'}
                    className="text-sm text-blue-400 hover:text-blue-300 disabled:opacity-50"
                  >
                    ✓ Select All
                  </button>
                </div>

                <div className="pt-4 space-y-2">
                  <button
                    onClick={handleStartSimulation}
                    disabled={state.status === 'running' || !billQuery.trim()}
                    className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white font-semibold py-2 rounded-lg transition"
                  >
                    {state.status === 'running' ? (
                      <div className="flex items-center justify-center gap-2">
                        <Loader className="w-4 h-4 animate-spin" />
                        Running...
                      </div>
                    ) : (
                      'Start Simulation'
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Results Panel */}
          <div className="lg:col-span-2">
            {state.status === 'idle' && (
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-12 text-center">
                <div className="text-6xl mb-4">📜</div>
                <h3 className="text-xl font-semibold text-white mb-2">Ready to simulate</h3>
                <p className="text-slate-400">
                  Describe a bill in the left panel and select which branches of government
                  should debate it. The simulation will:
                </p>
                <ul className="text-slate-400 text-sm mt-4 space-y-2">
                  <li>✓ Load relevant members from Neo4j</li>
                  <li>✓ Predict each member's position using their persona</li>
                  <li>✓ Generate debate statements between members</li>
                  <li>✓ Tally votes and determine outcomes</li>
                </ul>
              </div>
            )}

            {state.status === 'running' && (
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-12 space-y-8">
                <div className="text-center space-y-4">
                  <Loader className="w-12 h-12 animate-spin text-blue-500 mx-auto" />
                  <div>
                    <h3 className="text-xl font-semibold text-white mb-2">
                      Simulating congressional debate...
                    </h3>
                    <p className="text-slate-400 text-sm font-medium">
                      {state.progressStage}
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Progress</span>
                    <span className="text-slate-300 font-semibold">{state.progress}%</span>
                  </div>
                  <div className="bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-blue-600 h-full transition-all duration-300"
                      style={{ width: `${Math.max(state.progress, 5)}%` }}
                    />
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div className={state.progress >= 10 ? 'text-green-400' : 'text-slate-500'}>✓ Loading members</div>
                  <div className={state.progress >= 40 ? 'text-green-400' : 'text-slate-500'}>✓ Predicting positions</div>
                  <div className={state.progress >= 70 ? 'text-green-400' : 'text-slate-500'}>✓ Running debate</div>
                  <div className={state.progress >= 90 ? 'text-green-400' : 'text-slate-500'}>✓ Tallying votes</div>
                </div>
              </div>
            )}

            {state.status === 'complete' && state.results && (
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-8 space-y-6">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-6 h-6 text-green-500" />
                  <h3 className="text-xl font-semibold text-white">Simulation Complete</h3>
                </div>

                {/* Vote Results */}
                <div className="bg-slate-700 rounded-lg p-4">
                  <h4 className="font-semibold text-white mb-3">Vote Results</h4>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-500">
                        {state.results.vote_results?.yes || 0}
                      </div>
                      <div className="text-sm text-slate-400">Yes</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-red-500">
                        {state.results.vote_results?.no || 0}
                      </div>
                      <div className="text-sm text-slate-400">No</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-slate-400">
                        {state.results.vote_results?.abstain || 0}
                      </div>
                      <div className="text-sm text-slate-400">Abstain</div>
                    </div>
                  </div>

                  <div className="mt-4 p-3 bg-slate-600 rounded">
                    <div className="text-lg font-bold text-white">
                      {state.results.vote_results?.passes ? '✓ PASSES' : '✗ FAILS'}
                    </div>
                    <div className="text-sm text-slate-300">
                      Margin: {state.results.vote_results?.margin || 0} votes (
                      {((state.results.vote_results?.percentage_yes || 0) * 100).toFixed(1)}%)
                    </div>
                  </div>
                </div>

                {/* Member Positions */}
                <div className="bg-slate-700 rounded-lg p-4">
                  <h4 className="font-semibold text-white mb-3">Member Positions (click for details)</h4>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {Object.entries(state.results.member_positions || {}).map(([bioguide, position]: any) => (
                      <button
                        key={bioguide}
                        onClick={() => setSelectedMember({ bioguide_id: bioguide, full_name: position.full_name, position })}
                        className="w-full text-sm flex items-center justify-between p-2 bg-slate-600 hover:bg-slate-550 rounded transition text-left"
                      >
                        <div>
                          <span className="text-slate-200">{position.full_name}</span>
                          <span className="text-slate-400 text-xs ml-2">({position.chamber})</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-1 rounded text-xs font-semibold ${
                              position.position === 'yes'
                                ? 'bg-green-900 text-green-200'
                                : position.position === 'no'
                                ? 'bg-red-900 text-red-200'
                                : 'bg-slate-500 text-slate-100'
                            }`}
                          >
                            {position.position?.toUpperCase()}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <button
                  onClick={() => setState({ status: 'idle', progress: 0 })}
                  className="w-full bg-slate-700 hover:bg-slate-600 text-white font-semibold py-2 rounded-lg transition"
                >
                  New Simulation
                </button>
              </div>
            )}

            {state.status === 'error' && (
              <div className="bg-red-900/30 border border-red-700 rounded-lg p-8 flex items-start gap-4">
                <AlertCircle className="w-6 h-6 text-red-500 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-red-200 mb-1">Error</h3>
                  <p className="text-red-300 text-sm mb-4">{state.error}</p>
                  <button
                    onClick={() => setState({ status: 'idle', progress: 0 })}
                    className="text-red-300 hover:text-red-200 text-sm underline"
                  >
                    Try again
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Member Detail Modal */}
      {selectedMember && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
          onClick={() => setSelectedMember(null)}
        >
          <div
            className="bg-slate-800 border border-slate-700 rounded-lg p-6 max-w-md w-full max-h-96 overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white">{selectedMember.full_name}</h3>
                <p className="text-sm text-slate-400">{selectedMember.position.party === 'D' ? 'Democrat' : selectedMember.position.party === 'R' ? 'Republican' : 'Independent'}</p>
              </div>
              <button
                onClick={() => setSelectedMember(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3">
              <div className="bg-slate-700 rounded p-3">
                <p className="text-xs text-slate-400 mb-1">Position</p>
                <p className={`text-lg font-bold ${
                  selectedMember.position.position === 'yes'
                    ? 'text-green-400'
                    : selectedMember.position.position === 'no'
                    ? 'text-red-400'
                    : 'text-slate-400'
                }`}>
                  {selectedMember.position.position?.toUpperCase()}
                </p>
              </div>

              <div className="bg-slate-700 rounded p-3">
                <p className="text-xs text-slate-400 mb-1">Confidence</p>
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-slate-600 rounded-full h-2">
                    <div
                      className="bg-blue-500 h-full rounded-full"
                      style={{ width: `${(selectedMember.position.confidence || 0.5) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium text-slate-300">{Math.round((selectedMember.position.confidence || 0.5) * 100)}%</span>
                </div>
              </div>

              {selectedMember.position.reasoning && (
                <div className="bg-slate-700 rounded p-3">
                  <p className="text-xs text-slate-400 mb-1">Reasoning</p>
                  <p className="text-sm text-slate-200">{selectedMember.position.reasoning}</p>
                </div>
              )}

              {selectedMember.position.key_concerns && selectedMember.position.key_concerns.length > 0 && (
                <div className="bg-slate-700 rounded p-3">
                  <p className="text-xs text-slate-400 mb-2">Key Concerns</p>
                  <ul className="text-sm text-slate-300 space-y-1">
                    {selectedMember.position.key_concerns.map((concern: string, i: number) => (
                      <li key={i} className="flex gap-2">
                        <span>•</span>
                        <span>{concern}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="bg-slate-700 rounded p-3 text-xs">
                <p className="text-slate-400">Will negotiate: {selectedMember.position.willingness_to_negotiate ? '✓ Yes' : '✗ No'}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
