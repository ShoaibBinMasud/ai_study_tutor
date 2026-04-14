"""
Data models for the Adaptive AI STEM Tutor.

All core dataclasses used across the system:
- Content Intelligence: SubjectProfile, ProcessedDocument, SectionConcept, DependencyGraph
- Session Planning: TeachingPlan, TeachingPhase
- Teaching Execution: TeachingUnit, ContentChunk
- Merit & Assessment: MeritEntry, QuizResult, QuizQuestion
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum


# ─── Subject Detection ────────────────────────────────────────────────────────

@dataclass
class SubjectProfile:
    """Auto-detected profile of uploaded material."""
    subject: str              # "Physics", "Organic Chemistry", "Linear Algebra", etc.
    sub_field: str            # "Classical Mechanics", "Thermodynamics", etc.
    level: str                # "introductory", "intermediate", "advanced", "graduate"
    material_type: str        # "textbook", "lecture_notes", "problem_set", "formula_sheet", "exam_prep"
    teaching_style_hints: str # "equation-heavy", "proof-based", "conceptual", "reaction-based", "code-focused"


# ─── Document Scanning ───────────────────────────────────────────────────────

@dataclass
class DocumentScanEntry:
    """Structured metadata for a single scanned document."""
    file_name: str
    file_path: str
    file_type: str                # "pdf", "pptx", "docx", "image", "text"
    file_size_kb: float
    total_pages: int              # slide count for pptx, 1 for images
    is_scanned: bool = False
    has_toc: bool = False
    toc_entry_count: int = 0


@dataclass
class DocumentScanReport:
    """Report from scanning a batch of documents."""
    entries: List[DocumentScanEntry] = field(default_factory=list)
    collection_summary: str = ""


# ─── Content Intelligence ─────────────────────────────────────────────────────

@dataclass
class TOCEntry:
    """Normalized table of contents entry (works across all file types)."""
    title: str
    level: int                # 1=chapter, 2=section, 3=subsection
    page_or_slide: int        # Page number (PDF/DOCX) or slide number (PPTX)
    source_file: str          # Which uploaded file this came from
    section_id: str = ""      # Normalized ID like "1-2", "3.4", etc.


@dataclass
class Section:
    """A section of extracted content from any document type."""
    section_id: str
    title: str
    content: str              # Full text content of the section
    page_start: int
    page_end: int
    source_file: str
    subsections: List[str] = field(default_factory=list)  # Subsection titles


@dataclass
class ProcessedDocument:
    """Unified format for any uploaded file after processing."""
    file_path: str
    file_type: str            # "pdf_textbook", "pdf_slides", "image", "pptx", "docx", "text"
    label: str                # User-friendly display name
    toc: List[TOCEntry] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    subject_profile: Optional[SubjectProfile] = None
    added_at: datetime = field(default_factory=datetime.now)


@dataclass
class SectionConcept:
    """Shallow concept map for a single section (from ConceptMapper)."""
    section_id: str
    source_file: str
    title: str
    page_range: Tuple[int, int]
    concepts: List[str] = field(default_factory=list)          # Key concepts introduced
    prerequisites: List[str] = field(default_factory=list)     # Concepts needed from earlier
    key_equations: List[str] = field(default_factory=list)     # Equation numbers/labels
    key_examples: List[str] = field(default_factory=list)      # Example numbers
    key_figures: List[str] = field(default_factory=list)       # Figure numbers
    key_theorems: List[str] = field(default_factory=list)      # Theorem/definition names (math)
    key_reactions: List[str] = field(default_factory=list)     # Reaction names (chemistry)
    difficulty: str = "medium"                                  # "low", "medium", "high"
    estimated_teaching_time: str = "15 min"


@dataclass
class DependencyGraph:
    """Graph of concept dependencies across all uploaded materials."""
    nodes: Dict[str, SectionConcept] = field(default_factory=dict)  # section_id → SectionConcept
    edges: List[Tuple[str, str]] = field(default_factory=list)      # (prerequisite_concept, dependent_concept)

    def get_prerequisites(self, concept: str) -> List[str]:
        """Get all prerequisites for a concept."""
        return [pre for pre, dep in self.edges if dep == concept]

    def get_dependents(self, concept: str) -> List[str]:
        """Get all concepts that depend on this one."""
        return [dep for pre, dep in self.edges if pre == concept]

    def get_teaching_order(self, target_concepts: List[str]) -> List[str]:
        """Topological sort of target concepts respecting dependencies."""
        # Build adjacency for just the target concepts and their prereqs
        relevant = set(target_concepts)
        for concept in target_concepts:
            relevant.update(self.get_prerequisites(concept))

        # Kahn's algorithm for topological sort
        in_degree: Dict[str, int] = {c: 0 for c in relevant}
        for pre, dep in self.edges:
            if pre in relevant and dep in relevant:
                in_degree[dep] = in_degree.get(dep, 0) + 1

        queue = [c for c in relevant if in_degree.get(c, 0) == 0]
        result = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for dep in self.get_dependents(node):
                if dep in relevant:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)

        return result

    def find_gaps(self, known_concepts: List[str], target_concepts: List[str]) -> List[str]:
        """Find prerequisite concepts the student is missing."""
        known_set = set(known_concepts)
        needed = set()
        for concept in target_concepts:
            for prereq in self.get_prerequisites(concept):
                if prereq not in known_set:
                    needed.add(prereq)
        return list(needed)


# ─── Session Planning ─────────────────────────────────────────────────────────

class RequestScope(Enum):
    """Scope of a student's teaching request."""
    SINGLE_SECTION = "single_section"
    CHAPTER = "chapter"
    MULTI_CHAPTER = "multi_chapter"
    EXAM_PREP = "exam_prep"
    TARGETED_CONCEPT = "targeted_concept"
    INFO = "info"
    CONTINUE = "continue"


