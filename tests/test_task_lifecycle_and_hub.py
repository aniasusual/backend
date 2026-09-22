"""
Unit tests for Phase 4 Lifecycle & Hub:
- AgentRegistry status transitions and peer filtering
- AgentLifecycleManager idle parking and dynamic session revival
- AsyncJobManager background execution, status queries, cancellation, and delivery queue
- IrcBus and HubTool peer-to-peer messaging, inbox, wait, and parked peer wake-up
"""

import unittest
import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock

from task.types import SubagentProgress, TaskItem, AgentDefinition, SingleResult
from task.registry import AgentRegistry
from task.lifecycle import AgentLifecycleManager
from task.async_jobs import AsyncJobManager
from task.hub import IrcBus, HubTool


class TestAgentRegistry(unittest.TestCase):
    """Test global agent ledger and status tracking."""

    def setUp(self):
        AgentRegistry.reset()
        self.registry = AgentRegistry.get_global()

    def tearDown(self):
        AgentRegistry.reset()

    def test_register_and_query_status(self):
        p = SubagentProgress(id="scout_1", agent="scout", status="running", task="t", assignment="t")
        self.registry.register("scout_1", p)

        self.assertEqual(self.registry.get("scout_1").status, "running")

        # Update status
        self.registry.update_status("scout_1", "idle")
        self.assertEqual(self.registry.get("scout_1").status, "idle")

    def test_active_peers_filtering(self):
        self.registry.register("a1", SubagentProgress(id="a1", agent="scout", status="running", task="t", assignment="t"))
        self.registry.register("a2", SubagentProgress(id="a2", agent="reviewer", status="idle", task="t", assignment="t"))
        self.registry.register("a3", SubagentProgress(id="a3", agent="task", status="completed", task="t", assignment="t"))
        self.registry.register("a4", SubagentProgress(id="a4", agent="task", status="parked", task="t", assignment="t"))

        # Query active peers excluding self
        peers = self.registry.get_active_peers(exclude_id="a1")
        peer_ids = [p.id for p in peers]
        self.assertIn("a2", peer_ids)
        self.assertNotIn("a1", peer_ids)  # self excluded
        self.assertNotIn("a3", peer_ids)  # completed excluded
        self.assertNotIn("a4", peer_ids)  # parked excluded

    def test_invalid_status_rejected(self):
        """Verify invalid lifecycle status strings are rejected."""
        p = SubagentProgress(id="scout_x", agent="scout", status="running", task="t", assignment="t")
        self.registry.register("scout_x", p)
        self.assertFalse(self.registry.update_status("scout_x", "bogus_state"))
        self.assertEqual(self.registry.get("scout_x").status, "running")

class TestAgentLifecycleManager(unittest.TestCase):
    """Test idle TTL tracking, automatic parking, and session revival."""

    def setUp(self):
        AgentRegistry.reset()
        self.registry = AgentRegistry.get_global()
        self.lifecycle = AgentLifecycleManager(registry=self.registry, idle_ttl_seconds=10.0)

    def tearDown(self):
        AgentRegistry.reset()

    def test_idle_parking_after_ttl(self):
        p = SubagentProgress(id="worker_1", agent="task", status="running", task="t", assignment="t")
        self.registry.register("worker_1", p)

        # Mark idle at time T=100
        self.lifecycle.mark_idle("worker_1")
        self.assertEqual(self.registry.get("worker_1").status, "idle")

        # Check at T=105 (within TTL=10s) -> should NOT be parked
        parked = self.lifecycle.check_idle_parking(now=time.time() + 5.0)
        self.assertEqual(len(parked), 0)
        self.assertEqual(self.registry.get("worker_1").status, "idle")

        # Check at T=115 (past TTL=10s) -> should be parked
        parked = self.lifecycle.check_idle_parking(now=time.time() + 15.0)
        self.assertIn("worker_1", parked)
        self.assertEqual(self.registry.get("worker_1").status, "parked")

    def test_revival_of_parked_session(self):
        reviver_called = False

        def dummy_reviver():
            nonlocal reviver_called
            reviver_called = True
            return "revived_session_instance"

        p = SubagentProgress(id="worker_2", agent="task", status="running", task="t", assignment="t")
        self.registry.register("worker_2", p, reviver=dummy_reviver)

        # Park it
        self.lifecycle.park("worker_2")
        self.assertEqual(self.registry.get("worker_2").status, "parked")

        # Revive it
        session = self.lifecycle.revive("worker_2")
        self.assertTrue(reviver_called)
        self.assertEqual(session, "revived_session_instance")
        self.assertEqual(self.registry.get("worker_2").status, "idle")

    def test_idle_parking_ignores_completed_agents(self):
        """Verify agents that completed are never parked by idle TTL check."""
        p = SubagentProgress(id="finisher", agent="task", status="running", task="t", assignment="t")
        self.registry.register("finisher", p)
        self.lifecycle.mark_idle("finisher")

        # Agent finishes task
        self.registry.update_status("finisher", "completed")

        # Run idle check past TTL
        parked = self.lifecycle.check_idle_parking(now=time.time() + 500.0)
        self.assertNotIn("finisher", parked)
        self.assertEqual(self.registry.get("finisher").status, "completed")

    def test_revive_only_acts_on_parked(self):
        """Verify reviving a non-parked agent is a safe no-op."""
        p = SubagentProgress(id="active_agent", agent="task", status="running", task="t", assignment="t")
        self.registry.register("active_agent", p)
        res = self.lifecycle.revive("active_agent")
        self.assertIsNone(res)
        self.assertEqual(self.registry.get("active_agent").status, "running")

