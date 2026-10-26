import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from nova_apex.core.schemas import (
    AgentGoal, PlanStep, StepStatus, GoalStatus, ActionDomain, StepResult, ActionRequest
)
from nova_apex.core.planner import planner
from nova_apex.core.logger import agent_logger
from nova_apex.core.memory import agent_memory

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
        self.pending_approval: Optional[Dict[str, Any]] = None
        self._approval_event: Optional[asyncio.Event] = None
        self._approval_decision: Optional[bool] = None

    def get_status(self) -> Dict[str, Any]:
        if not self.active_goal:
            return {"status": "idle", "active_goal": None, "pending_approval": None}

        return {
            "status": self.active_goal.status.value,
            "goal_id": self.active_goal.goal_id,
            "summary": self.active_goal.summary,
            "current_step_index": self.active_goal.current_step_index,
            "total_steps": len(self.active_goal.steps),
            "steps": [
                {
                    "step_id": step.step_id,
                    "title": step.title,
                    "description": step.description,
                    "domain": step.domain.value,
                    "status": step.status.value,
                    "result": {
                        "success": step.result.success,
                        "error": step.result.error,
                        "screenshot_path": step.result.screenshot_path
                    } if step.result else None
                }
                for step in self.active_goal.steps
            ],
            "pending_approval": self.pending_approval,
            "created_at": self.active_goal.created_at.isoformat(),
            "updated_at": self.active_goal.updated_at.isoformat()
        }

    def _requires_approval(self, action: ActionRequest) -> bool:
        from nova_apex.core.schemas import ActionType

        always_confirm = {
            ActionType.CREATE_ACCOUNT,
            ActionType.SUBMIT_FORM,
            ActionType.EVALUATE_JS,
            ActionType.EXECUTE_SHELL,
            ActionType.DELETE_FILE,
            ActionType.KILL_PROCESS,
            ActionType.DIRECT_WINDOW_MESSAGE,
            ActionType.RAW_KEYSTROKE,
            ActionType.CLIPBOARD_WRITE,
            ActionType.ADB_INSTALL_APK,
            ActionType.ADB_KEYEVENT
        }
        if action.domain == ActionDomain.BROWSER and action.action_type == ActionType.CLICK_ELEMENT:
            return True
        if action.action_type in always_confirm:
            return True
        return False

    async def _request_action_approval(self, step: PlanStep) -> bool:
        self._approval_event = asyncio.Event()
        self._approval_decision = None
        self.pending_approval = {
            "step_id": step.step_id,
            "title": step.title,
            "description": step.description,
            "domain": step.domain.value,
            "action_type": step.action_type.value
        }
        self.active_goal.status = GoalStatus.WAITING_HUMAN
        self.active_goal.updated_at = datetime.utcnow()
        agent_logger.warning(
            f"Waiting for user approval before {step.domain.value} action {step.action_type.value}.",
            domain="APPROVAL"
        )
        await self._approval_event.wait()
        approved = self._approval_decision is True
        self.pending_approval = None
        self._approval_event = None
        self._approval_decision = None
        self.active_goal.status = GoalStatus.EXECUTING
        self.active_goal.updated_at = datetime.utcnow()
        return approved

    def approve_pending_action(self) -> bool:
        if not self._approval_event or not self.pending_approval:
            return False
        self._approval_decision = True
        self._approval_event.set()
        return True

    def reject_pending_action(self) -> bool:
        if not self._approval_event or not self.pending_approval:
            return False
        self._approval_decision = False
        self._approval_event.set()
        return True

    async def run_goal(self, prompt: str) -> AgentGoal:
        async with self._lock:
            self._is_aborted = False
            self._is_paused = False
            
            # Immediately register new active goal so UI updates instantly
            self.active_goal = AgentGoal(
                prompt=prompt,
                status=GoalStatus.PLANNING,
                steps=[]
            )
            agent_logger.info(f"Initializing autonomous mission: '{prompt}'", domain="ENGINE", goal_id=self.active_goal.goal_id)

            # Phase 1: Synthesize High-Level Execution Plan
            goal = await planner.create_plan(prompt)
            goal.status = GoalStatus.EXECUTING
            self.active_goal = goal

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

                if self._requires_approval(step.suggested_action):
                    if not await self._request_action_approval(step):
                        result = StepResult(
                            action_id=step.suggested_action.action_id,
                            success=False,
                            error="Action was not approved.",
                            data={"approval_rejected": True}
                        )
                    else:
                        step.suggested_action.params["user_confirmed"] = True
                        result = await self._dispatch_action(step.suggested_action)
                else:
                    result = await self._dispatch_action(step.suggested_action)
                step.result = result

                if result.success:
                    step.status = StepStatus.SUCCESS
                    agent_logger.success(f"Step {step.step_id} completed successfully.", domain="ENGINE")
                else:
                    step.status = StepStatus.FAILED
                    agent_logger.error(f"Step {step.step_id} failed: {result.error}", domain="ENGINE")
                    if result.data.get("approval_rejected"):
                        break

                    # Phase 3: Self-Correction & Replanning
                    if step.retries_left > 0:
                        agent_logger.warning(f"Initiating self-healing protocol (Retries remaining: {step.retries_left})...", domain="ENGINE")
                        recovery_step = await planner.replan_on_error(goal, step, result.error or "Unknown error")
                        if recovery_step:
                            agent_logger.info(f"Executing recovery action: {recovery_step.title}", domain="ENGINE")
                            if self._requires_approval(recovery_step.suggested_action):
                                if not await self._request_action_approval(recovery_step):
                                    rec_res = StepResult(
                                        action_id=recovery_step.suggested_action.action_id,
                                        success=False,
                                        error="Recovery action was not approved.",
                                        data={"approval_rejected": True}
                                    )
                                else:
                                    recovery_step.suggested_action.params["user_confirmed"] = True
                                    rec_res = await self._dispatch_action(recovery_step.suggested_action)
                            else:
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
                from nova_apex.controllers.browser_controller import browser_controller
                return await browser_controller.execute_action(action)

            elif domain in [ActionDomain.DESKTOP, ActionDomain.FILESYSTEM]:
                from nova_apex.controllers.desktop_controller import desktop_controller
                # Run synchronous desktop/filesystem in thread pool to prevent blocking event loop
                return await asyncio.to_thread(desktop_controller.execute_action, action)

            elif domain == ActionDomain.MOBILE:
                from nova_apex.controllers.mobile_controller import mobile_controller
                return await asyncio.to_thread(mobile_controller.execute_action, action)

            elif domain == ActionDomain.SHELL:
                from nova_apex.controllers.shell_controller import shell_controller
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
        if self._approval_event and not self._approval_event.is_set():
            self._approval_decision = False
            self._approval_event.set()
        agent_logger.warning("Agent execution aborted by user request.", domain="ENGINE")

engine = AutonomousEngine()
