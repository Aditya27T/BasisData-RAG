import { layoutGraph } from "./graph-layout.js";

export function graphFromAnswer(entities = [], relationships = []) {
  const nodes = new Map();
  const aliases = new Map();

  for (const entity of entities) {
    const label = String(entity.entity_name || entity.name || "").trim();
    if (!label) continue;
    const id = String(entity.entity_id || entity.id || label);
    const node = {
      id,
      label,
      type: String(entity.entity_type || entity.type || "Entitas"),
      description: String(entity.description || ""),
    };
    nodes.set(id, node);
    aliases.set(label, id);
    aliases.set(id, id);
  }

  const edges = [];
  const seen = new Set();
  for (const relationship of relationships) {
    const sourceValue = relationship.src_id || relationship.source || relationship.entity1;
    const targetValue = relationship.tgt_id || relationship.target || relationship.entity2;
    if (!sourceValue || !targetValue) continue;
    const sourceName = String(sourceValue);
    const targetName = String(targetValue);
    const source = aliases.get(sourceName) || sourceName;
    const target = aliases.get(targetName) || targetName;
    for (const [id, label] of [[source, sourceName], [target, targetName]]) {
      if (!nodes.has(id)) nodes.set(id, { id, label, type: "Entitas", description: "" });
    }
    const label = String(relationship.keywords || relationship.relation_type || "terkait");
    const key = `${[source, target].sort().join("\u0000")}\u0000${label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({
      source,
      target,
      label,
      description: String(relationship.description || ""),
    });
  }

  const resultNodes = [...nodes.values()].slice(0, 24);
  const nodeIds = new Set(resultNodes.map((node) => node.id));
  const resultEdges = edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)).slice(0, 36);
  const layout = layoutGraph({ nodes: resultNodes, edges: resultEdges }, 720, 360);
  return { nodes: resultNodes, edges: layout.edges, positions: layout.positions };
}
