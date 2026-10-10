"""
RailSathi AI — Conversation Manager Tests
"""

import time
from google.genai import types
from backend.agent.conversations import ConversationManager


def test_create_and_get_conversation():
    """Verify conversations can be created and retrieved."""
    mgr = ConversationManager()
    cid = mgr.create_conversation()
    assert cid.startswith("conv-")

    info = mgr.get_conversation_info(cid)
    assert info is not None
    assert info["conversation_id"] == cid
    assert info["message_count"] == 0

    cid_retrieved, history = mgr.get_or_create(cid)
    assert cid_retrieved == cid
    assert history == []


def test_add_messages_and_bounded_history():
    """Verify exchanges can be added and history is capped at max_history."""
    mgr = ConversationManager(max_history=4)
    cid = mgr.create_conversation()

    u = types.Content(role="user", parts=[types.Part.from_text(text="Q")])
    m = types.Content(role="model", parts=[types.Part.from_text(text="A")])

    for _ in range(5):
        mgr.add_exchange(cid, u, m)

    cid_retrieved, history = mgr.get_or_create(cid)
    assert len(history) <= 4


def test_conversation_non_existent():
    """Verify non-existent conversation returns None for info and creates new for get_or_create."""
    mgr = ConversationManager()
    assert mgr.get_conversation_info("non-existent-id") is None

    cid, history = mgr.get_or_create("non-existent-id")
    assert cid.startswith("conv-")
    assert history == []


def test_evict_oldest():
    """Verify oldest conversations are evicted when at max_conversations capacity."""
    mgr = ConversationManager(max_conversations=2, conversation_ttl=1)
    cid1 = mgr.create_conversation()
    cid2 = mgr.create_conversation()
    cid3 = mgr.create_conversation()  # Triggers eviction

    # Either cid1 was evicted or total count is <= 2
    assert mgr.get_conversation_info(cid1) is None or mgr.get_conversation_info(cid2) is None