class TestAsyncJobManager(unittest.IsolatedAsyncioTestCase):
    """Test background task execution, job listing, cancellation, and auto-deliveries."""

    def setUp(self):
        AgentRegistry.reset()
        self.registry = AgentRegistry.get_global()
        self.mgr = AsyncJobManager(registry=self.registry)

    def tearDown(self):
        AgentRegistry.reset()

    async def test_async_job_lifecycle_and_delivery(self):
        mock_registry = MagicMock()
        mock_registry.sandbox_path = Path("/tmp")
        mock_registry.get_tools.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "yield", "arguments": {"data": {"result": "background_done"}}}}],
            },
        }

        item = TaskItem(agent="task", task="Background job")
        defn = AgentDefinition(name="task", description="Worker", tools=[])

        job_id = self.mgr.register(
            agent_id="bg_agent_1",
            task_item=item,
            agent_definition=defn,
            context={"project_root": Path("/tmp")},
            tool_registry=mock_registry,
            client=mock_client,
        )

        self.assertIsNotNone(job_id)
        # Give asyncio event loop time to run the task
        await asyncio.sleep(0.05)

        # Check job completed
        job = self.mgr.get_job(job_id)
        self.assertEqual(job["status"], "completed")

        # Check delivery queue
        deliveries = self.mgr.consume_deliveries()
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].id, "bg_agent_1")
        self.assertEqual(deliveries[0].structured_output, {"result": "background_done"})

    async def test_async_job_cancellation(self):
        mock_registry = MagicMock()
        mock_registry.sandbox_path = Path("/tmp")
        mock_registry.get_tools.return_value = {}

        # Simulates long-running task by sleeping in chat call
        mock_client = MagicMock()
        def slow_chat(*args, **kwargs):
            time.sleep(0.5)
            return {"message": {"content": ""}}
        mock_client.chat.side_effect = slow_chat

        item = TaskItem(agent="task", task="Slow task")
        defn = AgentDefinition(name="task", description="Worker", tools=[])

        job_id = self.mgr.register(
            agent_id="slow_agent",
            task_item=item,
            agent_definition=defn,
            context={"project_root": Path("/tmp")},
            tool_registry=mock_registry,
            client=mock_client,
        )

        # Cancel while running
        cancelled = self.mgr.cancel_job(job_id)
        self.assertTrue(cancelled)
        job = self.mgr.get_job(job_id)
        self.assertEqual(job["status"], "aborted")
        self.assertEqual(self.registry.get("slow_agent").status, "aborted")


    async def test_cancellation_delivers_aborted_single_result(self):
        """Verify cancelling a job places an aborted SingleResult into delivery queue."""
        mock_registry = MagicMock()
        mock_registry.sandbox_path = Path("/tmp")
        mock_registry.get_tools.return_value = {}

        # Slow job
        mock_client = MagicMock()
        mock_client.chat.side_effect = lambda *args, **kwargs: time.sleep(0.3)

        item = TaskItem(agent="task", task="Slow work")
        defn = AgentDefinition(name="task", description="Worker", tools=[])

        job_id = self.mgr.register(
            agent_id="cancel_deliver_test",
            task_item=item,
            agent_definition=defn,
            context={"project_root": Path("/tmp")},
            tool_registry=mock_registry,
            client=mock_client,
        )

        self.mgr.cancel_job(job_id)
        deliveries = self.mgr.consume_deliveries()
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].id, "cancel_deliver_test")
        self.assertTrue(deliveries[0].aborted)
        self.assertIn("cancelled", deliveries[0].error.lower())
