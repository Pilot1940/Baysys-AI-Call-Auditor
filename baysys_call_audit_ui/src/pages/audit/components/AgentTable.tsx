/** Agent table component — scaffold only. */

interface AgentRow {
  agent_id: string;
  agent_name: string;
  total_calls: number;
  avg_score: number | null;
  critical_flags: number;
}

interface AgentTableProps {
  agents: AgentRow[];
}

export default function AgentTable({ agents }: AgentTableProps) {
  return (
    <table className="min-w-full divide-y divide-gray-200">
      <thead className="bg-gray-50">
        <tr>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Agent</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Calls</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Avg Score</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Critical Flags</th>
        </tr>
      </thead>
      <tbody className="bg-white divide-y divide-gray-200">
        {agents.map((agent) => (
          <tr key={agent.agent_id}>
            <td className="px-4 py-2 text-sm text-gray-900">{agent.agent_name}</td>
            <td className="px-4 py-2 text-sm text-gray-600">{agent.total_calls}</td>
            <td className="px-4 py-2 text-sm text-gray-600">
              {agent.avg_score != null ? `${agent.avg_score}%` : "—"}
            </td>
            <td className="px-4 py-2 text-sm text-gray-600">{agent.critical_flags}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
