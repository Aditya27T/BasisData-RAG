import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";

export function layoutGraph(data, width = 780, height = 560) {
  const nodes = (data.nodes || []).map((node) => ({ ...node }));
  const links = (data.edges || []).map((edge) => ({ ...edge }));
  if (!nodes.length) return { positions: {}, edges: [] };

  const centerX = width / 2;
  const centerY = height / 2;
  const marginX = Math.min(75, width * 0.1);
  const marginY = Math.min(60, height * 0.15);
  const simulation = forceSimulation(nodes)
    .force("link", forceLink(links).id((node) => node.id).distance(115).strength(0.32))
    .force("charge", forceManyBody().strength(-310))
    .force("center", forceCenter(centerX, centerY))
    .force("collide", forceCollide(45))
    .stop();
  simulation.tick(180);
  simulation.stop();

  const positions = Object.fromEntries(nodes.map((node) => [node.id, {
    x: Math.max(marginX, Math.min(width - marginX, node.x ?? centerX)),
    y: Math.max(marginY, Math.min(height - marginY - 24, node.y ?? centerY)),
  }]));
  const edges = links.map((edge, index) => ({
    id: `${edge.source.id || edge.source}-${edge.target.id || edge.target}-${index}`,
    source: edge.source.id || edge.source,
    target: edge.target.id || edge.target,
    label: edge.label,
  }));
  return { positions, edges };
}
