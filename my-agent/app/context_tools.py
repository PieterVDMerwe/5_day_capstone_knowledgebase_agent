import json
from typing import Any
from .database import get_db_connection

def _format_dsl(entity: dict[str, Any]) -> str:
    """Converts a database entity row into the Tiny Footprint Relational DSL."""
    if not entity:
        return ""
    
    # Base DSL: [Name(type) -> k:v | k:v]
    type_short = entity["entity_type"][:4].lower() # e.g. Character -> char, Location -> loca
    dsl = f"[{entity['name']}({type_short}) -> "
    
    parts = []
    if entity["summary"]:
        # Truncate summary for DSL
        summary = entity['summary']
        if len(summary) > 50:
            summary = summary[:47] + "..."
        parts.append(f"summary:{summary}")
    
    if entity.get("metadata"):
        for k, v in entity["metadata"].items():
            # Skip massive lists or long text strings in DSL to keep footprint tiny
            if isinstance(v, str) and len(v) < 30:
                parts.append(f"{k}:{v}")
            elif isinstance(v, list) and len(v) <= 3:
                # Just show count or join if very small
                parts.append(f"{k}:{','.join([str(i) for i in v])}")
                
    dsl += " | ".join(parts) + "]"
    return dsl

def get_entity_graph(entity_name: str, top_n: int = 5) -> str:
    """
    Retrieves the 1-hop neighborhood for a given entity, sorted by edge weight.
    Returns the context in the Tiny Footprint Relational DSL format to minimize LLM token usage
    and prevent Hub Explosion.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Get the core entity
    cursor.execute("SELECT * FROM entities WHERE name = ?", (entity_name,))
    core_row = cursor.fetchone()
    if not core_row:
        conn.close()
        return f"Context: Entity '{entity_name}' not found in database."
    
    core_entity = dict(core_row)
    if core_entity.get("metadata"):
        core_entity["metadata"] = json.loads(core_entity["metadata"])
        
    dsl_lines = ["Target Entity Context:", _format_dsl(core_entity)]
    
    # 2. Get top N connections (outgoing edges)
    cursor.execute("""
        SELECT e.target_name, e.weight, ent.* 
        FROM edges e 
        JOIN entities ent ON e.target_name = ent.name
        WHERE e.source_name = ?
        ORDER BY e.weight DESC 
        LIMIT ?
    """, (entity_name, top_n))
    
    outgoing = cursor.fetchall()
    if outgoing:
        dsl_lines.append(f"\nTop {len(outgoing)} Outgoing Links:")
        for row in outgoing:
            target_ent = dict(row)
            if target_ent.get("metadata"):
                target_ent["metadata"] = json.loads(target_ent["metadata"])
            dsl_lines.append("  " + _format_dsl(target_ent))
            
    # 3. Get top N incoming connections
    cursor.execute("""
        SELECT e.source_name, e.weight, ent.* 
        FROM edges e 
        JOIN entities ent ON e.source_name = ent.name
        WHERE e.target_name = ?
        ORDER BY e.weight DESC 
        LIMIT ?
    """, (entity_name, top_n))
    
    incoming = cursor.fetchall()
    if incoming:
        dsl_lines.append(f"\nTop {len(incoming)} Incoming Links:")
        for row in incoming:
            source_ent = dict(row)
            if source_ent.get("metadata"):
                source_ent["metadata"] = json.loads(source_ent["metadata"])
            dsl_lines.append("  " + _format_dsl(source_ent))
            
    conn.close()
    return "\n".join(dsl_lines)
