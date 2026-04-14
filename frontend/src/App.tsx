import { useState } from 'react';
import type { Message, LearningPathPlan } from './types';
import PLAN_RAW from './data/plan_output.json';

import Navbar from './components/Navbar';
import ChatArea from './components/ChatArea';
import InputBox from './components/InputBox';
import ContextPanel from './components/ContextPanel';
import Sidebar from './components/Sidebar';
import type { SidebarProject, SidebarSession } from './components/Sidebar';

const INITIAL_PROJECTS: SidebarProject[] = [
  {
    id: 'proj-1',
    name: 'Physics Midterm',
    sources: [
      { id: 'src-1', name: 'Blackbody_Radiation_Core.pdf', type: 'pdf' },
      { id: 'src-2', name: 'Lecture_Notes_Wien.docx', type: 'docx' }
    ],
    sessions: [
      { id: 'sess-1', name: 'Active Thread' }
    ]
  },
  {
    id: 'proj-2',
    name: 'Literature Review',
    sources: [],
    sessions: []
  }
];

const INITIAL_RECENTS = [
  { id: 'rec-1', name: 'Blackbody radiation fundamentals' },
  { id: 'rec-2', name: 'Teaching blackbody conceptually' },
  { id: 'rec-3', name: 'Hey what\'s going on' }
];

// ── Parse plan_output.json ──────────────────────────────
function parsePlanOutput(): LearningPathPlan {
  const raw = PLAN_RAW as any;
  return {
    id: 'physics-plan-1',
    studentOverview: raw.student_overview ?? '',
    finalLearningPath: raw.final_learning_path ?? [],
    sources: raw.sources.map((src: any) => ({
      sourceId: src.source_id,
      subject:  src.subject,
      expanded: true,
      units: src.units.map((u: any) => ({
        unitId:    u.unit_id,
        title:     u.title,
        completed: false,
        subtopics: (u.subtopics as string[]).map((st: string, idx: number) => ({
          id:        `${src.source_id}__${u.unit_id}__${idx}`,
          label:     st,
          completed: false,
        })),
      })),
    })),
  };
}

const INITIAL_PLAN = parsePlanOutput();

// ── Tutor intro message ─────────────────────────────────
const INTRO_MESSAGES: Message[] = [
  {
    id: 'intro-0',
    role: 'assistant',
    content: `You're preparing for your physics midterm. I'll guide you step-by-step through the key concepts, making sure you deeply understand each one before we move forward.\n\nWe'll begin with **Blackbody Radiation** — a foundational topic that underpins much of modern physics. Take your time with it; the ideas here are subtle but deeply rewarding once they click.\n\nShall we begin?`,
    timestamp: new Date(),
  },
];

// ── Helpers ─────────────────────────────────────────────
function markFirstUnitComplete(plan: LearningPathPlan): LearningPathPlan {
  let marked = false;
  return {
    ...plan,
    sources: plan.sources.map(src => ({
      ...src,
      units: src.units.map(unit => {
        if (!marked && !unit.completed) {
          marked = true;
          return { ...unit, completed: true };
        }
        return unit;
      }),
    })),
  };
}