class TestIrcBusAndHubTool(unittest.IsolatedAsyncioTestCase):
    """Test peer-to-peer IRC messaging bus and HubTool operations."""

    def setUp(self):
        AgentRegistry.reset()
        IrcBus.reset()
        self.registry = AgentRegistry.get_global()
        self.bus = IrcBus.get_global()
        self.lifecycle = AgentLifecycleManager(registry=self.registry)
        self.async_mgr = AsyncJobManager(registry=self.registry)

    def tearDown(self):
        AgentRegistry.reset()
        IrcBus.reset()

    async def test_peer_messaging_send_and_inbox(self):
        hub_a = HubTool(self_agent_id="agent_a", bus=self.bus, registry=self.registry)
        hub_b = HubTool(self_agent_id="agent_b", bus=self.bus, registry=self.registry)

        # Agent A sends message to Agent B
        res = await hub_a.execute(op="send", to="agent_b", message="Hello Agent B!")
        self.assertIn("Message delivered to 'agent_b'", res)

        # Agent B checks inbox
        inbox_res = await hub_b.execute(op="inbox")
        self.assertIn("Hello Agent B!", inbox_res)
        self.assertIn("agent_a", inbox_res)

        # Second inbox call is empty (messages consumed)
        inbox_res_empty = await hub_b.execute(op="inbox")
        self.assertIn("Inbox is empty", inbox_res_empty)

    async def test_wait_for_incoming_message(self):
        hub_a = HubTool(self_agent_id="agent_a", bus=self.bus, registry=self.registry)
        hub_b = HubTool(self_agent_id="agent_b", bus=self.bus, registry=self.registry)

        # Schedule agent A to send a message after a short delay
        async def send_later():
            await asyncio.sleep(0.05)
            await hub_a.execute(op="send", to="agent_b", message="Coordination handshake")

        asyncio.create_task(send_later())

        # Agent B waits for message
        wait_res = await hub_b.execute(op="wait", timeout=1.0)
        self.assertIn("Received message from 'agent_a'", wait_res)
        self.assertIn("Coordination handshake", wait_res)

    async def test_send_wakes_parked_peer(self):
        hub_a = HubTool(
            self_agent_id="agent_a",
            bus=self.bus,
            registry=self.registry,
            lifecycle_manager=self.lifecycle,
        )

        p = SubagentProgress(id="parked_peer", agent="task", status="running", task="t", assignment="t")
        self.registry.register("parked_peer", p)
        self.lifecycle.park("parked_peer")
        self.assertEqual(self.registry.get("parked_peer").status, "parked")

        # Agent A sends message to parked peer -> triggers revival
        await hub_a.execute(op="send", to="parked_peer", message="Wake up!")
        self.assertEqual(self.registry.get("parked_peer").status, "idle")

    async def test_wait_consumes_message_no_inbox_duplication(self):
        """Verify messages received via wait are consumed and not duplicated in inbox."""
        hub_a = HubTool(self_agent_id="agent_a", bus=self.bus, registry=self.registry)
        hub_b = HubTool(self_agent_id="agent_b", bus=self.bus, registry=self.registry)

        # Start waiter in background
        wait_task = asyncio.create_task(hub_b.execute(op="wait", timeout=1.0))
        await asyncio.sleep(0.02)

        # Agent A sends message
        await hub_a.execute(op="send", to="agent_b", message="Direct message")

        wait_res = await wait_task
        self.assertIn("Direct message", wait_res)

        # Inbox must be empty now (message was consumed by the waiter)
        inbox_res = await hub_b.execute(op="inbox")
        self.assertIn("Inbox is empty", inbox_res)

    async def test_wait_with_from_alias_and_filtering(self):
        """Verify wait supports 'from' parameter and only resolves matching sender."""
        hub_a = HubTool(self_agent_id="agent_a", bus=self.bus, registry=self.registry)
        hub_b = HubTool(self_agent_id="agent_b", bus=self.bus, registry=self.registry)
        hub_c = HubTool(self_agent_id="agent_c", bus=self.bus, registry=self.registry)

        # Agent B waits specifically for Agent C using 'from' alias
        wait_task = asyncio.create_task(hub_b.execute(op="wait", timeout=1.0, **{"from": "agent_c"}))
        await asyncio.sleep(0.02)

        # Agent A sends a message (should NOT wake Agent B's waiter for agent_c)
        await hub_a.execute(op="send", to="agent_b", message="Ignored by waiter")
        self.assertFalse(wait_task.done())

        # Agent C sends message (wakes Agent B's waiter)
        await hub_c.execute(op="send", to="agent_b", message="Targeted message from C")
        wait_res = await wait_task
        self.assertIn("Targeted message from C", wait_res)

    async def test_hub_list_with_status_filter(self):
        """Verify hub list supports status filtering."""
        hub = HubTool(self_agent_id="main", bus=self.bus, registry=self.registry)
        self.registry.register("idle_1", SubagentProgress(id="idle_1", agent="task", status="idle", task="t", assignment="t"))
        self.registry.register("parked_1", SubagentProgress(id="parked_1", agent="scout", status="parked", task="t", assignment="t"))

        list_parked = await hub.execute(op="list", status="parked")
        self.assertIn("parked_1", list_parked)
        self.assertNotIn("idle_1", list_parked)

if __name__ == "__main__":
    unittest.main()
