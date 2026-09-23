const labels: Record<string, [string, string]> = {
  analyzing: ["Understanding your request…", "Understood your request"],
  retrieving: ["Searching knowledge base…", "Searched knowledge base"],
  using_tool: ["Checking your account…", "Checked your account"],
  generating: ["Preparing an answer…", "Prepared an answer"],
};

export function AgentStage({ name, active }: { name: string; active: boolean }) {
  const label = labels[name]?.[active ? 0 : 1] ?? name;
  return <div className={active ? "agent-stage active" : "agent-stage"}><span>{active ? "●" : "✓"}</span>{label}</div>;
}
