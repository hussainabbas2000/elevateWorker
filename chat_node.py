"""
LangChainReasoningNode – Voice-optimized conversational agent
Natural conversation with guaranteed call termination
"""

import asyncio
import os
from typing import AsyncGenerator, Union
from dotenv import load_dotenv
from loguru import logger


# from twilio.rest import Client

# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

# twilio_client = Client(
#     TWILIO_ACCOUNT_SID,
#     TWILIO_AUTH_TOKEN
# )

# def send_followup_sms(to_number: str):
#     if not to_number:
#         return

#     try:
#         twilio_client.messages.create(
#             body="It was lovely chatting with you. We will contact you soon regarding next steps!",
#             from_=TWILIO_FROM_NUMBER,
#             to=to_number,
#         )
#         logger.info("📩 Follow-up SMS sent")
#     except Exception as e:
#         logger.error(f"❌ SMS send failed: {e}")

from line.events import (
    UserTranscriptionReceived,
    AgentResponse,
    EndCall,
)
from line.nodes.conversation_context import ConversationContext
from line.nodes.reasoning import ReasoningNode
from line.tools.system_tools import EndCallArgs, EndCallTool, end_call

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
    text = text.lower()
    phrases = [
        "it was a pleasure",
        "great talking to you",
        "have a wonderful day",
        "bye",
        "goodbye",
        "we'll be in touch",
        "we will be in touch",
        "talk soon",
        "thanks for your time",
    ]
    return any(p in text for p in phrases)

# -------------------------------------------------------------------
# ChatNode
# -------------------------------------------------------------------

class ChatNode(ReasoningNode):
    """
    Voice-first conversational reasoning node
    """

    def __init__(
        self,
        system_prompt: str,
        model: str = "gemini-2.5-flash",
        temperature: float = DEFAULT_TEMPERATURE,
        max_context_length: int = 100,
        phone_number: str | None = None,
    ):
        super().__init__(system_prompt, max_context_length)

        self.llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            streaming=True,
            tools=[EndCallTool],
        )

        self.phone_number = phone_number
        logger.info("🧠 ChatNode initialized")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def extract_transcript(self, events):
        transcript = []
        for e in events:
            if isinstance(e, UserTranscriptionReceived):
                transcript.append({"role": "user", "content": e.content})
            elif isinstance(e, AgentResponse):
                transcript.append({"role": "agent", "content": e.content})
        return transcript

    async def generate_summary(self, transcript):
        prompt = [
            SystemMessage(
                content=(
                    "Summarize this voice conversation for internal review. "
                    "Highlight background, motivations, personality traits, "
                    "communication style, and fit for Elevate."
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
        prompt = [
            SystemMessage(
                content=(
                    "You are an internal evaluator for Elevate.\n\n"
                    "Your task is to evaluate the candidate based ONLY on the summary below "
                "and assign a single overall strength score.\n\n"

                "Evaluate across these dimensions:\n"
                "- Innovation & originality\n"
                "- Initiative & ownership\n"
                "- Leadership potential\n"
                "- Confidence & presence\n"
                "- Communication clarity\n"
                "- Risk-taking mindset\n"
                "- Uniqueness / X-factor\n"
                "- Founder or builder mindset\n"
                "- Overall fit for Elevate\n\n"

                "Scoring rules:\n"
                "- Score must be an INTEGER between 0 and 100\n"
                "- Be honest and critical, not optimistic\n"
                "- 80–100: Strong candidate\n"
                "- 60–79: Medium candidate\n"
                "- Below 60: Weak candidate\n"
                "- Do NOT inflate scores without strong evidence\n\n"

                "Output requirements:\n"
                "- Return ONLY valid JSON\n"
                "- No markdown, no explanations outside JSON\n"
                "- Use EXACTLY this format:\n\n"
                "{\n"
                '  "score": <number>,\n'
                '  "verdict": "Strong" | "Medium" | "Weak",\n'
                '  "reasoning": "Brief, concrete explanation referencing specific traits or behaviors"\n'
                "}\n\n"

                "Candidate summary:"
            )
        ),
        HumanMessage(content=summary),
    ]

        response = await self.llm.ainvoke(prompt)
        return response.content

    
    def _messages_from_events(self, events):
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

        if not context.events:
            return

        messages = self._messages_from_events(context.events)
        full_response = ""

        async for chunk in self.llm.astream(messages):

            # Stream text
            if chunk.content:
                full_response += chunk.content
                yield AgentResponse(content=chunk.content)

            # Tool-based hangup (ideal path)
            if getattr(chunk, "tool_calls", None):
                for call in chunk.tool_calls:
                    if call["name"] == "EndCall":
                        logger.info("📞 Model requested end call")
                        await self._finalize_and_hangup(
                            context,
                            call["args"].get(
                                "goodbye_message",
                                "It was a pleasure speaking with you. Goodbye!"
                            ),
                        )
                        yield EndCall()
                        return

        # ------------------------------------------------------------------
        # Fallback hangup if model forgot tool
        # ------------------------------------------------------------------

        if should_force_hangup(full_response):
            logger.warning("⚠️ Forcing hangup via semantic detection")
            await self._finalize_and_hangup(
                context,
                "It was a pleasure speaking with you. Goodbye!"
            )
            yield EndCall()
            return

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    async def _finalize_and_hangup(self, context, goodbye_message: str):
        transcript = self.extract_transcript(context.events)
        summary = await self.generate_summary(transcript)
        score = await self.generate_score(summary)
        print("FINAL SCORE:", score)

        try:
            supabase.table("call_sessions").insert({
                "phone": self.phone_number or "unknown",
                "summary": summary,
                "transcript": transcript,
                "score": score,
            }).execute()
            logger.info("✅ Call saved")
        except Exception as e:
            logger.error(f"❌ Supabase error: {e}")

        
        await asyncio.sleep(0.6)

        async for _ in end_call(
            EndCallArgs(goodbye_message=goodbye_message)
        ):
            pass
