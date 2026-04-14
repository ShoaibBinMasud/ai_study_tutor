import type { Concept, Folder, Session, Flashcard, QuizQuestion, Message } from '../types';

// ─── Mock Concepts / Mastery Tree ───────────────────────────────────
export const mockConcepts: Concept[] = [
  { id: 'c1', label: 'Wave Properties of Light',     mastery: 5 },
  { id: 'c2', label: 'Basic Optics',                  mastery: 4 },
  { id: 'c3', label: 'Michelson Interferometer',       mastery: 3, parentId: 'c2' },
  { id: 'c4', label: 'Michelson-Morley Experiment',    mastery: 2, parentId: 'c3' },
  { id: 'c5', label: "Einstein's Postulates",          mastery: 0, parentId: 'c4' },
  { id: 'c6', label: 'Time Dilation',                  mastery: 0, parentId: 'c5' },
  { id: 'c7', label: 'Length Contraction',             mastery: 0, parentId: 'c5' },
  { id: 'c8', label: 'Relativistic Mass & Energy',     mastery: 0, parentId: 'c5' },
];

// ─── Mock Library ────────────────────────────────────────────────────
export const mockFolders: Folder[] = [
  {
    id: 'f1',
    name: 'Physics 301',
    documents: [
      { id: 'd1', name: 'physics_book_ch1.pdf', type: 'pdf', size: '2.4 MB', folder: 'f1', active: true },
      { id: 'd2', name: 'lecture_slides_week2.pptx', type: 'pptx', size: '8.1 MB', folder: 'f1', active: true },
      { id: 'd3', name: 'problem_set_3.pdf', type: 'pdf', size: '450 KB', folder: 'f1', active: false },
    ],
  },
  {
    id: 'f2',
    name: 'Calculus II',
    documents: [
      { id: 'd4', name: 'integration_notes.pdf', type: 'pdf', size: '1.2 MB', folder: 'f2', active: false },
    ],
  },
];

// ─── Mock Sessions ───────────────────────────────────────────────────
export const mockSessions: Session[] = [
  { id: 's1', title: "Einstein's Postulates Deep Dive", subject: 'Physics 301', createdAt: new Date('2025-04-03'), lastActive: new Date('2025-04-03'), messageCount: 14 },
  { id: 's2', title: 'Wave Properties Review', subject: 'Physics 301', createdAt: new Date('2025-04-02'), lastActive: new Date('2025-04-02'), messageCount: 8 },
  { id: 's3', title: 'Michelson-Morley Setup', subject: 'Physics 301', createdAt: new Date('2025-04-01'), lastActive: new Date('2025-04-01'), messageCount: 22 },
];

// ─── Mock Flashcards ─────────────────────────────────────────────────
export const mockFlashcards: Flashcard[] = [
  {
    id: 'fc1',
    front: "What is the first postulate of Special Relativity?",
    back: "The laws of physics are the same in **all inertial reference frames**. No experiment can distinguish between uniform motion and rest.\n\nFormally: The laws of nature are covariant with respect to Lorentz transformations.",
    concept: "Einstein's Postulates",
  },
  {
    id: 'fc2',
    front: "State the second postulate of Special Relativity.",
    back: "The speed of light in a vacuum is **constant** ($c \\approx 3 \\times 10^8$ m/s) for all observers, regardless of the motion of the light source or observer.",
    concept: "Einstein's Postulates",
  },
  {
    id: 'fc3',
    front: "What was the Michelson-Morley experiment designed to detect?",
    back: "It was designed to detect the **luminiferous aether** — a hypothetical medium through which light was thought to propagate. The experiment found no evidence of the aether, with a null result that formed a cornerstone of Special Relativity.",
    concept: "Michelson-Morley Experiment",
  },
  {
    id: 'fc4',
    front: "Write the time dilation formula.",
    back: "$$\\Delta t' = \\gamma \\Delta t = \\frac{\\Delta t}{\\sqrt{1 - \\frac{v^2}{c^2}}}$$\n\nWhere $\\Delta t$ is the proper time (measured in the rest frame) and $\\gamma$ is the Lorentz factor.",
    concept: "Time Dilation",
  },
];

