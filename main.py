import os

from chat_node import ChatNode
from config import BASE_PROMPT, VC_INVESTOR_PROMPT, WAITLIST_PROMPT, FAST_TRACKED_PROMPT, VERIFIED_MEMBER_PROMPT
from loguru import logger
from supabase import create_client

from line import Bridge, CallRequest, VoiceAgentApp, VoiceAgentSystem
from line.events import (
    UserStartedSpeaking,
    UserStoppedSpeaking,
    UserTranscriptionReceived,
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def determine_system_prompt(phone_number: str) -> str:
    """
    Determine which system prompt to use based on invitee status and role.
    
    Logic:
    - If phone NOT in invitees table -> base_prompt + WAITLIST_PROMPT
    - If phone in invitees and role is investor/vc -> base_prompt + VC_INVESTOR_PROMPT
    - If phone in invitees and role is verified member -> base_prompt + VERIFIED_MEMBER_PROMPT
    - Otherwise (founder, executive, advisor, etc.) -> base_prompt + FAST_TRACKED_PROMPT
    """
    
    # Check if phone number exists in invitees table
    invitee_check = (
        supabase
        .table("invitees")
        .select("first_name, role, achievements")
        .eq("phone", phone_number)
        .limit(1)
        .execute()
    )
    
    # Phone number NOT in invitees table - use waitlist flow
    if not invitee_check.data:
        logger.info(f"Phone {phone_number} not in invitees - using WAITLIST flow")
        return BASE_PROMPT + "\n\n" + WAITLIST_PROMPT
    
    # Phone number IS in invitees table - check role
    invitee = invitee_check.data[0]
    role = invitee.get("role", "").lower()
    first_name = invitee.get("first_name", "")
    achievements = invitee.get("achievements", "")
    
    # Add invitee context
    invitee_context = (
        f"Invitee Name: {first_name}\n"
        f"Invitee Role: {invitee.get('role', '')}\n"
        f"Invitee achievements context: {achievements}\n\n"
    )
    
    # Determine prompt based on role
    if role == "investor/vc":
        logger.info(f"Phone {phone_number} is investor/VC - using VC_INVESTOR flow")
        return BASE_PROMPT + "\n\n" + invitee_context + VC_INVESTOR_PROMPT
    
    elif role == "verified member":
        logger.info(f"Phone {phone_number} is verified member - using VERIFIED_MEMBER flow")
        return BASE_PROMPT + "\n\n" + invitee_context + VERIFIED_MEMBER_PROMPT
    
    else:
        # Founder, Executive, Advisor, or other roles
        logger.info(f"Phone {phone_number} with role '{role}' - using FAST_TRACKED flow")
        return BASE_PROMPT + "\n\n" + invitee_context + FAST_TRACKED_PROMPT

async def handle_new_call(system: VoiceAgentSystem, call_request: CallRequest):
    logger.info(
        f"Starting new call for {call_request.call_id}. "
        f"Call request: { {k: v for k, v in call_request.__dict__.items() if k != 'agent'} }, "
        f"agent.system_prompt: {call_request.agent.system_prompt[:100] if getattr(call_request.agent, 'system_prompt', None) else None}, "
        f"agent.introduction: {call_request.agent.introduction[:100] if getattr(call_request.agent, 'introduction', None) else None}. "
    )

    
    # Main conversation node (LangChain-powered)
    phone = call_request.to
    final_system_prompt = determine_system_prompt(phone)
    
    conversation_node = ChatNode(
        system_prompt=call_request.agent.system_prompt or final_system_prompt,
        phone_number=call_request.to,
    )

    conversation_bridge = Bridge(conversation_node)
    system.with_speaking_node(conversation_node, bridge=conversation_bridge)

    # Feed user transcripts into reasoning node
    conversation_bridge.on(UserTranscriptionReceived).map(
        conversation_node.add_event
    )

    # Streaming + interruption handling
    (
        conversation_bridge.on(UserStoppedSpeaking)
        .interrupt_on(
            UserStartedSpeaking,
            handler=conversation_node.on_interrupt_generate,
        )
        .stream(conversation_node.generate)
        .broadcast()
    )

    await system.start()

    # Initial greeting
    if call_request.agent.introduction:
        await system.send_initial_message(
            "Hello! I’m Ellie from Elevate Members. Tell me about yourself."
        )

    await system.wait_for_shutdown()


app = VoiceAgentApp(handle_new_call)

if __name__ == "__main__":
    app.run()