// ── App ─────────────────────────────────────────────────
export default function App() {
  const [messages, setMessages]               = useState<Message[]>(INTRO_MESSAGES);
  const [plan, setPlan]                       = useState<LearningPathPlan>(INITIAL_PLAN);
  const [activeUnitId, setActiveUnitId]       = useState<string>(INITIAL_PLAN.sources[0].units[0].unitId);
  const [targetUnitId, setTargetUnitId]       = useState<string | null>(null);
  const [isThinking, setIsThinking]           = useState(false);
  const [showProceedPrompt, setShowProceedPrompt] = useState(false);
  const [isDarkMode, setIsDarkMode]           = useState(true);

  // Sidebar states
  const [projects, setProjects]               = useState<SidebarProject[]>(INITIAL_PROJECTS);
  const [recentChats, setRecentChats]         = useState<SidebarSession[]>(INITIAL_RECENTS);
  const [activeSessionId, setActiveSessionId] = useState<string | null>('sess-1');

  const toggleTheme = () => setIsDarkMode(prev => !prev);

  const pushMessage = (msg: Omit<Message, 'id' | 'timestamp'>) => {
    setMessages(prev => [...prev, {
      ...msg,
      id:        `msg-${Date.now()}-${Math.random()}`,
      timestamp: new Date(),
      attachedUnitId: msg.role === 'assistant' ? activeUnitId : undefined,
    }]);
  };

  const handleSend = (text: string) => {
    pushMessage({ role: 'user', content: text });
    setIsThinking(true);
    setShowProceedPrompt(false);

    setTimeout(() => {
      const lower = text.toLowerCase();
      let reply = '';

      if (lower.includes('begin') || lower.includes('start') || lower.includes('yes') || lower.includes('sure') || lower.includes('ready')) {
        reply = `Excellent. Let's start with **Blackbody Radiation**.\n\n## What is a Blackbody?\n\nA **blackbody** is an idealized object that absorbs all incident electromagnetic radiation — regardless of frequency or angle — and emits radiation purely based on its temperature.\n\nThe spectrum of emitted radiation follows a characteristic distribution described by **Planck's Law**:\n\n$$B(\\nu, T) = \\frac{2h\\nu^3}{c^2} \\cdot \\frac{1}{e^{h\\nu/k_BT} - 1}$$\n\nwhere:\n- $h$ is Planck's constant\n- $\\nu$ is frequency\n- $T$ is absolute temperature\n- $k_B$ is Boltzmann's constant\n\nThis is a subtle concept — take your time here. The key insight is that energy is quantized, not continuous.`;
      } else if (lower.includes('simpler') || lower.includes('simple')) {
        reply = `Of course. Let's strip it back.\n\nImagine you heat a metal rod. As it gets hotter:\n\n1. It first glows **red**\n2. Then **orange**\n3. Then **white-hot**\n\nThis color change happens because **hotter objects emit higher-energy, shorter-wavelength light**. A blackbody is simply our idealized model for this behavior — a perfect emitter and absorber.\n\nThe key equation just tells us *how much light* comes out at each color (frequency) for a given temperature.`;
      } else if (lower.includes('deeper') || lower.includes('more') || lower.includes('detail')) {
        reply = `Certainly. Let's go into the mathematics more carefully.\n\n## The Ultraviolet Catastrophe\n\nBefore Planck, classical physics predicted the **Rayleigh-Jeans Law**:\n\n$$B_{\\text{classical}}(\\nu, T) = \\frac{2\\nu^2 k_B T}{c^2}$$\n\nThis works at low frequencies — but predicts that radiation intensity should **increase without limit** at high frequencies. This was called the **Ultraviolet Catastrophe**: a complete failure of classical mechanics.\n\n## Planck's Resolution\n\nPlanck proposed that energy is emitted only in discrete packets called **quanta**:\n\n$$E = h\\nu$$\n\nThis single assumption — radical at the time — resolved the catastrophe and gave birth to quantum mechanics.`;
      } else if (lower.includes('quiz') || lower.includes('test')) {
        reply = `Let's check your understanding.\n\n**Question:** According to Planck's Law, what happens to the peak frequency of blackbody radiation as temperature increases?\n\nThink through it carefully. The answer connects directly to Wien's Displacement Law:\n\n$$\\lambda_{\\text{max}} T = b$$\n\nwhere $b = 2.898 \\times 10^{-3}$ m·K.`;
      } else {
        reply = `That's a thoughtful question. Let me address it carefully.\n\nIn the context of blackbody radiation and quantum mechanics, the underlying principle we always return to is **energy quantization** — the idea that nature operates in discrete steps at the microscopic scale.\n\nWould you like me to connect this to the specific aspect you're asking about, or shall we continue with the main concept?`;
      }

      pushMessage({ role: 'assistant', content: reply, thinking: undefined });
      setIsThinking(false);
      setShowProceedPrompt(true);
    }, 1600);
  };

  const handleAction = (action: 'simpler' | 'deeper', _messageId: string) => {
    handleSend(action === 'simpler' ? 'Can you explain that simpler?' : 'Can you go deeper on that?');
  };

  const handleConceptClick = (unitId: string) => {
    setTargetUnitId(unitId);
    // Reset after a short delay so clicking the same one again works
    setTimeout(() => setTargetUnitId(null), 100);
  };

  const handleProceed = (choice: boolean) => {
    setShowProceedPrompt(false);

    if (choice) {
      // Find next unit to update activeUnitId
      let nextId = activeUnitId;
      const allUnits = plan.sources.flatMap(s => s.units);
      const currIdx = allUnits.findIndex(u => u.unitId === activeUnitId);
      if (currIdx !== -1 && currIdx < allUnits.length - 1) {
        nextId = allUnits[currIdx + 1].unitId;
      }

      // Mark current unit as complete
      const updated = markFirstUnitComplete(plan);
      setPlan(updated);
      setActiveUnitId(nextId);

      pushMessage({ role: 'user', content: "Yes, let's continue to the next concept." });
      setTimeout(() => {
        pushMessage({
          role: 'assistant',
          content: `Good. I've marked that concept as complete.\n\nNext, we'll move to **Classical Blackbody Radiation and the Ultraviolet Catastrophe** — this is where the story gets philosophically interesting. Classical physics was forced to confront its own limits.\n\nReady to proceed?`,
        });
      }, 900);
    } else {
      pushMessage({ role: 'user', content: "Not yet — I have more questions." });
      setTimeout(() => {
        pushMessage({
          role: 'assistant',
          content: `Of course. Take all the time you need — that's precisely why we're here.\n\nWhat aspect would you like me to clarify?`,
        });
      }, 600);
    }
  };

  return (
    <div className={isDarkMode ? 'dark' : ''}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', background: 'var(--color-bg)', color: 'var(--color-text-1)', overflow: 'hidden' }}>
        {/* Fixed Navbar */}
        <Navbar 
          sessionTitle="Physics Midterm Prep" 
          isDarkMode={isDarkMode}
          onToggleTheme={toggleTheme}
        />

        {/* Main area */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Sidebar Area */}
          <Sidebar 
            projects={projects}
            recentChats={recentChats}
            activeSessionId={activeSessionId}
            onProjectInitiate={() => {
              const newSessId = `sess-${Date.now()}`;
              setProjects([{ 
                id: `proj-${Date.now()}`, 
                name: 'New Project', 
                sources: [], 
                sessions: [{ id: newSessId, name: 'Active Thread' }] 
              }, ...projects]);
              setActiveSessionId(newSessId);
            }}
            onQuickConsultation={() => {
              const newSessId = `rec-${Date.now()}`;
              setRecentChats([{ id: newSessId, name: 'New Session' }, ...recentChats]);
              setActiveSessionId(newSessId);
            }}
            onSessionSelect={(sid) => setActiveSessionId(sid)}
            onUploadDocument={(pid) => {
               setProjects(projects.map(p => 
                  p.id === pid ? { ...p, sources: [...p.sources, { id: `src-${Date.now()}`, name: 'New_Document.pdf', type: 'pdf' }] } : p
               ));
            }}
            onConvertRecentToProject={(sid) => {
               const chat = recentChats.find(c => c.id === sid);
               if (!chat) return;
               
               // Remove from recents
               setRecentChats(prev => prev.filter(c => c.id !== sid));
               
               // Add to projects
               setProjects([{
                 id: `proj-${Date.now()}`,
                 name: chat.name, // Use the chat name as the project folder name
                 sources: [], // Any files attached to the chat would typically go here
                 sessions: [chat]
               }, ...projects]);
               
               if (activeSessionId !== sid) {
                 setActiveSessionId(sid);
               }
            }}
            onDeleteRecent={(sid) => {
               setRecentChats(prev => prev.filter(c => c.id !== sid));
               if (activeSessionId === sid) {
                 setActiveSessionId(null);
               }
            }}
            onRenameProject={(pid, newName) => {
               setProjects(projects.map(p => 
                  p.id === pid ? { ...p, name: newName } : p
               ));
            }}
            onDeleteProject={(pid) => {
               setProjects(projects.filter(p => p.id !== pid));
               // If the active session belonged to this project, clear it
               const projectToDelete = projects.find(p => p.id === pid);
               if (projectToDelete && projectToDelete.sessions.some(s => s.id === activeSessionId)) {
                 setActiveSessionId(null);
               }
            }}
          />

          {/* Chat column */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <ChatArea
              messages={messages}
              isThinking={isThinking}
              showProceedPrompt={showProceedPrompt}
              onAction={handleAction}
              targetUnitId={targetUnitId}
            />
            <InputBox
              onSend={handleSend}
              disabled={isThinking}
              showProceedPrompt={showProceedPrompt}
              onProceed={handleProceed}
            />
          </div>

          {/* Context panel (Only render if active project is Physics Midterm) */}
          {projects.find(p => p.sessions.some(s => s.id === activeSessionId))?.id === 'proj-1' && (
            <ContextPanel 
              plan={plan} 
              onConceptClick={handleConceptClick}
            />
          )}
        </div>
      </div>
    </div>
  );
}