// ─── Mock Quiz ───────────────────────────────────────────────────────
export const mockQuizQuestions: QuizQuestion[] = [
  {
    id: 'q1',
    question: "According to Einstein's second postulate, what happens to the speed of light if the light source is moving toward you at $0.5c$?",
    options: [
      "A) It increases to $1.5c$",
      "B) It stays constant at $c$",
      "C) It decreases to $0.5c$",
      "D) It depends on the medium",
    ],
    correctIndex: 1,
    explanation: "Einstein's second postulate states that $c$ is constant for **all** observers in all inertial frames, regardless of the source's motion. This was the revolutionary departure from Newtonian mechanics.",
    concept: "Einstein's Postulates",
  },
  {
    id: 'q2',
    question: "The Lorentz factor $\\gamma$ equals 1 when:",
    options: [
      "A) $v = c$",
      "B) $v = 0$",
      "C) $v = 0.5c$",
      "D) $v \\to \\infty$",
    ],
    correctIndex: 1,
    explanation: "When $v = 0$, the term $v^2/c^2 = 0$, giving $\\gamma = 1/\\sqrt{1-0} = 1$. At rest, there is no time dilation or length contraction — everything is in its rest frame.",
    concept: "Time Dilation",
  },
  {
    id: 'q3',
    question: "The Michelson-Morley experiment used interference of light beams split perpendicular to each other. What was the expected result if aether existed?",
    options: [
      "A) A brighter fringe pattern",
      "B) A detectable phase shift due to different travel times",
      "C) A complete cancellation of both beams",
      "D) No change at all",
    ],
    correctIndex: 1,
    explanation: "If aether existed, the beam traveling against the aether current would take slightly longer than the beam perpendicular to it, producing a measurable fringe shift. The **null result** showed no such shift.",
    concept: "Michelson-Morley Experiment",
  },
];

// ─── Mock Document Content (Rich with LaTeX and prose) ──────────────
export const mockDocumentContent = `
## Section 1-2: Einstein's Postulates of Special Relativity

By the turn of the 20th century, physicists had accumulated a troubling paradox. Maxwell's equations predicted electromagnetic waves propagating at a fixed speed $c$. Yet Newtonian mechanics demanded that speeds add — a bullet fired from a moving train has a ground-speed equal to the sum. So, what was the speed of light *relative to*?

### The Historic Context

The Michelson-Morley experiment of 1887 had already shown that no aether wind could be detected. Lorentz and Fitzgerald proposed ad-hoc length contraction to explain the null result. Einstein took a bolder step: **he rejected the aether entirely**.

> "The introduction of a 'light ether' will prove superfluous, inasmuch as the view here to be developed will not require an 'absolutely stationary space'." — Einstein, 1905

### The Two Postulates

Einstein's 1905 paper, *"On the Electrodynamics of Moving Bodies"*, was built on only two postulates:

**Postulate I — The Principle of Relativity:**
The laws of physics take the same form in every inertial (non-accelerating) reference frame.

$$\\mathcal{L}_{\\text{physics}} = \\text{covariant w.r.t. Lorentz transforms}$$

**Postulate II — The Invariance of the Speed of Light:**
The speed of light in a vacuum is $c \\approx 2.998 \\times 10^8$ m/s for all inertial observers, independent of the motion of the source or observer.

$$c = \\frac{1}{\\sqrt{\\mu_0 \\varepsilon_0}}$$

### Immediate Consequences

From these two simple postulates, Einstein derived an entirely new mechanics:

| Classical Mechanics | Special Relativity |
|---|---|
| Time is absolute | Time is relative (dilation) |
| Length is fixed | Length contracts along motion |
| Mass is constant | $m = \\gamma m_0$ |
| $K = \\frac{1}{2}mv^2$ | $E = \\gamma m_0 c^2$ |

The Lorentz factor $\\gamma$ appears throughout:

$$\\gamma = \\frac{1}{\\sqrt{1 - \\frac{v^2}{c^2}}}$$

For everyday speeds, $v \\ll c$ and $\\gamma \\approx 1$ — Newtonian mechanics is a superb approximation. Only near the cosmic speed limit does the relativistic correction become significant.
`;

// ─── Mock Initial Messages ───────────────────────────────────────────
export const mockInitialMessages: Message[] = [
  {
    id: 'm0',
    role: 'assistant',
    content: "Hello! I've loaded **Physics 301 — Special Relativity**. I've analyzed your materials and mapped 8 key concepts.\n\nYou've mastered Wave Properties and Basic Optics. Today, I recommend we tackle **Section 1-2: Einstein's Postulates** — it's the gateway to everything else in this module.\n\nWhere would you like to start?",
    timestamp: new Date(),
  },
];
