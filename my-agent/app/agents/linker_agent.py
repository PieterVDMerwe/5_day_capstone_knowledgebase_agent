import re
from ..database import get_all_entities

class LinkerAgent:
    """Agent responsible for inserting wikilinks deterministically."""
    def __init__(self, llm_client=None):
        pass

    def insert_links(self, draft_text: str) -> str:
        entities = get_all_entities()
        
        link_map = {}
        for e in entities:
            name = e["name"]
            # Exclude duplicate stubs or invalid names starting with [[
            if name.startswith("[["):
                continue
            link_map[name] = f"[[{name}]]"
            aliases = e.get("metadata", {}).get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_stripped = alias.strip()
                    if alias_stripped and alias_stripped.lower() != name.lower():
                        link_map[alias_stripped] = f"[[{name}|{alias_stripped}]]"
                        
        sorted_terms = sorted(link_map.keys(), key=len, reverse=True)
        
        existing_links = []
        def mask_link(match):
            existing_links.append(match.group(0))
            return f"__WIKILINK_{len(existing_links) - 1}__"
            
        masked_text = re.sub(r'\[\[.*?\]\]', mask_link, draft_text)
        
        for term in sorted_terms:
            escaped_term = re.escape(term)
            pattern = rf"\b{escaped_term}\b"
            
            def replace_term(match):
                link_val = link_map[term]
                existing_links.append(link_val)
                return f"__WIKILINK_{len(existing_links) - 1}__"
                
            masked_text = re.sub(pattern, replace_term, masked_text, flags=re.IGNORECASE)
            
        for i, link in enumerate(existing_links):
            masked_text = masked_text.replace(f"__WIKILINK_{i}__", link)
            
        return masked_text
