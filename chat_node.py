"""
LangChainReasoningNode – Voice-optimized conversational agent
Immediate call termination with async background finalization
"""

import asyncio
import os
from typing import AsyncGenerator, Union
from dotenv import load_dotenv
from loguru import logger

from line.events import (
    UserTranscriptionReceived,
    AgentResponse,
    EndCall,
)
from line.nodes.conversation_context import ConversationContext
from line.nodes.reasoning import ReasoningNode
from line.tools.system_tools import EndCallTool

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI

from supabase import create_client
from config import DEFAULT_TEMPERATURE

# -------------------------------------------------------------------
# Environment
# -------------------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def should_force_hangup(text: str) -> bool:
    """Check if text contains goodbye phrases - immediate detection"""
    text = text.lower().strip()
    
    # Exact phrases (standalone words)
    exact_phrases = [
        "goodbye",
        "bye bye",
        "talk soon",
        "talk to you soon",
        "speak soon",
    ]
    
    # Partial phrases that indicate conversation end
    partial_phrases = [
        "it was a pleasure",
        "great talking to you",
        "great chatting",
        "have a wonderful day",
        "have a great day",
        "we'll be in touch",
        "we will be in touch",
        "thanks for your time",
        "take care",
        "best of luck",
        "looking forward to",
    ]
    
    # Check exact matches
    words = text.split()
    if any(phrase in words for phrase in exact_phrases):
        return True
    
    # Check partial matches
    if any(phrase in text for phrase in partial_phrases):
        return True
    
    # Special case: "bye" as standalone or at boundaries
    if text.endswith(" bye") or text.startswith("bye ") or text == "bye":
        return True
        
    return False

# -------------------------------------------------------------------
# ChatNode
# -------------------------------------------------------------------