@dataclass
class TeachingPhase:
    """A phase within a teaching plan (e.g., 'Foundations', 'Core Theory')."""
    name: str
    sections: List[str] = field(default_factory=list)   # Section IDs to cover
    estimated_time: str = ""
    priority: str = "important"  # "critical", "important", "if_time_allows"
    completed: bool = False


@dataclass
class TeachingPlan:
    """Complete teaching plan created by the Session Planner."""
    scope: RequestScope
    phases: List[TeachingPhase] = field(default_factory=list)
    skip_list: List[str] = field(default_factory=list)           # Concepts to skip
    priority_concepts: List[str] = field(default_factory=list)   # High-value concepts
    diagnostic_results: Optional[Dict[str, float]] = None        # concept → mastery %
    estimated_total_time: str = ""
    current_phase_index: int = 0
    current_section_index: int = 0

    @property
    def current_phase(self) -> Optional[TeachingPhase]:
        if 0 <= self.current_phase_index < len(self.phases):
            return self.phases[self.current_phase_index]
        return None

    def advance_section(self) -> bool:
        """Move to next section. Returns True if there are more sections/phases."""
        phase = self.current_phase
        if not phase:
            return False

        self.current_section_index += 1
        if self.current_section_index >= len(phase.sections):
            # Phase complete
            phase.completed = True
            self.current_phase_index += 1
            self.current_section_index = 0
            return self.current_phase_index < len(self.phases)
        return True

    @property
    def is_complete(self) -> bool:
        return self.current_phase_index >= len(self.phases)

    def get_current_section_id(self) -> Optional[str]:
        phase = self.current_phase
        if phase and self.current_section_index < len(phase.sections):
            return phase.sections[self.current_section_index]
        return None


# ─── Teaching Execution ───────────────────────────────────────────────────────

@dataclass
class TeachingUnit:
    """A single teachable chunk within a section."""
    unit_id: str
    title: str
    content: str              # The actual text to teach (400-1200 words)
    page_range: Tuple[int, int]
    content_type: str         # "concept", "equation_group", "example", "derivation", "theorem", "reaction"
    source_file: str = ""
    equations: List[str] = field(default_factory=list)
    figures: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    difficulty: str = "medium"


# ─── Merit & Assessment ───────────────────────────────────────────────────────

@dataclass
class MeritEntry:
    """A single merit assessment record."""
    timestamp: datetime
    unit_id: str              # Which teaching unit was being assessed
    score: float              # 1-10
    reasoning: str
    adjustment: str           # "slower", "normal", "faster"


