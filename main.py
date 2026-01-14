import os

from chat_node import ChatNode
from config import SYSTEM_PROMPT
from loguru import logger

from line import Bridge, CallRequest, VoiceAgentApp, VoiceAgentSystem
from line.events import (
    UserStartedSpeaking,
    UserStoppedSpeaking,
    UserTranscriptionReceived,
)


async def handle_new_call(system: VoiceAgentSystem, call_request: CallRequest):
    logger.info(
        f"Starting new call for {call_request.call_id}. "
        f"Call request: { {k: v for k, v in call_request.__dict__.items() if k != 'agent'} }, "
        f"agent.system_prompt: {call_request.agent.system_prompt[:100] if getattr(call_request.agent, 'system_prompt', None) else None}, "
        f"agent.introduction: {call_request.agent.introduction[:100] if getattr(call_request.agent, 'introduction', None) else None}. "
    )

    # Main conversation node (LangChain-powered)
    conversation_node = ChatNode(
        system_prompt=call_request.agent.system_prompt or SYSTEM_PROMPT,
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