class ChatNode(ReasoningNode):
    """
    Voice-first conversational reasoning node with immediate call termination
    """

    def __init__(
        self,
        system_prompt: str,
        model: str = "gemini-2.5-flash",
        temperature: float = DEFAULT_TEMPERATURE,
        max_context_length: int = 100,
        phone_number: str | None = None,
    ):

        res = (
                supabase
                .table("profiles")
                .select()
                .eq("phone", phone_number)
                .limit(1)
                .execute()
            )

        firstName = res.data[0]["first_name"] if res.data else None
        lastName = res.data[0]["last_name"] if res.data else None
        system_prompt = f"Context: User's name is {firstName}" + system_prompt
        super().__init__(system_prompt, max_context_length)

        self.llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            streaming=True,
            tools=[EndCallTool],
        )

        self.phone_number = phone_number
        self._finalized = False

        logger.info("🧠 ChatNode initialized")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def extract_transcript(self, events):
        """Extract clean transcript from conversation events"""
        transcript = []
        for e in events:
            if isinstance(e, UserTranscriptionReceived):
                transcript.append({"role": "user", "content": e.content})
            elif isinstance(e, AgentResponse):
                transcript.append({"role": "agent", "content": e.content})
        return transcript

    async def generate_summary(self, transcript):
        """Generate interview summary from transcript"""
        prompt = [
            SystemMessage(
                content=(
                    "Summarize this voice conversation for internal review. "
                    "Highlight the candidate's background, motivations, personality traits, "
                    "communication style, and overall fit for Elevate. "
                    "Be thorough but concise."
                )
            ),
            HumanMessage(
                content="\n".join(
                    f"{m['role'].upper()}: {m['content']}" for m in transcript
                )
            ),
        ]
        return (await self.llm.ainvoke(prompt)).content

    async def generate_score(self, summary: str) -> str:
        """Generate membership evaluation score"""
        prompt = [
            SystemMessage(
                content=(
                    "You are the admissions evaluator for Elevate, an exclusive community of high-achieving investors, founders, and executives.\n\n"
                    "Your role is to assess whether candidates meet Elevate's standards for membership. Elevate seeks individuals who:\n"
                    "- Hold significant leadership positions (C-suite, VP+, Founder, Partner-level)\n"
                    "- Demonstrate exceptional professional achievements and impact\n"
                    "- Show genuine engagement with the community's mission and values\n"
                    "- Bring valuable expertise, connections, or resources to the network\n"
                    "- Display intellectual curiosity, ambition, and collaborative mindset\n\n"
                    "Evaluation Framework:\n"
                    "1. Professional Stature (0-30 points)\n"
                    "   - Current role seniority and scope of responsibility\n"
                    "   - Track record of leadership and measurable achievements\n"
                    "   - Industry reputation and credibility\n\n"
                    "2. Value Proposition (0-30 points)\n"
                    "   - Unique expertise or domain knowledge\n"
                    "   - Network quality and strategic connections\n"
                    "   - Potential to contribute insights, deals, or opportunities\n\n"
                    "3. Alignment & Engagement (0-25 points)\n"
                    "   - Understanding of and enthusiasm for Elevate's mission\n"
                    "   - Demonstrated commitment to professional growth\n"
                    "   - Cultural fit and collaborative approach\n\n"
                    "4. Communication & Presence (0-15 points)\n"
                    "   - Articulation of ideas and professional polish\n"
                    "   - Confidence and executive presence\n"
                    "   - Authenticity and self-awareness\n\n"
                    "Verdict Guidelines:\n"
                    "- Strong (75-100): Clear admit - Exemplary candidate who will elevate the community\n"
                    "- Medium (50-74): Conditional - Promising but needs verification or has minor gaps\n"
                    "- Weak (0-49): Decline - Does not meet Elevate's membership standards\n\n"
                    "Be discerning and maintain high standards. Elevate's exclusivity depends on rigorous selection.\n\n"
                    "Return ONLY valid JSON with no markdown, preamble, or additional text:\n\n"
                    "{\n"
                    '  "score": <integer 0-100>,\n'
                    '  "verdict": "Strong" | "Medium" | "Weak",\n'
                    '  "reasoning": "<Concise 3-4 sentence evaluation covering: (1) key strengths, (2) any concerns or gaps, (3) overall fit for Elevate>"\n'
                    "}"
                )
            ),
            HumanMessage(content=f"Candidate Interview Summary:\n\n{summary}"),
        ]

        response = await self.llm.ainvoke(prompt)
        return response.content

    def _messages_from_events(self, events):
        """Convert conversation events to LangChain messages"""
        messages = [SystemMessage(content=self.system_prompt)]
        for e in events:
            if isinstance(e, UserTranscriptionReceived):
                messages.append(HumanMessage(content=e.content))
            elif isinstance(e, AgentResponse):
                messages.append(AIMessage(content=e.content))
        return messages

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    async def process_context(
        self, context: ConversationContext
    ) -> AsyncGenerator[Union[AgentResponse, EndCall], None]:
        """Process conversation with immediate goodbye detection"""

        if not context.events:
            return

        messages = self._messages_from_events(context.events)
        full_response = ""

        async for chunk in self.llm.astream(messages):

            # Stream spoken text
            if chunk.content:
                full_response += chunk.content
                
                # 🔥 Check for goodbye IMMEDIATELY after each chunk
                if should_force_hangup(full_response):
                    logger.info(f"📞 Goodbye detected: '{full_response.strip()}'")
                    
                    # Yield this final chunk
                    yield AgentResponse(content=chunk.content)
                    
                    # Trigger background save and end call immediately
                    self._trigger_background_finalize(context)
                    yield EndCall()
                    return
                
                # Continue streaming normally
                yield AgentResponse(content=chunk.content)

            # Tool-based hangup (explicit EndCall tool)
            if getattr(chunk, "tool_calls", None):
                for call in chunk.tool_calls:
                    if call["name"] == "EndCall":
                        logger.info("📞 Model requested EndCall via tool")

                        self._trigger_background_finalize(context)
                        yield EndCall()
                        return

    # ------------------------------------------------------------------
    # Finalization (background, non-blocking)
    # ------------------------------------------------------------------

    def _trigger_background_finalize(self, context):
        """Start background finalization task (non-blocking)"""
        if self._finalized:
            return
        self._finalized = True
        asyncio.create_task(self._finalize_and_save(context))

    async def _finalize_and_save(self, context):
        """Generate summary, score, and save to database"""
        try:
            logger.info("📝 Starting call finalization...")
            
            # Extract and process
            transcript = self.extract_transcript(context.events)
            summary = await self.generate_summary(transcript)
            score = await self.generate_score(summary)

            # Save to database
            supabase.table("call_sessions").insert({
                "phone": self.phone_number or "unknown",
                "summary": summary,
                "transcript": transcript,
                "score": score,
            }).execute()

            logger.info("✅ Call finalized and saved to database")

        except Exception as e:
            logger.error(f"❌ Finalization error: {e}")