class AdaptationLevel(Enum):
    """Pacing adaptation based on merit score."""
    SLOWER = "slower"    # merit < 5: ~400 word chunks, more examples
    NORMAL = "normal"    # merit 5-7: ~800 word chunks, standard
    FASTER = "faster"    # merit > 7: ~1200 word chunks, challenge problems

    @classmethod
    def from_merit(cls, merit_score: float) -> "AdaptationLevel":
        if merit_score < 5.0:
            return cls.SLOWER
        elif merit_score > 7.0:
            return cls.FASTER
        return cls.NORMAL

    @property
    def target_chunk_words(self) -> int:
        return {
            AdaptationLevel.SLOWER: 400,
            AdaptationLevel.NORMAL: 800,
            AdaptationLevel.FASTER: 1200,
        }[self]


@dataclass
class QuizQuestion:
    """A single quiz question."""
    question_id: str
    question_text: str
    question_type: str        # "easy_mc", "medium_answer", "hard_problem", "worked_example"
    correct_answer: str
    options: List[str] = field(default_factory=list)  # For MC questions
    hint: str = ""
    source_example: str = ""  # e.g., "Example 4.3 (page 52)" for worked examples
    student_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    feedback: str = ""


@dataclass
class QuizResult:
    """Results of a section completion quiz."""
    section_id: str
    timestamp: datetime
    questions: List[QuizQuestion] = field(default_factory=list)
    score_percentage: float = 0.0
    weak_areas: List[str] = field(default_factory=list)  # Concepts student struggled with

    @property
    def questions_correct(self) -> int:
        return sum(1 for q in self.questions if q.is_correct)

    @property
    def questions_total(self) -> int:
        return len(self.questions)


# ─── State Machine ────────────────────────────────────────────────────────────

class TutorState(Enum):
    """States in the tutor's state machine."""
    IDLE = "idle"
    FILE_UPLOAD = "file_upload"
    CONCEPT_MAPPING = "concept_mapping"
    INTENT_CLASSIFICATION = "intent_classification"
    PLANNING = "planning"
    DIAGNOSTIC = "diagnostic"
    PLAN_REVIEW = "plan_review"
    DEEP_ANALYZE = "deep_analyze"
    TEACHING = "teaching"
    COMPREHENSION_CHECK = "comprehension_check"
    RETEACH = "reteach"
    MERIT_UPDATE = "merit_update"
    SECTION_QUIZ = "section_quiz"
    QUIZ_EVAL = "quiz_eval"
    PHASE_CHECKPOINT = "phase_checkpoint"
    PLAN_COMPLETE = "plan_complete"
    SHOW_INFO = "show_info"
    RESUME = "resume"
    DETOUR = "detour"


# ─── Session State (In-Memory) ───────────────────────────────────────────────

@dataclass
class SessionState:
    """In-memory session state for the current tutoring session."""
    # Content Intelligence
    documents: List[ProcessedDocument] = field(default_factory=list)
    subject_profile: Optional[SubjectProfile] = None
    concept_map: Dict[str, SectionConcept] = field(default_factory=dict)
    dependency_graph: DependencyGraph = field(default_factory=DependencyGraph)

    # Current state
    current_state: TutorState = TutorState.IDLE
    previous_state: Optional[TutorState] = None  # For DETOUR returns

    # Teaching plan
    current_plan: Optional[TeachingPlan] = None
    current_units: List[TeachingUnit] = field(default_factory=list)
    current_unit_index: int = 0

    # Merit
    merit_score: float = 5.0  # Start at neutral
    merit_history: List[MeritEntry] = field(default_factory=list)
    adaptation_level: AdaptationLevel = AdaptationLevel.NORMAL

    # Conversation
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

    # Assessment
    quiz_results: List[QuizResult] = field(default_factory=list)

    # Tracking
    sections_completed: List[str] = field(default_factory=list)
    concepts_mastered: List[str] = field(default_factory=list)

    # Prerequisite check tracking
    waiting_for_prerequisite_response: bool = False
    pending_section_id: Optional[str] = None

    def update_merit(self, new_assessment: float):
        """Update merit score using EWMA: new = 0.7 * current + 0.3 * latest."""
        self.merit_score = (0.7 * self.merit_score) + (0.3 * new_assessment)
        self.adaptation_level = AdaptationLevel.from_merit(self.merit_score)

    @property
    def current_unit(self) -> Optional[TeachingUnit]:
        if 0 <= self.current_unit_index < len(self.current_units):
            return self.current_units[self.current_unit_index]
        return None

    def has_more_units(self) -> bool:
        return self.current_unit_index < len(self.current_units) - 1

    def advance_unit(self):
        self.current_unit_index += 1
