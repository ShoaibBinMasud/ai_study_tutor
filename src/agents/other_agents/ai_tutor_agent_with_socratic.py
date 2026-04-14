"""
AI Tutor Agent with Integrated Socratic Subagent

This version integrates SimpleSocraticTutor as a specialized subagent for teaching dialogue.

Architecture:
- Main Agent: Orchestration, navigation, planning, problems
- Socratic Subagent: Actual teaching dialogue (short, question-driven)

When teach_part is called:
1. Agent extracts part content
2. Agent initializes Socratic subagent with that content
3. Subagent handles the teaching dialogue
4. When part is done, control returns to agent
"""

import json
import logging
import sys
import os
import re
from typing import Dict, List, Any, Optional
import requests
from requests.auth import HTTPBasicAuth

# Import existing tools
from tools.pdf_content_navigator import get_pdf_content_range
from tools.pdf_extraction_tool import extract_pdf_pages

# Import Socratic subagent
from .simple_socratic_tutor import SimpleSocraticTutor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AITutorAgentWithSocratic:
    """
    AI Tutor Agent with Socratic Subagent integration.
    
    The Socratic subagent handles actual teaching dialogue while the main
    agent handles orchestration, navigation, and problem management.
    """
    
    def __init__(
        self,
        api_key: str,
        pdf_path: str,
        model: Optional[str] = "gpt-4o-mini"
    ):
        """Initialize the AI Tutor Agent with Socratic subagent."""
        self.api_key = api_key
        self.pdf_path = pdf_path
        self.model = model
        self.api_url = "https://api.openai.com/v1/chat/completions"
        
        # Initialize Socratic subagent
        self.socratic_tutor = SimpleSocraticTutor(api_key, model)
        self.socratic_mode = False  # Track if we're in Socratic teaching mode
        
        # Conversation state
        self.conversation_history = []
        self.context = {
            'current_section': None,
            'section_content': None,
            'toc': None,
            'learning_history': [],
            'teaching_parts': [],
            'current_part': 0,
            'section_page_range': None,
            'current_part_content': None  # Content for current part being taught
        }
        
        # Initialize conversation with system prompt
        self._initialize_agent()
        
        logger.info(f"AI Tutor Agent with Socratic Subagent initialized")
        logger.info(f"  PDF: {pdf_path}")
        logger.info(f"  API: {self.api_url}")
    
    def _initialize_agent(self):
        """Initialize the agent with system prompt and available tools."""
        self.conversation_history = [
            {
                "role": "system",
                "content": (
                    f"You are an AUTONOMOUS AI TUTOR AGENT for teaching physics.\n"
                    f"\n"
                    f"PDF: {self.pdf_path}\n"
                    f"\n"
                    f"YOUR ARCHITECTURE:\n"
                    f"- You are the ORCHESTRATOR - you manage the big picture\n"
                    f"- You have a SOCRATIC SUBAGENT for actual teaching dialogue\n"
                    f"- You use tools to navigate, plan, extract problems\n"
                    f"- When teaching, you delegate to the Socratic subagent\n"
                    f"\n"
                    f"REQUEST TYPES (READ CAREFULLY - DON'T CONFUSE THEM):\n"
                    f"\n"
                    f"1. INFO REQUEST - Simple lookups from TOC:\n"
                    f"   Examples: 'what's the title of section X', 'what pages is section X', 'what sections in chapter X'\n"
                    f"   Action: Use get_book_overview to look up info from TOC\n"
                    f"   Response: Answer directly - DO NOT load content or teach\n"
                    f"   Example answer: 'Section 1-2: Einstein's Postulates (pages 29-34)'\n"
                    f"\n"
                    f"2. SUMMARY REQUEST - Brief content overview:\n"
                    f"   Examples: 'summarize section X', 'what's in section X', 'overview of section X'\n"
                    f"   Action: get_section_content, then provide brief summary\n"
                    f"   Response: Summarize key topics, equations, examples covered\n"
                    f"   DO NOT call break_section_into_parts or teach_part\n"
                    f"\n"
                    f"3. TEACHING REQUEST - Full interactive teaching:\n"
                    f"   Examples: 'teach me section X', 'help me understand section X', 'learn section X'\n"
                    f"   Action: get_section_content, break_section_into_parts, teach_part(1) - ALL AT ONCE\n"
                    f"   Response: Start teaching immediately, no confirmation needed\n"
                    f"   The Socratic subagent will begin the dialogue\n"
                    f"\n"
                    f"TEACHING FLOW:\n"
                    f"1. Student says 'teach me section X':\n"
                    f"   - Call get_section_content to load content\n"
                    f"   - Call break_section_into_parts to create plan\n"
                    f"   - Immediately call teach_part(1) to start teaching\n"
                    f"   - NO confirmation needed - just start!\n"
                    f"\n"
                    f"2. teach_part(1) activates Socratic subagent:\n"
                    f"   - SOCRATIC MODE ON\n"
                    f"   - Subagent begins question-driven dialogue\n"
                    f"\n"
                    f"3. SOCRATIC MODE: All student messages go to subagent until part is complete\n"
                    f"4. Subagent teaches with short, question-driven dialogue\n"
                    f"5. When part is done, subagent signals completion\n"
                    f"6. SOCRATIC MODE OFF: You extract problems or move to next part\n"
                    f"\n"
                    f"CRITICAL RULES:\n"
                    f"- When teach_part is called, you enter SOCRATIC MODE\n"
                    f"- In Socratic mode, DO NOT call any tools - just pass messages to subagent\n"
                    f"- Subagent will handle all teaching dialogue\n"
                    f"- When subagent says 'Part complete!', exit Socratic mode\n"
                    f"- Then you resume orchestration (extract problems, next part, etc.)\n"
                    f"\n"
                    f"TOOL USAGE BY REQUEST TYPE:\n"
                    f"- INFO requests: get_book_overview ONLY (look up from TOC, answer directly)\n"
                    f"- SUMMARY requests: get_section_content ONLY (load and summarize)\n"
                    f"- TEACHING requests: get_section_content + break_section_into_parts + teach_part(1)\n"
                    f"\n"
                    f"DO NOT confuse these! Simple questions about titles/pages = INFO, not TEACHING.\n"
                    f"\n"
                    f"AVAILABLE TOOLS:\n"
                    f"- get_book_overview: Show table of contents\n"
                    f"- get_section_content: Load section for teaching\n"
                    f"- break_section_into_parts: Create teaching plan (3-5 parts)\n"
                    f"- teach_part(N): Start teaching part N with Socratic subagent\n"
                    f"- extract_practice_problems: Get problems from book\n"
                    f"- get_teaching_progress: Show current progress\n"
                    f"\n"
                    f"Remember: You orchestrate, Socratic subagent teaches.\n"
                )
            }
        ]
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Define all available tools for the agent."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_book_overview",
                    "description": "Get book table of contents (TOC). Use for: (1) showing full TOC ('what's in the book'), (2) answering questions about section titles ('what's the title of section X'), (3) finding page numbers ('what pages is section X'), (4) listing sections in a chapter. Returns section titles and page ranges.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pdf_path": {
                                "type": "string",
                                "description": f"PDF file path (use: {self.pdf_path})"
                            }
                        },
                        "required": ["pdf_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_section_content",
                    "description": "Extract full content of a section from PDF. Use for both TEACHING (follow with break_section_into_parts) and SUMMARY (just summarize the content without teaching).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pdf_path": {
                                "type": "string",
                                "description": f"PDF file path (use: {self.pdf_path})"
                            },
                            "section": {
                                "type": "string",
                                "description": "Section ID (e.g., '1-2', '2-3')"
                            }
                        },
                        "required": ["pdf_path", "section"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "break_section_into_parts",
                    "description": "Break loaded section into 3-5 teaching parts. Creates structured teaching plan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "section_id": {
                                "type": "string",
                                "description": "Section ID (e.g., '1-2')"
                            },
                            "num_parts": {
                                "type": "integer",
                                "description": "Number of parts (3-5 recommended)",
                                "default": 3
                            }
                        },
                        "required": ["section_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "teach_part",
                    "description": "Start teaching a specific part using Socratic subagent. For teaching requests ('teach me section X'), call this immediately after break_section_into_parts. This activates question-driven teaching dialogue and enters SOCRATIC MODE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "part_number": {
                                "type": "integer",
                                "description": "Which part to teach (1-based)"
                            }
                        },
                        "required": ["part_number"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "extract_practice_problems",
                    "description": "Extract problems from textbook section for practice.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "problem_type": {
                                "type": "string",
                                "enum": ["examples", "practice", "both"],
                                "description": "Type of problems",
                                "default": "both"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_teaching_progress",
                    "description": "Show current teaching progress (parts completed, remaining, etc.).",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]
    
    def _call_llm(self, include_tools: bool = True) -> Dict[str, Any]:
        """Call the LLM API with current conversation and tools."""
        payload = {
            "messages": self.conversation_history
        }
        
        if include_tools:
            payload["tools"] = self.get_available_tools()
            payload["tool_choice"] = "auto"
        
        payload["model"] = self.model
        payload["max_tokens"] = 2000
        payload["temperature"] = 0.7
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API call failed: {e}")
            raise Exception(f"LLM API call failed: {e}")
    
    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================
    
    def tool_get_book_overview(self, pdf_path: str) -> str:
        """Tool: Get book overview."""
        try:
            logger.info(f"Getting book overview for: {pdf_path}")
            toc_result = get_pdf_content_range(pdf_path=pdf_path)
            
            if toc_result.startswith("Error:"):
                return toc_result
            
            self.context['toc'] = toc_result
            
            output = "📚 BOOK OVERVIEW\n"
            output += "="*80 + "\n\n"
            output += toc_result
            output += "\n\n" + "="*80
            output += "\n\n💡 Ask me to teach any specific section!"
            
            return output
            
        except Exception as e:
            logger.error(f"Error getting book overview: {e}")
            return f"Error: Could not get book overview - {str(e)}"
    
    def tool_get_section_content(self, pdf_path: str, section: str) -> str:
        """Tool: Get section content."""
        try:
            logger.info(f"Getting section content: {section}")
            
            # Find section
            nav_result = get_pdf_content_range(pdf_path=pdf_path, section=section)
            
            if nav_result.startswith("Error:"):
                return nav_result
            
            # Parse page range
            patterns = [
                r'[Pp]ages?:\s*(\d+)\s*-\s*(\d+)',
                r'[Pp]ages?\s+(\d+)\s*-\s*(\d+)',
            ]
            
            pages = None
            for pattern in patterns:
                match = re.search(pattern, nav_result)
                if match:
                    start_page, end_page = int(match.group(1)), int(match.group(2))
                    pages = (start_page, end_page)
                    break
            
            if not pages:
                return f"Error: Could not determine page range from: {nav_result}"
            
            start_page, end_page = pages
            
            # Extract content
            content = extract_pdf_pages(pdf_path=pdf_path, start_page=start_page, end_page=end_page)
            
            if content.startswith("Error:"):
                return content
            
            # Store in context
            self.context['current_section'] = section
            self.context['section_content'] = content
            self.context['section_page_range'] = pages
            
            output = f"✅ Section {section} Content Loaded\n"
            output += f"Pages: {start_page}-{end_page}\n"
            output += f"Length: {len(content)} characters\n\n"
            output += "📚 Content loaded! Ready to break into parts for teaching."
            
            return output
            
        except Exception as e:
            logger.error(f"Error getting section content: {e}")
            return f"Error: Could not get section content - {str(e)}"
    
    def tool_break_section_into_parts(self, section_id: str, num_parts: int = 3) -> str:
        """Tool: Break section into parts."""
        if not self.context.get('section_content'):
            return f"Error: No section content loaded. Use get_section_content first."
        
        num_parts = int(num_parts)
        
        try:
            logger.info(f"Breaking section {section_id} into {num_parts} parts...")
            
            # Call LLM to analyze and break down section
            analysis_prompt = [
                {
                    "role": "system",
                    "content": (
                        f"Analyze this physics section and break it into {num_parts} logical teaching parts.\n"
                        f"\n"
                        f"SECTION CONTENT:\n{self.context['section_content']}\n"
                        f"\n"
                        f"Respond with ONLY a JSON array of {num_parts} parts:\n"
                        f"[\n"
                        f"  {{\n"
                        f"    \"number\": 1,\n"
                        f"    \"title\": \"Brief title\",\n"
                        f"    \"key_concepts\": [\"concept1\", \"concept2\"],\n"
                        f"    \"pages\": [29, 30],\n"
                        f"    \"equations\": [\"1-1\"]\n"
                        f"  }}\n"
                        f"]\n"
                    )
                },
                {
                    "role": "user",
                    "content": f"Break into {num_parts} parts. Return ONLY JSON array."
                }
            ]
            
            payload = {
                "messages": analysis_prompt,
                "model": self.model,
                "max_tokens": 1000,
                "temperature": 0.3
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=60
            )
            
            response.raise_for_status()
            parts_json = response.json()["choices"][0]["message"]["content"]
            
            # Parse JSON
            json_match = re.search(r'\[.*\]', parts_json, re.DOTALL)
            if json_match:
                parts_json = json_match.group(0)
            
            parts = json.loads(parts_json)
            
            # Store in context
            self.context['teaching_parts'] = parts
            self.context['current_part'] = 0
            
            # Format output (plan created, will proceed to teaching immediately)
            output = f"📋 Teaching Plan for Section {section_id}\n\n"
            
            for part in parts:
                output += f"• **Part {part['number']}: {part['title']}**\n"
            
            output += f"\n✓ Plan created ({len(parts)} parts)\n"
            
            logger.info(f"Successfully broke section into {len(parts)} parts")
            return output
            
        except Exception as e:
            logger.error(f"Error breaking section into parts: {e}")
            return f"Error: Could not break section - {str(e)}"
    
    def tool_teach_part(self, part_number: int) -> str:
        """Tool: Start teaching a part with Socratic subagent."""
        if not self.context.get('teaching_parts'):
            return "Error: No teaching parts. Use break_section_into_parts first."
        
        part_number = int(part_number)
        parts = self.context['teaching_parts']
        
        if part_number < 1 or part_number > len(parts):
            return f"Error: Part {part_number} doesn't exist. Valid: 1-{len(parts)}"
        
        # Get the part
        part = parts[part_number - 1]
        total_parts = len(parts)
        
        # Update current part
        self.context['current_part'] = part_number - 1
        
        # Extract part content from section content
        # For simplicity, pass full section content to subagent
        # (In production, you could extract just the relevant pages)
        part_content = self.context['section_content']
        
        # Store part content
        self.context['current_part_content'] = part_content
        
        # Initialize Socratic subagent with part content
        part_topic = f"Part {part_number}/{total_parts}: {part['title']}"
        self.socratic_tutor.set_section_content(part_content, part_topic)
        
        # Enter Socratic mode
        self.socratic_mode = True
        
        # Get opening from Socratic tutor
        opening = self.socratic_tutor.start_teaching()
        
        logger.info(f"Socratic mode ACTIVATED for Part {part_number}")
        
        # Format output
        output = f"📚 {part_topic}\n\n"
        output += opening
        
        return output
    
    def tool_extract_practice_problems(self, problem_type: str = "both") -> str:
        """Tool: Extract practice problems."""
        if not self.context.get('section_content'):
            return "Error: No section content loaded."
        
        try:
            # Call LLM to extract problems
            extraction_prompt = [
                {
                    "role": "system",
                    "content": (
                        f"Extract {problem_type} problems from this section:\n\n"
                        f"{self.context['section_content']}\n\n"
                        f"Return ONE example problem that's relevant to what was taught.\n"
                        f"Format:\n"
                        f"**Problem [number] (Page X):** [Title]\n"
                        f"\n[Problem statement]\n"
                        f"\n**Given:** ...\n"
                        f"**Find:** ...\n"
                    )
                },
                {
                    "role": "user",
                    "content": f"Extract {problem_type} problem."
                }
            ]
            
            payload = {
                "messages": extraction_prompt,
                "model": self.model,
                "max_tokens": 1000,
                "temperature": 0.3
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=60
            )
            
            response.raise_for_status()
            problems = response.json()["choices"][0]["message"]["content"]
            
            # Handle JSON format if present
            if problems.startswith('[{"type":'):
                try:
                    parsed = json.loads(problems)
                    if isinstance(parsed, list) and len(parsed) > 0 and "text" in parsed[0]:
                        problems = parsed[0]["text"]
                except:
                    pass
            
            return problems
            
        except Exception as e:
            logger.error(f"Error extracting problems: {e}")
            return f"Error: Could not extract problems - {str(e)}"
    
    def tool_get_teaching_progress(self) -> str:
        """Tool: Get teaching progress."""
        if not self.context.get('teaching_parts'):
            return "No active teaching session."
        
        parts = self.context['teaching_parts']
        current = self.context.get('current_part', 0)
        
        output = f"📊 Teaching Progress\n\n"
        
        for i, part in enumerate(parts):
            status = "✅" if i < current else "▶️" if i == current else "⏸️"
            output += f"{status} Part {part['number']}: {part['title']}\n"
        
        output += f"\n**Completed:** {current}/{len(parts)}\n"
        
        return output
    
    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Execute a tool and return result."""
        logger.info(f"Executing tool: {tool_name}")
        
        if tool_name == "get_book_overview":
            return self.tool_get_book_overview(**tool_args)
        elif tool_name == "get_section_content":
            return self.tool_get_section_content(**tool_args)
        elif tool_name == "break_section_into_parts":
            return self.tool_break_section_into_parts(**tool_args)
        elif tool_name == "teach_part":
            return self.tool_teach_part(**tool_args)
        elif tool_name == "extract_practice_problems":
            return self.tool_extract_practice_problems(**tool_args)
        elif tool_name == "get_teaching_progress":
            return self.tool_get_teaching_progress(**tool_args)
        else:
            return f"Error: Unknown tool '{tool_name}'"
    
    def chat(self, user_message: str) -> str:
        """
        Main chat interface with Socratic mode support.
        
        Returns tutor's response.
        """
        # Check if we're in Socratic mode
        if self.socratic_mode:
            # Check for exit signals
            if any(phrase in user_message.lower() for phrase in [
                "done with this part",
                "move to next part",
                "next part",
                "that covers this",
                "ready for next"
            ]):
                # Exit Socratic mode
                self.socratic_mode = False
                logger.info("Socratic mode DEACTIVATED")
                
                # Return to orchestration
                return f"Great! Part {self.context['current_part'] + 1} complete. Ready for the next part or practice problems?"
            
            # Pass to Socratic subagent
            logger.info("Socratic mode: Passing message to subagent")
            response = self.socratic_tutor.respond(user_message)
            return response
        
        # Normal orchestration mode
        # Add user message
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Tool execution loop - continue until no more tool calls or teach_part is activated
        max_rounds = 5  # Prevent infinite loops
        round_count = 0
        
        while round_count < max_rounds:
            round_count += 1
            
            # Call LLM with tools
            response = self._call_llm(include_tools=True)
            message = response["choices"][0]["message"]
            
            # Add assistant message
            self.conversation_history.append(message)
            
            # Check for tool calls
            if message.get("tool_calls"):
                for tool_call in message["tool_calls"]:
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])
                    
                    # Execute tool
                    result = self._execute_tool(function_name, function_args)
                    
                    # Add tool response to history
                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function_name,
                        "content": result
                    })
                    
                    # If teach_part was called, return its result directly (enters Socratic mode)
                    if function_name == "teach_part":
                        return result
                
                # Continue loop to allow next round of tool calls
                continue
            
            # No more tool calls - return the content
            return message.get("content") or "I had trouble generating a response."
        
        # Max rounds reached
        return "I apologize, I got stuck in my planning. Could you rephrase your request?"


# ============================================================================
# Interactive Mode
# ============================================================================

def interactive_mode():
    """Run the integrated agent in interactive mode."""
    if len(sys.argv) < 2:
        print("Usage: python ai_tutor_agent_with_socratic.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)
    
    # Configuration
    api_url = "https://smapi-int-tsta.bcbsfl.com/gpt/api/v1/models/meta-llama/Llama-4-Scout-17B-16E-Instruct/v1/chat/completions"
    username = "m8yl"
    password = "Fl33ll66"
    
    print("\n" + "="*80)
    print("AI TUTOR AGENT + SOCRATIC SUBAGENT")
    print("="*80)
    print(f"PDF: {os.path.basename(pdf_path)}")
    print("\nThe agent orchestrates, the Socratic subagent teaches.")
    print("="*80)
    
    # Initialize agent
    agent = AITutorAgentWithSocratic(
        api_url=api_url,
        pdf_path=pdf_path,
        username=username,
        password=password
    )
    
    print("\n✅ Ready!")
    print("\nTry:")
    print("  - 'What's in this book?'")
    print("  - 'Teach me section 1-2'")
    print("\nType 'quit' to exit\n")
    print("="*80 + "\n")
    
    # Main loop
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye! 📚")
                break
            
            # Show mode indicator
            mode_indicator = "🎓 [SOCRATIC]" if agent.socratic_mode else "🤖 [ORCHESTRATOR]"
            print(f"\n{mode_indicator} Thinking...\n")
            
            # Get response
            response = agent.chat(user_input)
            print(f"Tutor: {response}\n")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye! 📚")
            break
        
        except Exception as e:
            print(f"\nError: {str(e)}\n")
            logger.error(f"Error in main loop: {e}", exc_info=True)


if __name__ == "__main__":
    interactive_mode()
