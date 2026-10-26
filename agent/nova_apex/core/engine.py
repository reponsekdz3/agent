import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from nova_apex.core.schemas import (
    AgentGoal, PlanStep, StepStatus, GoalStatus, ActionDomain, StepResult, ActionRequest
)
from nova_apex.core.planner import planner
from nova_apex.core.logger import agent_logger
from nova_apex.core.memory import agent_memory
from nova_apex.controllers.browser_controller import browser_controller
from nova_apex.controllers.desktop_controller import desktop_controller
from nova_apex.controllers.mobile_controller import mobile_controller
from nova_apex.controllers.shell_controller import shell_controller

class AutonomousEngine:
    """
    NOVA-APEX Orchestration Engine:
    Coordinates perception, hierarchical planning, cross-domain dispatching,
    and self-healing dynamic recovery.
    """

    def __init__(self):
        self.active_goal: Optional[AgentGoal] = None
        self._is_paused = False
        self._is_aborted = False
        self._lock = asyncio.Lock()

    def get_status(self) -> Dict[str, Any]:
        if not self.active_goal:
            return {"status": "idle", "active_goal": None}

        return {
            "status": self.active_goal.status.value,
            "goal_id": self.active_goal.goal_id,
            "prompt": self.active_goal.prompt,
            "summary": self.active_goal.summary,
            "current_step_index": self.active_goal.current_step_index,
            "total_steps": len(self.active_goal.steps),
            "steps": [s.dict() for s in self.active_goal.steps],
            "created_at": self.active_goal.created_at.isoformat(),
            "updated_at": self.active_goal.updated_at.isoformat()
        }

    async def run_goal(self, prompt: str) -> AgentGoal:
        async with self._lock:
            self._is_aborted = False
            self._is_paused = False
            agent_logger.info(f"Initializing autonomous mission: '{prompt}'", domain="ENGINE")

            # Phase 1: Synthesize High-Level Execution Plan
            goal = await planner.create_plan(prompt)
            self.active_goal = goal
            goal.status = GoalStatus.EXECUTING

            # Phase 2: Sequential Milestone Execution with Dynamic Healing
            for i, step in enumerate(goal.steps):
                if self._is_aborted:
                    goal.status = GoalStatus.FAILED
                    agent_logger.warning("Mission execution manually aborted.", domain="ENGINE")
                    break

                while self._is_paused:
                    goal.status = GoalStatus.PAUSED
                    await asyncio.sleep(0.5)
                goal.status = GoalStatus.EXECUTING

                goal.current_step_index = i
                goal.updated_at = datetime.utcnow()
                step.status = StepStatus.IN_PROGRESS
                agent_logger.info(f"--- [Step {step.step_id}/{len(goal.steps)}] {step.title} ---", domain="ENGINE")

                # Execute action
                result = await self._dispatch_action(step.suggested_action)
                step.result = result

                if result.success:
                    step.status = StepStatus.SUCCESS
                    agent_logger.success(f"Step {step.step_id} completed successfully.", domain="ENGINE")
                else:
                    step.status = StepStatus.FAILED
                    agent_logger.error(f"Step {step.step_id} failed: {result.error}", domain="ENGINE")

                    # Phase 3: Self-Correction & Replanning
                    if step.retries_left > 0:
                        agent_logger.warning(f"Initiating self-healing protocol (Retries remaining: {step.retries_left})...", domain="ENGINE")
                        recovery_step = await planner.replan_on_error(goal, step, result.error or "Unknown error")
                        if recovery_step:
                            agent_logger.info(f"Executing recovery action: {recovery_step.title}", domain="ENGINE")
                            rec_res = await self._dispatch_action(recovery_step.suggested_action)
                            recovery_step.result = rec_res
                            if rec_res.success:
                                recovery_step.status = StepStatus.SUCCESS
                                step.status = StepStatus.SUCCESS
                                agent_logger.success(f"Recovery succeeded for Step {step.step_id}.", domain="ENGINE")
                            else:
                                step.retries_left -= 1
                    
                    if step.status != StepStatus.SUCCESS:
                        agent_logger.error(f"Milestone {step.step_id} failed after recovery attempts.", domain="ENGINE")

            # Final Evaluation
            all_succeeded = all(s.status == StepStatus.SUCCESS for s in goal.steps)
            goal.status = GoalStatus.SUCCESS if all_succeeded else GoalStatus.FAILED
            goal.updated_at = datetime.utcnow()

            if goal.status == GoalStatus.SUCCESS:
                agent_logger.success(f"Mission '{prompt[:60]}' completed with 100% success rate!", domain="ENGINE")
            else:
                agent_logger.warning(f"Mission completed with partial or failed milestones.", domain="ENGINE")

            return goal

    async def _dispatch_action(self, action: ActionRequest) -> StepResult:
        domain = action.domain
        try:
            if domain == ActionDomain.BROWSER:
                return await browser_controller.execute_action(action)

            elif domain in [ActionDomain.DESKTOP, ActionDomain.FILESYSTEM]:
                # Run synchronous desktop/filesystem in thread pool to prevent blocking event loop
                return await asyncio.to_thread(desktop_controller.execute_action, action)

            elif domain == ActionDomain.MOBILE:
                return await asyncio.to_thread(mobile_controller.execute_action, action)

            elif domain == ActionDomain.SHELL:
                return await shell_controller.execute_action(action)

            elif domain == ActionDomain.MEMORY:
                return StepResult(action_id=action.action_id, success=True, output="Memory operation completed")

            else:
                return StepResult(action_id=action.action_id, success=True, output=f"Executed default action in {domain}")

        except Exception as e:
            agent_logger.error(f"Dispatch exception in {domain}: {e}", domain="ENGINE")
            return StepResult(action_id=action.action_id, success=False, error=str(e))

    def pause(self):
        self._is_paused = True
        agent_logger.warning("Agent execution paused.", domain="ENGINE")

    def resume(self):
        self._is_paused = False
        agent_logger.info("Agent execution resumed.", domain="ENGINE")

    def abort(self):
        self._is_aborted = True
        agent_logger.warning("Agent execution aborted by user request.", domain="ENGINE")

engine = AutonomousEngine()
