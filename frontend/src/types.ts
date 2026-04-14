// ─── Projects & Documents ───────────────────────────────
export interface Document {
  id: string;
  name: string;
  type: 'pdf' | 'pptx' | 'docx' | 'txt' | 'url';
  size?: string;
  uploadedAt: Date;
}

export interface Project {
  id: string;
  name: string;
  documents: Document[];
  updatedAt: Date;
}

// ─── Chat ─────────────────────────────────────────────
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  thinking?: string; // agent step label
  attachedUnitId?: string; // Links message to a concept in the timeline
}

// ─── Teaching Plan ────────────────────────────────────
export interface TeachingTopic {
  id: string;
  title: string;
  status: 'pending' | 'in-progress' | 'mastered';
  score?: number; // 0-100
}

export interface TeachingPlan {
  id: string;
  title: string;
  topics: TeachingTopic[];
  startedAt: Date;
}

// ─── Learning Path (plan_output.json) ─────────────────
export interface LearningPathSubtopic {
  id: string;
  label: string;
  completed: boolean;
}

export interface LearningPathUnit {
  unitId: string;
  title: string;
  subtopics: LearningPathSubtopic[];
  completed: boolean; // true when ALL subtopics checked
}

export interface LearningPathSource {
  sourceId: string;
  subject: string;
  units: LearningPathUnit[];
  expanded: boolean;
}

export interface LearningPathPlan {
  id: string;
  studentOverview: string;
  sources: LearningPathSource[];
  finalLearningPath: string[]; // ordered unit_ids
}

// ─── Canvas Modes & Practice ──────────────────────────
export interface Flashcard {
  id: string;
  front: string;
  back: string;
  concept: string;
}

export interface QuizQuestion {
  id: string;
  question: string;
  options: string[];
  correctAnswer: number;
  explanation: string;
}

export type CanvasMode = 
  | { type: 'syllabus'; plan: TeachingPlan | LearningPathPlan }
  | { type: 'document'; sectionTitle: string; content: string }
  | { type: 'flashcards'; cards: Flashcard[] }
  | { type: 'quiz'; questions: QuizQuestion[] }
  | { type: 'scratchpad' }
  | { type: 'welcome' };
