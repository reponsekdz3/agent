import json
from typing import List, Optional
from nova_apex.core.schemas import AgentGoal, PlanStep, StepStatus, ActionDomain, ActionType, ActionRequest, GoalStatus
from nova_apex.core.llm_provider import llm
from nova_apex.core.logger import agent_logger

SYSTEM_PLANNING_PROMPT = """
You are the Executive Planner of NOVA-APEX, the advanced universal automation agent.
You deconstruct high-level goals across 4 operational domains:
1. 'browser': Web browsing, forms, account creation, scraping, button clicks, DOM evaluation.
2. 'desktop': OS GUI control, PyAutoGUI mouse/keyboard, active window focus, app launching.
3. 'filesystem': Creating files, folders, writing code, reading files, searching directories.
4. 'mobile': Android ADB actions (tap, swipe, input_text, keyevent, app launch, screenshot).
5. 'shell': Running commands, system automation, scripting.

Safety boundaries:
- For shopping, ordering, bookings, reservations, and account registration, only search,
  compare, prepare, and present a draft for the user to review. Never finalize a purchase,
  booking, registration, payment, or other external submission autonomously.
- Stop before clicking any final-action button or submitting a form. The controller
  requires a separate explicit user approval for browser clicks and submissions.
- Do not bypass CAPTCHAs, anti-bot controls, identity checks, or verification codes.
- Do not retrieve or enter OTPs or other authentication codes automatically.

Format your response strictly as valid JSON with:
{
  "goal": "summary of goal",
  "explanation": "high-level strategy",
  "steps": [
    {
      "step_id": 1,
      "title": "Short title",
      "description": "What this step accomplishes",
      "domain": "browser|desktop|mobile|filesystem|shell",
      "action_type": "navigate|click_element|type_element|create_account|desktop_click|desktop_type|create_file|write_file|create_folder|adb_tap|adb_input_text|execute_shell|...",
      "target": "target selector, coordinate, or file path",
      "value": "text to type, URL, or code",
      "params": {}
    }
  ]
}
"""

class Planner:
    """
    Deconstructs high-level objectives into sequential, self-healing execution graphs.
    """

    async def create_plan(self, prompt: str) -> AgentGoal:
        agent_logger.thinking(f"Formulating execution graph for: '{prompt}'", domain="PLANNER")

        user_content = f"Formulate a precise, step-by-step automation plan for the following objective:\n\n{prompt}"
        response_text = await llm.generate_response(
            prompt=user_content,
            system_instruction=SYSTEM_PLANNING_PROMPT,
            json_mode=True
        )

        try:
            # Strip markdown code fences if present
            clean_json = response_text.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            clean_json = clean_json.strip()

            data = json.loads(clean_json)
        except Exception as e:
            agent_logger.error(f"Failed to parse planner output as JSON: {e}. Using raw text.", domain="PLANNER")
            data = {"steps": []}

        plan_steps: List[PlanStep] = []
        raw_steps = data.get("steps", [])

        for s in raw_steps:
            try:
                domain_val = ActionDomain(s.get("domain", "system").lower())
            except ValueError:
                domain_val = ActionDomain.SYSTEM

            try:
                action_type_val = ActionType(s.get("action_type", "complete").lower())
            except ValueError:
                action_type_val = ActionType.COMPLETE

            action_req = ActionRequest(
                domain=domain_val,
                action_type=action_type_val,
                description=s.get("description", s.get("title", "Execute action")),
                target=s.get("target"),
                value=s.get("value"),
                params=s.get("params", {})
            )

            plan_step = PlanStep(
                step_id=s.get("step_id", len(plan_steps) + 1),
                title=s.get("title", f"Step {len(plan_steps) + 1}"),
                description=s.get("description", ""),
                domain=domain_val,
                action_type=action_type_val,
                suggested_action=action_req,
                status=StepStatus.PENDING
            )
            plan_steps.append(plan_step)

        goal = AgentGoal(
            prompt=prompt,
            status=GoalStatus.PLANNING,
            steps=plan_steps,
            summary=data.get("explanation", "Plan synthesized successfully.")
        )

        agent_logger.success(f"Synthesized plan with {len(plan_steps)} structured milestone(s).", domain="PLANNER")
        return goal

    async def replan_on_error(self, goal: AgentGoal, failed_step: PlanStep, error_msg: str) -> Optional[PlanStep]:
        """
        Dynamically synthesize a self-healing alternative step when an action fails.
        """
        agent_logger.warning(f"Synthesizing self-healing recovery for Step {failed_step.step_id}: {error_msg}", domain="PLANNER")

        prompt = f"""
Step {failed_step.step_id} ('{failed_step.title}') in domain '{failed_step.domain}' failed with error:
{error_msg}

Goal: {goal.prompt}

Provide a recovery or bypass action in JSON format with domain, action_type, target, value, description.
"""
        response_text = await llm.generate_response(prompt=prompt, json_mode=True)
        try:
            clean = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            rec_step = PlanStep(
                step_id=failed_step.step_id,
                title=f"Recovery: {failed_step.title}",
                description=data.get("description", "Alternative recovery action"),
                domain=ActionDomain(data.get("domain", failed_step.domain)),
                action_type=ActionType(data.get("action_type", "wait")),
                suggested_action=ActionRequest(
                    domain=ActionDomain(data.get("domain", failed_step.domain)),
                    action_type=ActionType(data.get("action_type", "wait")),
                    description=data.get("description", "Recovery action"),
                    target=data.get("target"),
                    value=data.get("value")
                ),
                status=StepStatus.PENDING,
                retries_left=failed_step.retries_left - 1
            )
            return rec_step
        except Exception:
            return None

planner = Planner()
