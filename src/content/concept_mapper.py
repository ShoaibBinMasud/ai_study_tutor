"""
ConceptMapper — builds a shallow concept map and dependency graph from uploaded materials.

This is what makes the system a tutor, not a chatbot.
The tutor "reads" all materials once and understands the knowledge structure.

One LLM call per section → SectionConcept
All SectionConcepts → DependencyGraph
"""

import logging
from typing import Dict, List, Optional

from models.data_models import (
    DependencyGraph, ProcessedDocument, Section,
    SectionConcept, SubjectProfile,
)
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

CONCEPT_MAP_PROMPT = """You are analyzing a section of a {subject} {material_type} at the {level} level.

SECTION: {section_title}
CONTENT (first 2000 chars):
{content_sample}

Extract the knowledge structure of this section. Return ONLY a JSON object:
{{
  "concepts": ["list of 2-5 key concepts or topics INTRODUCED in this section"],
  "prerequisites": ["concepts from EARLIER sections the student needs to understand this"],
  "key_equations": ["equation numbers or names, e.g. '2-5', 'F=ma', 'Pythagorean theorem'"],
  "key_examples": ["example numbers, e.g. 'Example 1-7', 'Example 3.2'"],
  "key_figures": ["figure numbers, e.g. 'Figure 2-3', 'Figure 4.1'"],
  "key_theorems": ["theorem or definition names for math subjects"],
  "key_reactions": ["reaction names or numbers for chemistry subjects"],
  "difficulty": "low | medium | high",
  "estimated_teaching_time": "5 min | 10 min | 15 min | 20 min | 30 min"
}}

Focus on what is INTRODUCED here. Prerequisites are things taught in EARLIER sections.
Be concise — 2-5 items per list maximum."""


class ConceptMapper:
    """
    Builds a shallow concept map across all sections of all loaded documents.

    Runs once on file upload (~1 LLM call per section).
    The resulting SectionConcept dict and DependencyGraph are stored in SessionState.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def map_document(
        self,
        doc: ProcessedDocument,
        subject_profile: Optional[SubjectProfile] = None,
        existing_map: Optional[Dict[str, SectionConcept]] = None,
        sections_subset: Optional[List[Section]] = None,
    ) -> Dict[str, SectionConcept]:
        """
        Map sections in a document.

        Args:
            doc: The processed document to analyze
            subject_profile: Detected subject info to guide mapping
            existing_map: Existing concept map to extend (for mid-session additions)
            sections_subset: If provided, only map these specific sections (for lazy mapping)

        Returns:
            Dict of section_id → SectionConcept (new entries only)
        """
        new_concepts: Dict[str, SectionConcept] = {}
        sp = subject_profile

        subject = sp.subject if sp else "STEM"
        level = sp.level if sp else "intermediate"
        material_type = sp.material_type if sp else "textbook"

        # Use provided subset, or filter doc sections by content length
        if sections_subset is not None:
            sections_to_map = [s for s in sections_subset if len(s.content.strip()) > 100]
        else:
            sections_to_map = [
                s for s in doc.sections
                if len(s.content.strip()) > 100
            ]

        if sections_to_map:
            logger.info(f"Mapping {len(sections_to_map)} section(s) from '{doc.label}'...")

        for section in sections_to_map:
            try:
                concept = self._map_section(section, subject, level, material_type)
                new_concepts[section.section_id] = concept
            except Exception as e:
                logger.warning(f"Failed to map section {section.section_id}: {e}")
                # Create a minimal fallback concept entry
                new_concepts[section.section_id] = SectionConcept(
                    section_id=section.section_id,
                    source_file=doc.file_path,
                    title=section.title,
                    page_range=(section.page_start, section.page_end),
                    difficulty="medium",
                    estimated_teaching_time="15 min",
                )

        logger.info(f"Mapped {len(new_concepts)} sections from '{doc.label}'")
        return new_concepts

    def _map_section(
        self, section: Section, subject: str, level: str, material_type: str
    ) -> SectionConcept:
        """Run one LLM call to extract concept info for a single section."""
        content_sample = section.content[:2000].strip()

        prompt = CONCEPT_MAP_PROMPT.format(
            subject=subject,
            material_type=material_type,
            level=level,
            section_title=section.title,
            content_sample=content_sample,
        )

        result = self.llm.get_json_completion(
            [{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2,
        )

        return SectionConcept(
            section_id=section.section_id,
            source_file=section.source_file,
            title=section.title,
            page_range=(section.page_start, section.page_end),
            concepts=result.get("concepts", []),
            prerequisites=result.get("prerequisites", []),
            key_equations=result.get("key_equations", []),
            key_examples=result.get("key_examples", []),
            key_figures=result.get("key_figures", []),
            key_theorems=result.get("key_theorems", []),
            key_reactions=result.get("key_reactions", []),
            difficulty=result.get("difficulty", "medium"),
            estimated_teaching_time=result.get("estimated_teaching_time", "15 min"),
        )

    def build_dependency_graph(
        self, concept_map: Dict[str, SectionConcept]
    ) -> DependencyGraph:
        """
        Build a DependencyGraph from the concept map.

        Edges are drawn between sections based on their prerequisite lists.
        A prerequisite concept is matched to the section that introduces it.
        """
        graph = DependencyGraph(nodes=concept_map)

        # Build a lookup: concept_name → section_id (which section introduces it)
        concept_to_section: Dict[str, str] = {}
        for section_id, sc in concept_map.items():
            for concept in sc.concepts:
                concept_to_section[concept.lower()] = section_id

        # Add dependency edges
        for section_id, sc in concept_map.items():
            for prereq in sc.prerequisites:
                prereq_lower = prereq.lower()
                # Find which section introduces this prerequisite
                introducing_section = concept_to_section.get(prereq_lower)
                if introducing_section and introducing_section != section_id:
                    edge = (introducing_section, section_id)
                    if edge not in graph.edges:
                        graph.edges.append(edge)

        logger.info(
            f"Built dependency graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )
        return graph

    def get_teaching_order(
        self,
        graph: DependencyGraph,
        section_ids: List[str],
    ) -> List[str]:
        """Return section_ids sorted by dependency order (prerequisites first)."""
        return graph.get_teaching_order(section_ids)

    def find_prerequisite_gaps(
        self,
        graph: DependencyGraph,
        known_section_ids: List[str],
        target_section_ids: List[str],
    ) -> List[str]:
        """Return section IDs that are prerequisite gaps for the target sections."""
        known_set = set(known_section_ids)
        gaps = []
        for target in target_section_ids:
            for prereq_section, dep_section in graph.edges:
                if dep_section == target and prereq_section not in known_set:
                    gaps.append(prereq_section)
        return list(set(gaps))
